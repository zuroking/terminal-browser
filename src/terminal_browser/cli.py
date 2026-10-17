from __future__ import annotations

import argparse
import shutil
import sys
import traceback
from typing import NoReturn, Protocol, cast

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from .core.clock import SystemClock
from .core.errors import BrowserError
from .core.limits import Limits
from .core.sanitize import sanitize_text
from .html.tree import TreeBuilderImpl
from .net.cache import DiskCache
from .net.cookies import CookieJarImpl
from .net.http import HttpClientImpl
from .net.transport import SocketTransport
from .render.layout import LayoutEngineImpl
from .session.session import BrowserSession, BrowserSessionImpl
from .term.output import Terminal, TerminalImpl, WriteRequest
from .ui.repl import BoundedInput, InputLine, ReplImpl, TerminalSize


class CliArgs(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    url: str | None
    width: int | None
    cache_dir: str | None
    no_cache: bool
    debug: bool

    @model_validator(mode="after")
    def validate_width(self) -> CliArgs:
        if self.width is not None and self.width <= 0:
            raise ValueError("width must be positive")
        return self


class Cli(Protocol):
    def run(self, argv: list[str]) -> int: ...


class _ArgumentParser(argparse.ArgumentParser):
    def __init__(self, terminal: Terminal, terminal_size: TerminalSize) -> None:
        super().__init__(add_help=False)
        self._terminal = terminal
        self._terminal_size = terminal_size

    def error(self, message: str) -> NoReturn:
        self._write_error(f"argument error: {message}")
        raise argparse.ArgumentError(None, message)

    def _write_error(self, message: str) -> None:
        width = _width(self._terminal_size, None, 80, 4, 120)
        self._terminal.write(
            WriteRequest(
                lines=(_one_line(message),),
                width=width,
                stream="stderr",
            )
        )


class _StdinInput:
    def read_line(self, max_bytes: int) -> InputLine:
        stream = sys.stdin.buffer
        data = stream.readline(max_bytes + 1)
        if not data:
            return InputLine(text=None, over_limit=False)
        if len(data) > max_bytes:
            while data and not data.endswith(b"\n"):
                data = stream.readline(max_bytes + 1)
            return InputLine(text=None, over_limit=True)
        text = data.decode("utf-8", errors="replace")
        if text.endswith("\n"):
            text = text[:-1]
        if text.endswith("\r"):
            text = text[:-1]
        return InputLine(text=text, over_limit=False)


class _ShutilTerminalSize:
    def width(self) -> int | None:
        return int(shutil.get_terminal_size().columns)


class CliImpl:
    def __init__(
        self,
        terminal: Terminal | None = None,
        terminal_size: TerminalSize | None = None,
        bounded_input: BoundedInput | None = None,
    ) -> None:
        self._limits = Limits.defaults()
        self._terminal = terminal or TerminalImpl()
        self._terminal_size = terminal_size or _ShutilTerminalSize()
        self._bounded_input = bounded_input or _StdinInput()

    def run(self, argv: list[str]) -> int:
        debug = False
        try:
            args = self._parse(argv)
            if args is None:
                return 2
            debug = args.debug
            session = self._build_session(args)
            if args.url is None:
                repl = ReplImpl(
                    limits=self._limits,
                    session=session,
                    bounded_input=self._bounded_input,
                    terminal=self._terminal,
                    terminal_size=self._terminal_size,
                    width_override=args.width,
                )
                return repl.run()
            try:
                page = session.open(args.url, self._width(args.width))
            finally:
                session.close()
            return 0 if page.status != 0 else 1
        except KeyboardInterrupt:
            return 130
        except SystemExit:
            raise
        except BrowserError as error:
            self._write_error(str(error))
            return 1
        except Exception as error:
            self._write_unexpected(error, debug)
            return 1

    def _parse(self, argv: list[str]) -> CliArgs | None:
        parser = _ArgumentParser(self._terminal, self._terminal_size)
        parser.add_argument("--url", default=None)
        parser.add_argument("--width", type=int, default=None)
        parser.add_argument("--cache-dir", dest="cache_dir", default=None)
        parser.add_argument("--no-cache", action="store_true")
        parser.add_argument("--debug", action="store_true")
        try:
            namespace = parser.parse_args(argv)
            return CliArgs(
                url=cast(str | None, namespace.url),
                width=cast(int | None, namespace.width),
                cache_dir=cast(str | None, namespace.cache_dir),
                no_cache=cast(bool, namespace.no_cache),
                debug=cast(bool, namespace.debug),
            )
        except argparse.ArgumentError:
            return None
        except ValidationError:
            self._write_error("invalid command-line arguments")
            return None

    def _build_session(self, args: CliArgs) -> BrowserSession:
        clock = SystemClock()
        cookie_jar = CookieJarImpl(clock, self._limits)
        cache: DiskCache | None = None
        if not args.no_cache:
            cache = DiskCache(
                args.cache_dir or ".terminal-browser-cache",
                self._limits,
                clock,
            )
        transport = SocketTransport(self._limits, clock)
        http_client = HttpClientImpl(
            self._limits,
            transport,
            clock,
            cache,
            cookie_jar,
        )
        tree_builder = TreeBuilderImpl()
        layout_engine = LayoutEngineImpl()
        return BrowserSessionImpl(
            limits=self._limits,
            clock=clock,
            http_client=http_client,
            tree_builder=tree_builder,
            layout_engine=layout_engine,
            terminal=self._terminal,
            cache=cache,
        )

    def _width(self, override: int | None) -> int:
        return _width(
            self._terminal_size,
            override,
            self._limits.terminal_width_fallback,
            self._limits.min_layout_width,
            self._limits.max_line_width,
        )

    def _write_error(self, message: str) -> None:
        detail = _one_line(message) or "command failed"
        self._terminal.write(
            WriteRequest(
                lines=(detail,),
                width=self._width(None),
                stream="stderr",
            )
        )

    def _write_unexpected(self, error: Exception, debug: bool) -> None:
        detail = _one_line(str(error)) or type(error).__name__
        self._terminal.write(
            WriteRequest(
                lines=(f"unexpected error: {detail}",),
                width=self._width(None),
                stream="stderr",
            )
        )
        if debug:
            self._terminal.write(
                WriteRequest(
                    lines=(_one_line(traceback.format_exc()),),
                    width=self._width(None),
                    stream="stderr",
                )
            )


def _width(
    terminal_size: TerminalSize,
    override: int | None,
    fallback: int,
    minimum: int,
    maximum: int,
) -> int:
    candidate = override if override is not None else terminal_size.width()
    if type(candidate) is not int or candidate <= 0:
        candidate = fallback
    return max(minimum, min(candidate, maximum))


def _one_line(text: str) -> str:
    return sanitize_text(text).replace("\n", " ").replace("\t", " ")
