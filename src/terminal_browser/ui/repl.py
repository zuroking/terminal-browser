from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, model_validator

from ..core.errors import BrowserError, FormError, InvalidNavigationError
from ..core.sanitize import sanitize_text
from ..session.session import BrowserSession
from ..term.output import Terminal, WriteRequest


class InputLine(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    text: str | None
    over_limit: bool

    @model_validator(mode="after")
    def validate_state(self) -> InputLine:
        if self.text is not None and self.over_limit:
            raise ValueError("text and over_limit cannot both be set")
        return self


class BoundedInput(Protocol):
    def read_line(self, max_bytes: int) -> InputLine: ...


class TerminalSize(Protocol):
    def width(self) -> int | None: ...


class Repl(Protocol):
    def run(self) -> int: ...


class _LimitValues(Protocol):
    max_repl_line_bytes: int
    max_repl_tokens: int
    terminal_width_fallback: int
    min_layout_width: int
    max_line_width: int


class ReplImpl:
    def __init__(
        self,
        limits: _LimitValues,
        session: BrowserSession,
        bounded_input: BoundedInput,
        terminal: Terminal,
        terminal_size: TerminalSize,
        width_override: int | None = None,
    ) -> None:
        self._limits = limits
        self._session = session
        self._bounded_input = bounded_input
        self._terminal = terminal
        self._terminal_size = terminal_size
        self._width_override = width_override

    def run(self) -> int:
        try:
            while True:
                width = self._width()
                self._write(("> ",), width, "stdout")
                item = self._bounded_input.read_line(
                    max_bytes=self._limits.max_repl_line_bytes
                )
                if item.text is None:
                    if item.over_limit:
                        self._notice("input line exceeds the byte limit", width)
                        continue
                    return 0
                line = _one_line(item.text)
                tokens = _tokenize(line, self._limits.max_repl_tokens)
                if tokens is None:
                    self._notice("input line exceeds the token limit", width)
                    continue
                if not tokens:
                    continue
                if tokens[0] == "quit":
                    if len(tokens) != 1:
                        self._notice("usage: quit", width)
                        continue
                    return 0
                self._dispatch(tokens, width)
        except KeyboardInterrupt:
            return 130
        finally:
            self._session.close()

    def _dispatch(self, tokens: tuple[str, ...], width: int) -> None:
        command = tokens[0]
        if command == "open":
            if len(tokens) != 2:
                self._notice("usage: open <url>", width)
                return
            try:
                self._session.open(tokens[1], width)
            except BrowserError as error:
                self._notice(str(error), width)
                return
            return
        if command == "follow":
            if len(tokens) != 2:
                self._notice("usage: follow <n>", width)
                return
            index = _index(tokens[1])
            if index is None:
                self._notice("usage: follow <n>", width)
                return
            try:
                self._session.follow(index, width)
            except InvalidNavigationError as error:
                self._notice(str(error), width)
                return
            except BrowserError as error:
                self._notice(str(error), width)
                return
            return
        if command == "back":
            if len(tokens) != 1:
                self._notice("usage: back", width)
                return
            try:
                self._session.back(width)
            except InvalidNavigationError as error:
                self._notice(str(error), width)
                return
            except BrowserError as error:
                self._notice(str(error), width)
                return
            return
        if command == "forward":
            if len(tokens) != 1:
                self._notice("usage: forward", width)
                return
            try:
                self._session.forward(width)
            except InvalidNavigationError as error:
                self._notice(str(error), width)
                return
            except BrowserError as error:
                self._notice(str(error), width)
                return
            return
        if command == "submit":
            if len(tokens) < 2:
                self._notice("usage: submit <n> [name=value ...]", width)
                return
            form_index = _index(tokens[1])
            if form_index is None or form_index <= 0:
                self._notice("usage: submit <n> [name=value ...]", width)
                return
            overrides = _overrides(tokens[2:])
            if overrides is None:
                self._notice("usage: submit <n> [name=value ...]", width)
                return
            try:
                current = self._session.current()
                if current is not None and form_index <= len(current.forms):
                    form = current.forms[form_index - 1]
                    names = {field.name for field in form.fields}
                    if set(overrides) - names:
                        raise FormError("form field override names an unknown control")
                self._session.submit(form_index, overrides, width)
            except FormError as error:
                self._notice(str(error), width)
                return
            except BrowserError as error:
                self._notice(str(error), width)
                return
            return
        self._notice(f"unknown command: {command}", width)

    def _notice(self, message: str, width: int) -> None:
        self._write((_one_line(message),), width, "stderr")

    def _write(
        self,
        lines: tuple[str, ...],
        width: int,
        stream: Literal["stdout", "stderr"],
    ) -> None:
        self._terminal.write(
            WriteRequest(
                lines=tuple(_one_line(line) for line in lines),
                width=width,
                stream=stream,
            )
        )

    def _width(self) -> int:
        candidate: int | None
        if self._width_override is not None:
            candidate = self._width_override
        else:
            candidate = self._terminal_size.width()
        if type(candidate) is not int or candidate <= 0:
            candidate = self._limits.terminal_width_fallback
        return max(
            self._limits.min_layout_width,
            min(candidate, self._limits.max_line_width),
        )


def _index(text: str) -> int | None:
    if not text.isascii() or not text.isdecimal():
        return None
    return int(text)


def _tokenize(line: str, max_tokens: int) -> tuple[str, ...] | None:
    tokens: list[str] = []
    current: list[str] = []
    for character in line:
        if character.isspace():
            if current:
                tokens.append("".join(current))
                current.clear()
                if len(tokens) > max_tokens:
                    return None
        else:
            current.append(character)
    if current:
        tokens.append("".join(current))
    if len(tokens) > max_tokens:
        return None
    return tuple(tokens)


def _overrides(tokens: tuple[str, ...]) -> dict[str, str] | None:
    values: dict[str, str] = {}
    for token in tokens:
        name, separator, value = token.partition("=")
        if not separator or not name:
            return None
        values[name] = value
    return values


def _one_line(text: str) -> str:
    return sanitize_text(text).replace("\n", " ").replace("\t", " ")
