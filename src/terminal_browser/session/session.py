from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from ..core.clock import Clock
from ..core.encoding import decode_body
from ..core.errors import (
    BrowserError,
    FormError,
    InvalidNavigationError,
    NavigationTimeoutError,
)
from ..core.limits import Limits
from ..core.sanitize import sanitize_text
from ..forms import FormSpec, extract_forms, serialize_form
from ..html.tree import Document, Node, TreeBuilder
from ..net.cache import Cache
from ..net.http import HttpClient, HttpRequest, HttpResponse
from ..render.layout import LayoutEngine, Link, RenderedPage
from ..term.output import Terminal, WriteRequest


class PageView(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    url: str
    status: int
    title: str
    lines: tuple[str, ...]
    links: list[Link]
    forms: tuple[FormSpec, ...]
    from_cache: bool
    notices: tuple[str, ...]


class SessionEvent(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    kind: Literal["navigated", "error", "notice"]
    message: str
    url: str | None


class BrowserSession(Protocol):
    def open(self, url: str, width: int) -> PageView: ...
    def follow(self, n: int, width: int) -> PageView: ...
    def back(self, width: int) -> PageView: ...
    def forward(self, width: int) -> PageView: ...
    def submit(
        self,
        form_index: int,
        field_values: dict[str, str],
        width: int,
    ) -> PageView: ...
    def current(self) -> PageView | None: ...
    def history(self) -> tuple[str, ...]: ...
    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class _HistoryEntry:
    url: str
    method: Literal["GET", "POST"]


@dataclass(frozen=True, slots=True)
class _BuiltPage:
    page: PageView
    write_width: int


class BrowserSessionImpl:
    def __init__(
        self,
        limits: Limits,
        clock: Clock,
        http_client: HttpClient,
        tree_builder: TreeBuilder,
        layout_engine: LayoutEngine,
        terminal: Terminal,
        cache: Cache | None = None,
    ) -> None:
        self._limits = limits
        self._clock = clock
        self._http_client = http_client
        self._tree_builder = tree_builder
        self._layout_engine = layout_engine
        self._terminal = terminal
        self._cache = cache
        self._history: list[_HistoryEntry] = []
        self._pointer: int | None = None
        self._current: PageView | None = None

    def open(self, url: str, width: int) -> PageView:
        request = _request("GET", url)
        return self._navigate(request, url, width, "GET", None, ())

    def follow(self, n: int, width: int) -> PageView:
        page = self._require_current()
        if n <= 0 or n > len(page.links):
            raise InvalidNavigationError("link index is out of range")
        target = page.links[n - 1].href
        request = _request("GET", target)
        return self._navigate(request, target, width, "GET", None, ())

    def back(self, width: int) -> PageView:
        index = self._traversal_index(-1)
        entry = self._history[index]
        notices = (
            ("[notice] history POST entry replayed as GET",)
            if entry.method == "POST"
            else ()
        )
        request = _request("GET", entry.url)
        return self._navigate(
            request,
            entry.url,
            width,
            "GET",
            index,
            notices,
        )

    def forward(self, width: int) -> PageView:
        index = self._traversal_index(1)
        entry = self._history[index]
        notices = (
            ("[notice] history POST entry replayed as GET",)
            if entry.method == "POST"
            else ()
        )
        request = _request("GET", entry.url)
        return self._navigate(
            request,
            entry.url,
            width,
            "GET",
            index,
            notices,
        )

    def submit(
        self,
        form_index: int,
        field_values: dict[str, str],
        width: int,
    ) -> PageView:
        if self._current is None:
            return self._error_page("", FormError("there is no current page"), width)
        page = self._current
        attempted_url = page.url
        try:
            if form_index <= 0 or form_index > len(page.forms):
                raise FormError("form index is out of range")
            form = page.forms[form_index - 1]
            target, body = serialize_form(form, field_values, self._limits)
            content_type = (
                "application/x-www-form-urlencoded"
                if form.method == "POST"
                else None
            )
            request = HttpRequest(
                method=form.method,
                url=target,
                headers=(),
                body=body,
                content_type=content_type,
            )
        except BrowserError as error:
            return self._error_page(attempted_url, error, width)
        return self._navigate(
            request,
            attempted_url,
            width,
            form.method,
            None,
            (),
        )

    def current(self) -> PageView | None:
        if self._current is None:
            return None
        return self._copy_page(self._current)

    def history(self) -> tuple[str, ...]:
        return tuple(entry.url for entry in self._history)

    def close(self) -> None:
        if self._cache is not None:
            self._cache.close()

    def _navigate(
        self,
        request: HttpRequest,
        attempted_url: str,
        width: int,
        history_method: Literal["GET", "POST"],
        traversal_index: int | None,
        extra_notices: tuple[str, ...],
    ) -> PageView:
        deadline = self._clock.now_monotonic() + self._limits.navigation_timeout_sec
        try:
            self._check_deadline(deadline)
            response = self._http_client.request(request, deadline)
            self._check_deadline(deadline)
            built = self._build_page(response, width, extra_notices, deadline)
            self._check_deadline(deadline)
            self._write_page(built.page, built.write_width, deadline)
            self._check_deadline(deadline)
            if traversal_index is None:
                self._commit_new(built.page, history_method)
            else:
                self._commit_traversal(built.page, traversal_index)
            return built.page
        except BrowserError as error:
            return self._error_page(attempted_url, error, width)

    def _build_page(
        self,
        response: HttpResponse,
        width: int,
        extra_notices: tuple[str, ...],
        deadline: float,
    ) -> _BuiltPage:
        notices = [_one_line(notice) for notice in response.notices]
        media_type = _media_type(response)
        if response.status in {204, 205, 304}:
            return _BuiltPage(
                page=PageView(
                    url=_one_line(response.url),
                    status=response.status,
                    title="",
                    lines=(),
                    links=[],
                    forms=(),
                    from_cache=response.from_cache,
                    notices=tuple((*notices, *(_one_line(note) for note in extra_notices))),
                ),
                write_width=self._effective_width(width),
            )
        if media_type == "text/html":
            decoded = decode_body(
                response.body,
                _content_type_header(response),
                self._limits,
            )
            self._check_deadline(deadline)
            document = self._tree_builder.parse(response.url, decoded, self._limits)
            self._check_deadline(deadline)
            forms = extract_forms(document.root, document.url, self._limits)
            self._check_deadline(deadline)
            rendered = self._layout_engine.render(document, width)
            self._check_deadline(deadline)
            return self._rendered_page(response, rendered, forms, notices, extra_notices)
        if media_type == "text/plain":
            decoded = decode_body(
                response.body,
                _content_type_header(response),
                self._limits,
            )
            self._check_deadline(deadline)
            document = _plain_document(response.url, decoded)
            self._check_deadline(deadline)
            rendered = self._layout_engine.render(document, width)
            self._check_deadline(deadline)
            return self._rendered_page(response, rendered, (), notices, extra_notices)
        if not any("unsupported content type" in notice for notice in notices):
            label = media_type or "<missing>"
            notices.append(f"[notice] unsupported content type: {label}")
        return _BuiltPage(
            page=PageView(
                url=_one_line(response.url),
                status=response.status,
                title="",
                lines=(),
                links=[],
                forms=(),
                from_cache=response.from_cache,
                notices=tuple((*notices, *(_one_line(note) for note in extra_notices))),
            ),
            write_width=self._effective_width(width),
        )

    def _rendered_page(
        self,
        response: HttpResponse,
        rendered: RenderedPage,
        forms: tuple[FormSpec, ...],
        notices: list[str],
        extra_notices: tuple[str, ...],
    ) -> _BuiltPage:
        return _BuiltPage(
            page=PageView(
                url=_one_line(response.url),
                status=response.status,
                title=_one_line(rendered.title),
                lines=tuple(_one_line(line.text) for line in rendered.lines),
                links=list(rendered.links),
                forms=forms,
                from_cache=response.from_cache,
                notices=tuple((*notices, *(_one_line(note) for note in extra_notices))),
            ),
            write_width=rendered.width,
        )

    def _write_page(self, page: PageView, write_width: int, deadline: float) -> None:
        self._check_deadline(deadline)
        self._terminal.write(
            WriteRequest(
                lines=(*page.lines, *page.notices),
                width=write_width,
                stream="stdout",
            )
        )

    def _error_page(self, attempted_url: str, error: BrowserError, width: int) -> PageView:
        detail = _one_line(str(error)) or type(error).__name__
        page = PageView(
            url=_one_line(attempted_url),
            status=0,
            title="",
            lines=(),
            links=[],
            forms=(),
            from_cache=False,
            notices=(detail,),
        )
        self._terminal.write(
            WriteRequest(
                lines=page.notices,
                width=self._effective_width(width),
                stream="stderr",
            )
        )
        return page

    def _commit_new(self, page: PageView, method: Literal["GET", "POST"]) -> None:
        if self._pointer is not None:
            del self._history[self._pointer + 1 :]
        self._history.append(_HistoryEntry(page.url, method))
        if len(self._history) > self._limits.max_history:
            del self._history[: len(self._history) - self._limits.max_history]
        self._pointer = len(self._history) - 1
        self._current = self._copy_page(page)

    def _commit_traversal(self, page: PageView, index: int) -> None:
        entry = self._history[index]
        self._history[index] = _HistoryEntry(page.url, entry.method)
        self._pointer = index
        self._current = self._copy_page(page)

    def _traversal_index(self, direction: Literal[-1, 1]) -> int:
        if self._pointer is None or self._current is None:
            raise InvalidNavigationError("history is empty")
        index = self._pointer + direction
        if index < 0 or index >= len(self._history):
            raise InvalidNavigationError("history transition is at a boundary")
        return index

    def _require_current(self) -> PageView:
        if self._current is None:
            raise InvalidNavigationError("there is no current page")
        return self._current

    def _check_deadline(self, deadline: float) -> None:
        if self._clock.now_monotonic() >= deadline:
            raise NavigationTimeoutError("navigation deadline exhausted")

    def _effective_width(self, width: int) -> int:
        return max(
            self._limits.min_layout_width,
            min(width, self._limits.max_line_width),
        )

    def _copy_page(self, page: PageView) -> PageView:
        return PageView(
            url=page.url,
            status=page.status,
            title=page.title,
            lines=page.lines,
            links=list(page.links),
            forms=page.forms,
            from_cache=page.from_cache,
            notices=page.notices,
        )


Session = BrowserSessionImpl


def _request(method: Literal["GET", "POST"], url: str) -> HttpRequest:
    return HttpRequest(
        method=method,
        url=url,
        headers=(),
        body=b"",
        content_type=None,
    )


def _media_type(response: HttpResponse) -> str:
    content_type = _content_type_header(response)
    return content_type.split(";", 1)[0].strip().lower() if content_type else ""


def _content_type_header(response: HttpResponse) -> str | None:
    for name, value in response.headers:
        if name.lower() == "content-type":
            return value
    return None


def _plain_document(url: str, text: str) -> Document:
    pre = Node(
        kind="element",
        tag="pre",
        attrs=(),
        text="",
        children=(
            Node(kind="text", tag="", attrs=(), text=sanitize_text(text), children=()),
        ),
    )
    root = Node(kind="element", tag="body", attrs=(), text="", children=(pre,))
    return Document(
        url=_one_line(url),
        title="",
        root=root,
        node_count=3,
        truncated=False,
        truncation_reason=None,
    )


def _one_line(text: str) -> str:
    return sanitize_text(text).replace("\n", " ").replace("\t", " ")
