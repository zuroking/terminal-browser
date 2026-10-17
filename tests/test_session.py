import ast
from pathlib import Path

import pytest

from terminal_browser.core.clock import FakeClock
from terminal_browser.core.errors import BrowserError, ConnectionLostError
from terminal_browser.core.limits import Limits
from terminal_browser.core.sanitize import sanitize_text
from terminal_browser.html.tree import TreeBuilderImpl
from terminal_browser.net.http import HttpRequest, HttpResponse
from terminal_browser.render.layout import LayoutEngineImpl
from terminal_browser.session.session import BrowserSessionImpl
from terminal_browser.term.output import WriteRequest, WriteResult


class FakeHttpClient:
    def __init__(self, responses: tuple[HttpResponse | Exception, ...]) -> None:
        self.responses = list(responses)
        self.requests: list[HttpRequest] = []
        self.deadlines: list[float] = []

    def request(self, request: HttpRequest, navigation_deadline: float) -> HttpResponse:
        self.requests.append(request)
        self.deadlines.append(navigation_deadline)
        if not self.responses:
            raise AssertionError("fake HTTP client has no scripted response")
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


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


def limits(**overrides: int) -> Limits:
    return Limits.model_validate({**Limits.defaults().model_dump(), **overrides})


def response(
    url: str,
    body: str = "<html><body><p>page</p></body></html>",
    *,
    status: int = 200,
    content_type: str = "text/html; charset=utf-8",
    from_cache: bool = False,
    notices: tuple[str, ...] = (),
) -> HttpResponse:
    headers = () if content_type == "" else (("Content-Type", content_type),)
    return HttpResponse(
        url=url,
        status=status,
        reason="OK",
        headers=headers,
        body=body.encode("utf-8"),
        redirect_chain=(),
        from_cache=from_cache,
        revalidated=False,
        notices=notices,
    )


def make_session(
    http_client: FakeHttpClient,
    terminal: FakeTerminal,
    session_limits: Limits | None = None,
) -> BrowserSessionImpl:
    return BrowserSessionImpl(
        limits=session_limits or Limits.defaults(),
        clock=FakeClock(0.0, 100.0),
        http_client=http_client,
        tree_builder=TreeBuilderImpl(),
        layout_engine=LayoutEngineImpl(),
        terminal=terminal,
    )


def test_ast_import_boundaries() -> None:
    source_path = Path(__file__).parents[1] / "src" / "terminal_browser" / "session" / "session.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    allowed = {
        "core.clock",
        "core.encoding",
        "core.errors",
        "core.limits",
        "core.sanitize",
        "url",
        "net.http",
        "net.cookies",
        "net.cache",
        "html.tree",
        "forms",
        "render.layout",
        "term.output",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level == 0:
                assert node.module in {"__future__", "dataclasses", "typing", "pydantic"}
            else:
                assert node.level == 2
                assert node.module in allowed


def test_successful_open_commits_history_and_page() -> None:
    http_client = FakeHttpClient(
        (response("https://example.test/first", "<html><title>First</title><p>one</p></html>"),)
    )
    terminal = FakeTerminal()
    session = make_session(http_client, terminal)

    page = session.open("https://example.test/first", 40)

    assert page.url == "https://example.test/first"
    assert page.status == 200
    assert page.title == "First"
    assert "one" in page.lines
    assert session.current() == page
    assert session.history() == ("https://example.test/first",)
    assert terminal.requests[0].stream == "stdout"


def test_failed_navigation_preserves_state() -> None:
    first = response("https://example.test/first", "<html><title>First</title></html>")
    http_client = FakeHttpClient((first, ConnectionLostError("offline")))
    terminal = FakeTerminal()
    session = make_session(http_client, terminal)
    committed = session.open("https://example.test/first", 40)

    failed = session.open("https://example.test/missing", 40)

    assert failed.status == 0
    assert session.current() == committed
    assert session.history() == ("https://example.test/first",)
    assert terminal.requests[-1].stream == "stderr"


def test_forward_history_truncated_on_new_open() -> None:
    http_client = FakeHttpClient(
        (
            response("https://example.test/a", "<html><title>A</title></html>"),
            response("https://example.test/b", "<html><title>B</title></html>"),
            response("https://example.test/a", "<html><title>A fresh</title></html>"),
            response("https://example.test/c", "<html><title>C</title></html>"),
        )
    )
    session = make_session(http_client, FakeTerminal())
    session.open("https://example.test/a", 40)
    session.open("https://example.test/b", 40)
    session.back(40)

    session.open("https://example.test/c", 40)

    assert session.history() == ("https://example.test/a", "https://example.test/c")


def test_max_history_enforced_by_dropping_oldest() -> None:
    http_client = FakeHttpClient(
        (
            response("https://example.test/a", "<html><title>A</title></html>"),
            response("https://example.test/b", "<html><title>B</title></html>"),
            response("https://example.test/c", "<html><title>C</title></html>"),
        )
    )
    session = make_session(http_client, FakeTerminal(), limits(max_history=2))

    session.open("https://example.test/a", 40)
    session.open("https://example.test/b", 40)
    session.open("https://example.test/c", 40)

    assert session.history() == ("https://example.test/b", "https://example.test/c")
    current_page = session.current()
    assert current_page is not None
    assert current_page.url == "https://example.test/c"


def test_browser_error_mapped_to_error_view() -> None:
    http_client = FakeHttpClient((ConnectionLostError("bad \x1b[31mresponse"),))
    session = make_session(http_client, FakeTerminal())

    page = session.open("https://example.test/fail", 40)

    assert page.status == 0
    assert page.url == "https://example.test/fail"
    assert page.title == ""
    assert page.lines == ()
    assert page.links == []
    assert page.forms == ()
    assert page.from_cache is False
    assert page.notices == ("bad [31mresponse",)


def test_unexpected_exceptions_propagate() -> None:
    open_http = FakeHttpClient((ValueError("open boom"),))
    open_session = make_session(open_http, FakeTerminal())
    with pytest.raises(ValueError, match="open boom"):
        open_session.open("https://example.test/open", 40)

    follow_http = FakeHttpClient(
        (
            response(
                "https://example.test/a",
                '<html><body><a href="https://example.test/b">next</a></body></html>',
            ),
            ValueError("follow boom"),
        )
    )
    follow_session = make_session(follow_http, FakeTerminal())
    follow_session.open("https://example.test/a", 40)
    with pytest.raises(ValueError, match="follow boom"):
        follow_session.follow(1, 40)

    submit_http = FakeHttpClient(
        (
            response(
                "https://example.test/a",
                '<html><form method="post" action="/submit"><input name="q"></form></html>',
            ),
            ValueError("submit boom"),
        )
    )
    submit_session = make_session(submit_http, FakeTerminal())
    submit_session.open("https://example.test/a", 40)
    with pytest.raises(ValueError, match="submit boom"):
        submit_session.submit(1, {"q": "x"}, 40)


def test_back_and_forward_perform_fresh_fetch() -> None:
    http_client = FakeHttpClient(
        (
            response("https://example.test/a", "<html><title>A one</title></html>"),
            response("https://example.test/b", "<html><title>B one</title></html>"),
            response("https://example.test/a", "<html><title>A two</title></html>"),
            response("https://example.test/b", "<html><title>B two</title></html>"),
        )
    )
    session = make_session(http_client, FakeTerminal())
    session.open("https://example.test/a", 40)
    session.open("https://example.test/b", 40)

    back_page = session.back(40)
    forward_page = session.forward(40)

    assert back_page.title == "A two"
    assert forward_page.title == "B two"
    assert [request.url for request in http_client.requests] == [
        "https://example.test/a",
        "https://example.test/b",
        "https://example.test/a",
        "https://example.test/b",
    ]


def test_post_history_replayed_as_get_with_notice() -> None:
    form_page = response(
        "https://example.test/a",
        '<html><form method="post" action="/first"><input name="q" value="x"></form></html>',
    )
    http_client = FakeHttpClient(
        (
            form_page,
            response("https://example.test/first", "<html><title>POST target</title></html>"),
            response("https://example.test/c", "<html><title>C</title></html>"),
            response("https://example.test/first", "<html><title>Replayed</title></html>"),
        )
    )
    session = make_session(http_client, FakeTerminal())
    session.open("https://example.test/a", 40)
    session.submit(1, {"q": "x"}, 40)
    session.open("https://example.test/c", 40)

    replayed = session.back(40)

    assert http_client.requests[-1].method == "GET"
    assert http_client.requests[-1].body == b""
    assert replayed.url == "https://example.test/first"
    assert any("POST" in notice and "GET" in notice for notice in replayed.notices)


def test_submit_truncates_forward_and_uses_new_deadline() -> None:
    form = '<html><form method="post" action="/submit"><input name="q" value="x"></form></html>'
    http_client = FakeHttpClient(
        (
            response("https://example.test/a", form),
            response("https://example.test/b", form),
            response("https://example.test/a", form),
            response("https://example.test/submit", "<html><title>Submitted</title></html>"),
        )
    )
    terminal = FakeTerminal()
    clock = FakeClock(0.0, 100.0)
    session = BrowserSessionImpl(
        limits=Limits.defaults(),
        clock=clock,
        http_client=http_client,
        tree_builder=TreeBuilderImpl(),
        layout_engine=LayoutEngineImpl(),
        terminal=terminal,
    )
    session.open("https://example.test/a", 40)
    session.open("https://example.test/b", 40)
    session.back(40)
    clock.advance(10.0)

    submitted = session.submit(1, {"q": "value"}, 40)

    assert submitted.title == "Submitted"
    assert session.history() == ("https://example.test/a", "https://example.test/submit")
    assert http_client.deadlines[0] == 60.0
    assert http_client.deadlines[-1] == 70.0
    assert http_client.requests[-1].method == "POST"
    assert http_client.requests[-1].body == b"q=value"
