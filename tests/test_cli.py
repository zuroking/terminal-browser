import ast
from pathlib import Path

import pytest

import terminal_browser.cli as cli
from terminal_browser.core.errors import ConnectionLostError
from terminal_browser.session.session import BrowserSession, PageView
from terminal_browser.term.output import WriteRequest, WriteResult
from terminal_browser.ui.repl import InputLine


class FakeTerminal:
    def __init__(self) -> None:
        self.requests: list[WriteRequest] = []

    def write(self, request: WriteRequest) -> WriteResult:
        self.requests.append(request)
        return WriteResult(bytes_written=0, lines_written=len(request.lines))

    def sanitize(self, text: str) -> str:
        return text


class FakeSize:
    def width(self) -> int | None:
        return 40


class FakeInput:
    def read_line(self, max_bytes: int) -> InputLine:
        return InputLine(text=None, over_limit=False)


class FakeSession:
    def __init__(self, page: PageView | None = None) -> None:
        self.page = page or PageView(
            url="https://example.test/",
            status=200,
            title="",
            lines=("page",),
            links=[],
            forms=(),
            from_cache=False,
            notices=(),
        )
        self.open_error: BaseException | None = None
        self.open_calls: list[tuple[str, int]] = []
        self.close_count = 0

    def open(self, url: str, width: int) -> PageView:
        self.open_calls.append((url, width))
        if self.open_error is not None:
            raise self.open_error
        return self.page

    def follow(self, n: int, width: int) -> PageView:
        return self.page

    def back(self, width: int) -> PageView:
        return self.page

    def forward(self, width: int) -> PageView:
        return self.page

    def submit(
        self,
        form_index: int,
        field_values: dict[str, str],
        width: int,
    ) -> PageView:
        return self.page

    def current(self) -> PageView | None:
        return self.page

    def history(self) -> tuple[str, ...]:
        return (self.page.url,)

    def close(self) -> None:
        self.close_count += 1


def install_session(
    monkeypatch: pytest.MonkeyPatch,
    session: FakeSession,
) -> None:
    def build_session(self: cli.CliImpl, args: cli.CliArgs) -> BrowserSession:
        del self
        del args
        return session

    monkeypatch.setattr(cli.CliImpl, "_build_session", build_session)


def test_ast_import_boundaries() -> None:
    source_path = Path(__file__).parents[1] / "src" / "terminal_browser" / "cli.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    allowed_stdlib = {"__future__", "argparse", "shutil", "sys", "traceback", "typing", "pydantic"}
    allowed_project = {
        "core.clock",
        "core.encoding",
        "core.errors",
        "core.limits",
        "core.sanitize",
        "net.cookies",
        "net.cache",
        "net.transport",
        "net.http",
        "html.tree",
        "render.layout",
        "session.session",
        "term.output",
        "ui.repl",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name.split(".")[0] in allowed_stdlib for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                assert node.module in allowed_stdlib
            else:
                assert node.level == 1
                assert node.module in allowed_project


def test_cli_args_parsing_defaults() -> None:
    terminal = FakeTerminal()
    command = cli.CliImpl(
        terminal=terminal,
        terminal_size=FakeSize(),
        bounded_input=FakeInput(),
    )

    args = command._parse([])

    assert args is not None
    assert args.url is None
    assert args.width is None
    assert args.cache_dir is None
    assert args.no_cache is False
    assert args.debug is False


def test_cli_invalid_args_returns_2() -> None:
    terminal = FakeTerminal()
    command = cli.CliImpl(
        terminal=terminal,
        terminal_size=FakeSize(),
        bounded_input=FakeInput(),
    )

    assert command.run(["--width", "abc"]) == 2
    assert any(request.stream == "stderr" for request in terminal.requests)


def test_one_shot_navigates_and_returns_0(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession()
    install_session(monkeypatch, session)
    command = cli.CliImpl(
        terminal=FakeTerminal(),
        terminal_size=FakeSize(),
        bounded_input=FakeInput(),
    )

    assert command.run(["--no-cache", "--url", "https://example.test/"]) == 0
    assert session.open_calls == [("https://example.test/", 40)]
    assert session.close_count == 1


def test_one_shot_browser_error_returns_1(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession()
    session.open_error = ConnectionLostError("offline")
    install_session(monkeypatch, session)
    terminal = FakeTerminal()
    command = cli.CliImpl(
        terminal=terminal,
        terminal_size=FakeSize(),
        bounded_input=FakeInput(),
    )

    assert command.run(["--no-cache", "--url", "https://example.test/"]) == 1
    assert session.close_count == 1
    assert any(request.stream == "stderr" for request in terminal.requests)


def test_interactive_mode_starts_repl(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession()
    install_session(monkeypatch, session)

    class FakeRepl:
        def __init__(self, **kwargs: object) -> None:
            del kwargs

        def run(self) -> int:
            return 7

    monkeypatch.setattr(cli, "ReplImpl", FakeRepl)
    command = cli.CliImpl(
        terminal=FakeTerminal(),
        terminal_size=FakeSize(),
        bounded_input=FakeInput(),
    )

    assert command.run([]) == 7


def test_top_level_unexpected_exception_returns_1(monkeypatch: pytest.MonkeyPatch) -> None:
    def exploding_clock() -> object:
        raise ValueError("dependency failure")

    monkeypatch.setattr(cli, "SystemClock", exploding_clock)
    terminal = FakeTerminal()
    command = cli.CliImpl(
        terminal=terminal,
        terminal_size=FakeSize(),
        bounded_input=FakeInput(),
    )

    assert command.run(["--no-cache"]) == 1
    assert any(request.stream == "stderr" for request in terminal.requests)


def test_debug_flag_includes_sanitized_traceback(monkeypatch: pytest.MonkeyPatch) -> None:
    def exploding_clock() -> object:
        raise ValueError("dependency\x1b[31m failure")

    monkeypatch.setattr(cli, "SystemClock", exploding_clock)
    terminal = FakeTerminal()
    command = cli.CliImpl(
        terminal=terminal,
        terminal_size=FakeSize(),
        bounded_input=FakeInput(),
    )

    assert command.run(["--no-cache", "--debug"]) == 1
    output = " ".join(line for request in terminal.requests for line in request.lines)
    assert "unexpected error" in output
    assert "Traceback" in output
    assert "\x1b" not in output


def test_keyboard_interrupt_returns_130(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession()
    session.open_error = KeyboardInterrupt()
    install_session(monkeypatch, session)
    command = cli.CliImpl(
        terminal=FakeTerminal(),
        terminal_size=FakeSize(),
        bounded_input=FakeInput(),
    )

    assert command.run(["--no-cache", "--url", "https://example.test/"]) == 130
    assert session.close_count == 1
