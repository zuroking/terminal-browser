import ast
from pathlib import Path

import pytest

from terminal_browser.core.errors import FormError, InvalidNavigationError
from terminal_browser.core.limits import Limits
from terminal_browser.core.sanitize import sanitize_text
from terminal_browser.forms import FormField, FormSpec
from terminal_browser.session.session import PageView
from terminal_browser.term.output import WriteRequest, WriteResult
from terminal_browser.ui.repl import (
    BoundedInput,
    InputLine,
    ReplImpl,
    TerminalSize,
)


class FakeInput:
    def __init__(self, items: tuple[InputLine | KeyboardInterrupt, ...]) -> None:
        self.items = list(items)
        self.max_bytes: list[int] = []

    def read_line(self, max_bytes: int) -> InputLine:
        self.max_bytes.append(max_bytes)
        item = self.items.pop(0)
        if isinstance(item, KeyboardInterrupt):
            raise item
        return item


class FakeSize:
    def __init__(self, values: tuple[int | None, ...]) -> None:
        self.values = list(values)
        self.calls = 0

    def width(self) -> int | None:
        self.calls += 1
        if len(self.values) == 1:
            return self.values[0]
        return self.values.pop(0)


class FakeTerminal:
    def __init__(self) -> None:
        self.requests: list[WriteRequest] = []

    def write(self, request: WriteRequest) -> WriteResult:
        self.requests.append(request)
        return WriteResult(
            bytes_written=sum(len(line.encode("utf-8")) + 1 for line in request.lines),
            lines_written=len(request.lines),
        )

    def sanitize(self, text: str) -> str:
        return sanitize_text(text)


class FakeSession:
    def __init__(self, page: PageView) -> None:
        self.page = page
        self.current_page = page
        self.open_calls: list[tuple[str, int]] = []
        self.follow_calls: list[tuple[int, int]] = []
        self.back_calls: list[int] = []
        self.forward_calls: list[int] = []
        self.submit_calls: list[tuple[int, dict[str, str], int]] = []
        self.follow_error: InvalidNavigationError | None = None
        self.submit_errors: list[FormError | None] = []
        self.close_count = 0

    def open(self, url: str, width: int) -> PageView:
        self.open_calls.append((url, width))
        return self.page

    def follow(self, n: int, width: int) -> PageView:
        self.follow_calls.append((n, width))
        if self.follow_error is not None:
            raise self.follow_error
        return self.page

    def back(self, width: int) -> PageView:
        self.back_calls.append(width)
        return self.page

    def forward(self, width: int) -> PageView:
        self.forward_calls.append(width)
        return self.page

    def submit(
        self,
        form_index: int,
        field_values: dict[str, str],
        width: int,
    ) -> PageView:
        self.submit_calls.append((form_index, field_values, width))
        if self.submit_errors:
            error = self.submit_errors.pop(0)
            if error is not None:
                raise error
        return self.page

    def current(self) -> PageView | None:
        return self.current_page

    def history(self) -> tuple[str, ...]:
        return (self.page.url,)

    def close(self) -> None:
        self.close_count += 1


def page(lines: tuple[str, ...] = ("page",), forms: tuple[FormSpec, ...] = ()) -> PageView:
    return PageView(
        url="https://example.test/",
        status=200,
        title="",
        lines=lines,
        links=[],
        forms=forms,
        from_cache=False,
        notices=(),
    )


def form() -> FormSpec:
    return FormSpec(
        index=1,
        action="https://example.test/submit",
        method="POST",
        fields=(
            FormField(
                name="q",
                field_type="text",
                label="Query",
                value="",
                checked=False,
                required=False,
                disabled=False,
                options=(),
                selected_options=(),
            ),
        ),
    )


def make_repl(
    items: tuple[InputLine | KeyboardInterrupt, ...],
    session: FakeSession,
    size: FakeSize,
    terminal: FakeTerminal,
) -> ReplImpl:
    return ReplImpl(
        limits=Limits.defaults(),
        session=session,
        bounded_input=FakeInput(items),
        terminal=terminal,
        terminal_size=size,
    )


def test_ast_import_boundaries() -> None:
    source_path = Path(__file__).parents[1] / "src" / "terminal_browser" / "ui" / "repl.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    allowed = {"core.errors", "core.sanitize", "session.session", "term.output"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level == 0:
                assert node.module in {"__future__", "typing", "pydantic"}
            else:
                assert node.level == 2
                assert node.module in allowed


def test_open_command_navigates_and_writes_stdout() -> None:
    session = FakeSession(page(("visible",)))
    terminal = FakeTerminal()
    repl = make_repl(
        (InputLine(text="open https://example.test/", over_limit=False),
         InputLine(text="quit", over_limit=False)),
        session,
        FakeSize((40,)),
        terminal,
    )

    assert repl.run() == 0
    assert session.open_calls == [("https://example.test/", 40)]
    assert all("visible" not in request.lines for request in terminal.requests)
    assert all(request.stream == "stdout" for request in terminal.requests)


def test_follow_back_forward_commands() -> None:
    session = FakeSession(page(("visited",)))
    session.follow_error = InvalidNavigationError("link index is out of range")
    terminal = FakeTerminal()
    repl = make_repl(
        (InputLine(text="follow 3", over_limit=False),
         InputLine(text="back", over_limit=False),
         InputLine(text="forward", over_limit=False),
         InputLine(text="quit", over_limit=False)),
        session,
        FakeSize((40,)),
        terminal,
    )

    assert repl.run() == 0
    assert session.follow_calls == [(3, 40)]
    assert session.back_calls == [40]
    assert session.forward_calls == [40]
    assert any(request.stream == "stderr" for request in terminal.requests)


def test_submit_command_with_and_without_overrides() -> None:
    session = FakeSession(page(("submitted",), (form(),)))
    session.submit_errors = [None, FormError("form rejected")]
    terminal = FakeTerminal()
    repl = make_repl(
        (InputLine(text="submit 1 q=a=b", over_limit=False),
         InputLine(text="submit 1", over_limit=False),
         InputLine(text="submit 1 unknown=x", over_limit=False),
         InputLine(text="quit", over_limit=False)),
        session,
        FakeSize((40,)),
        terminal,
    )

    assert repl.run() == 0
    assert session.submit_calls == [
        (1, {"q": "a=b"}, 40),
        (1, {}, 40),
    ]
    assert any("form rejected" in line for request in terminal.requests for line in request.lines)


def test_quit_command_returns_zero_and_closes_session() -> None:
    session = FakeSession(page())
    repl = make_repl(
        (InputLine(text="quit", over_limit=False),),
        session,
        FakeSize((40,)),
        FakeTerminal(),
    )

    assert repl.run() == 0
    assert session.close_count == 1


def test_unknown_command_emits_notice_and_continues() -> None:
    session = FakeSession(page())
    terminal = FakeTerminal()
    repl = make_repl(
        (InputLine(text="bogus", over_limit=False), InputLine(text="quit", over_limit=False)),
        session,
        FakeSize((40,)),
        terminal,
    )

    assert repl.run() == 0
    assert any("unknown command" in line for request in terminal.requests for line in request.lines)
    assert session.open_calls == []


def test_empty_lines_are_ignored() -> None:
    session = FakeSession(page())
    terminal = FakeTerminal()
    repl = make_repl(
        (InputLine(text="", over_limit=False),
         InputLine(text=" \t", over_limit=False),
         InputLine(text="quit", over_limit=False)),
        session,
        FakeSize((40,)),
        terminal,
    )

    assert repl.run() == 0
    assert all(request.stream == "stdout" for request in terminal.requests)
    assert session.open_calls == []


def test_eof_returns_zero_after_close() -> None:
    session = FakeSession(page())
    repl = make_repl(
        (InputLine(text=None, over_limit=False),),
        session,
        FakeSize((40,)),
        FakeTerminal(),
    )

    assert repl.run() == 0
    assert session.close_count == 1


def test_keyboard_interrupt_returns_130() -> None:
    session = FakeSession(page())
    repl = make_repl(
        (KeyboardInterrupt(),),
        session,
        FakeSize((40,)),
        FakeTerminal(),
    )

    assert repl.run() == 130
    assert session.close_count == 1


def test_over_limit_input_emits_notice_and_discards() -> None:
    session = FakeSession(page())
    terminal = FakeTerminal()
    repl = make_repl(
        (InputLine(text=None, over_limit=True), InputLine(text="quit", over_limit=False)),
        session,
        FakeSize((40,)),
        terminal,
    )

    assert repl.run() == 0
    assert any(request.stream == "stderr" for request in terminal.requests)
    assert session.open_calls == []


def test_terminal_size_fallback_and_min_width() -> None:
    fallback_session = FakeSession(page())
    fallback_repl = make_repl(
        (InputLine(text="open https://example.test/", over_limit=False),
         InputLine(text="quit", over_limit=False)),
        fallback_session,
        FakeSize((None,)),
        FakeTerminal(),
    )
    assert fallback_repl.run() == 0
    assert fallback_session.open_calls[0][1] == 80

    narrow_session = FakeSession(page())
    narrow_repl = make_repl(
        (InputLine(text="open https://example.test/", over_limit=False),
         InputLine(text="quit", over_limit=False)),
        narrow_session,
        FakeSize((1,)),
        FakeTerminal(),
    )
    assert narrow_repl.run() == 0
    assert narrow_session.open_calls[0][1] == 4
