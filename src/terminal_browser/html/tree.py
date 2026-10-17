from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from typing import Literal, Protocol, cast

from pydantic import BaseModel, ConfigDict

from ..core.errors import InvalidUrlError, TokenLimitError, UnsupportedSchemeError
from ..core.limits import Limits
from ..core.sanitize import sanitize_attribute, sanitize_text
from .entities import EntityDecoder
from .tokenizer import Token, Tokenizer, TokenizerImpl
from ..url import ParsedUrl, UrlParser, UrlParserImpl


@dataclass(slots=True)
class BuilderNode:
    kind: Literal["element", "text"]
    tag: str
    attrs: dict[str, str]
    text: str
    children: list[BuilderNode]


class Node(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    kind: Literal["element", "text"]
    tag: str
    attrs: tuple[tuple[str, str], ...]
    text: str
    children: tuple[Node, ...]


class Link(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    index: int
    href: str
    text: str


class Document(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    url: str
    title: str
    root: Node
    node_count: int
    truncated: bool
    truncation_reason: Literal["tokens", "nodes", "depth", None]


class TreeBuilder(Protocol):
    def parse(self, url: str, source: str, limits: Limits) -> Document: ...


@dataclass(slots=True)
class _AnchorState:
    node: BuilderNode
    href: str | None
    text_parts: list[str]
    pending_link: int | None
    unsupported_scheme: str | None


@dataclass(slots=True)
class _BuildState:
    limits: Limits
    stack: list[BuilderNode]
    anchors: list[_AnchorState]
    pending_links: list[tuple[int, str, list[str]]]
    node_count: int


_SUPPORTED_TAGS = frozenset(
    {
        "a",
        "article",
        "aside",
        "blockquote",
        "body",
        "br",
        "button",
        "caption",
        "code",
        "dd",
        "div",
        "dl",
        "dt",
        "em",
        "b",
        "i",
        "u",
        "strong",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "head",
        "header",
        "hr",
        "html",
        "img",
        "input",
        "label",
        "li",
        "main",
        "nav",
        "ol",
        "option",
        "p",
        "pre",
        "section",
        "select",
        "span",
        "table",
        "tbody",
        "td",
        "textarea",
        "tfoot",
        "th",
        "thead",
        "tr",
        "ul",
    }
)
_RETAINED_ATTRIBUTES: dict[str, frozenset[str]] = {
    "a": frozenset({"href"}),
    "img": frozenset({"alt"}),
    "form": frozenset({"action", "method"}),
    "input": frozenset(
        {"type", "name", "value", "checked", "disabled", "required", "placeholder", "aria-label"}
    ),
    "select": frozenset({"name", "disabled", "required", "multiple", "aria-label"}),
    "option": frozenset({"value", "selected", "disabled"}),
    "textarea": frozenset({"name", "disabled", "required", "placeholder", "aria-label"}),
    "button": frozenset({"type", "name", "value", "disabled", "required"}),
    "label": frozenset({"for"}),
    "base": frozenset({"href"}),
    "meta": frozenset({"charset", "content"}),
}
_VOID_ELEMENTS = frozenset({"br", "hr", "img", "input", "meta", "link", "wbr", "base"})
_DROPPED_VOID_ELEMENTS = frozenset({"meta", "link", "wbr", "base"})
_BLOCK_ELEMENTS = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "div",
        "dl",
        "fieldset",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "dd",
        "dt",
        "td",
        "th",
        "tr",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "ul",
    }
)


class TreeBuilderImpl:
    def __init__(
        self,
        tokenizer: Tokenizer | None = None,
        url_parser: UrlParser | None = None,
        entity_decoder: EntityDecoder | None = None,
    ) -> None:
        self._tokenizer = tokenizer or TokenizerImpl()
        self._url_parser = url_parser
        self._entity_decoder = entity_decoder
        self.links: list[Link] = []

    def parse(self, url: str, source: str, limits: Limits) -> Document:
        parser = self._url_parser or UrlParserImpl(limits)
        document_url = parser.parse(url)
        decoder = self._entity_decoder or EntityDecoder(limits)
        base_url = _find_base_url(document_url, source, parser, decoder)
        root = BuilderNode("element", "#document", {}, "", [])
        state = _BuildState(limits, [root], [], [], 1)
        title_parts: list[str] = []
        in_title = False
        truncated = False
        truncation_reason: Literal["tokens", "nodes", "depth", None] = None
        suppressed_tables = 0
        suppressed_raw_tag: str | None = None
        stop = False
        token_stream = cast(
            Generator[Token, None, None],
            self._tokenizer.tokenize(source, limits),
        )
        try:
            for token in token_stream:
                if suppressed_raw_tag is not None:
                    if token.kind == "end" and token.name == suppressed_raw_tag:
                        suppressed_raw_tag = None
                    continue
                if suppressed_tables > 0:
                    if token.kind == "start" and token.name == "table":
                        suppressed_tables += 1
                    elif token.kind == "end" and token.name == "table":
                        suppressed_tables -= 1
                    elif token.kind == "text" and token.data:
                        text = sanitize_text(token.data)
                        for anchor in state.anchors:
                            anchor.text_parts.append(text)
                        if not self._append_text(
                            state,
                            state.stack[-1],
                            text,
                        ):
                            truncated = True
                            truncation_reason = "nodes"
                            stop = True
                            break
                    continue
                if token.kind == "text":
                    if in_title:
                        title_parts.append(sanitize_text(token.data))
                    else:
                        text = sanitize_text(token.data)
                        if text:
                            for anchor in state.anchors:
                                anchor.text_parts.append(text)
                            if not self._append_text(state, state.stack[-1], text):
                                truncated = True
                                truncation_reason = "nodes"
                                stop = True
                                break
                    continue
                if token.kind == "start":
                    tag = token.name
                    if tag == "table" and any(node.tag == "table" for node in state.stack):
                        suppressed_tables = 1
                        continue
                    if tag == "title":
                        in_title = True
                        continue
                    if tag in {"script", "style"}:
                        suppressed_raw_tag = tag
                        continue
                    if tag in _DROPPED_VOID_ELEMENTS:
                        continue
                    if tag not in _SUPPORTED_TAGS:
                        continue
                    self._apply_implied_ends(state, tag)
                    if len(state.stack) + 1 > limits.max_dom_depth:
                        truncated = True
                        truncation_reason = "depth"
                        stop = True
                        break
                    attrs = _sanitized_attributes(tag, token.attrs)
                    node = BuilderNode("element", tag, attrs, "", [])
                    if not self._append_node(state, state.stack[-1], node):
                        truncated = True
                        truncation_reason = "nodes"
                        stop = True
                        break
                    if tag == "a":
                        anchor = self._start_anchor(state, node, attrs, base_url, parser)
                        state.anchors.append(anchor)
                    if tag not in _VOID_ELEMENTS:
                        state.stack.append(node)
                    continue
                if token.kind == "end":
                    tag = token.name
                    if in_title and tag == "title":
                        in_title = False
                        continue
                    if tag in _SUPPORTED_TAGS and tag not in {"title", "script", "style"}:
                        self._close_to_tag(state, tag)
                    continue
        except TokenLimitError:
            truncated = True
            truncation_reason = "tokens"
        finally:
            token_stream.close()
        while state.anchors:
            self._finish_anchor(state, state.anchors.pop())
        title = sanitize_text("".join(title_parts)).strip()
        self.links = [
            Link(
                index=index,
                href=href,
                text=sanitize_text("".join(parts)).strip() or href,
            )
            for index, href, parts in state.pending_links
        ]
        return Document(
            url=url,
            title=title,
            root=_freeze(root),
            node_count=state.node_count,
            truncated=truncated,
            truncation_reason=truncation_reason,
        )

    def _append_text(
        self,
        state: _BuildState,
        parent: BuilderNode,
        text: str,
    ) -> bool:
        if not text:
            return True
        return self._append_node(state, parent, BuilderNode("text", "", {}, text, []))

    def _append_node(
        self,
        state: _BuildState,
        parent: BuilderNode,
        node: BuilderNode,
    ) -> bool:
        if state.node_count >= state.limits.max_nodes:
            return False
        parent.children.append(node)
        state.node_count += 1
        return True

    def _start_anchor(
        self,
        state: _BuildState,
        node: BuilderNode,
        attrs: dict[str, str],
        base_url: ParsedUrl,
        parser: UrlParser,
    ) -> _AnchorState:
        href = attrs.get("href")
        if href is None:
            return _AnchorState(node, None, [], None, None)
        scheme = parser.scheme_of(href)
        if scheme not in {"", "http", "https"}:
            return _AnchorState(node, href, [], None, scheme)
        try:
            target = parser.resolve(base_url, href)
        except (InvalidUrlError, UnsupportedSchemeError):
            return _AnchorState(node, href, [], None, None)
        index = len(state.pending_links) + 1
        node.attrs["href"] = target.normalized_url
        state.pending_links.append((index, target.normalized_url, []))
        return _AnchorState(node, href, [], index, None)

    def _finish_anchor(self, state: _BuildState, anchor: _AnchorState) -> None:
        if anchor.pending_link is not None:
            index = anchor.pending_link - 1
            state.pending_links[index] = (
                anchor.pending_link,
                state.pending_links[index][1],
                anchor.text_parts,
            )
        if anchor.unsupported_scheme is not None:
            visible = sanitize_text("".join(anchor.text_parts)).strip()
            fallback = visible or anchor.href or ""
            suffix = f" [unsupported: {anchor.unsupported_scheme}]"
            self._append_text(state, anchor.node, fallback + suffix)

    def _finish_anchor_for_node(
        self,
        state: _BuildState,
        node: BuilderNode,
    ) -> None:
        for index in range(len(state.anchors) - 1, -1, -1):
            if state.anchors[index].node is node:
                self._finish_anchor(state, state.anchors.pop(index))
                return

    def _close_to_tag(self, state: _BuildState, tag: str) -> None:
        for index in range(len(state.stack) - 1, 0, -1):
            if state.stack[index].tag == tag:
                self._pop_through(state, index)
                return

    def _pop_through(self, state: _BuildState, index: int) -> None:
        while len(state.stack) > index:
            node = state.stack.pop()
            self._finish_anchor_for_node(state, node)

    def _apply_implied_ends(self, state: _BuildState, tag: str) -> None:
        if tag in _BLOCK_ELEMENTS:
            self._close_unscoped(state, "p")
        if tag == "li":
            self._close_scoped(state, {"li"}, {"ul", "ol"})
        if tag in {"dt", "dd"}:
            self._close_scoped(state, {"dt", "dd"}, {"dl"})
        if tag == "tr":
            self._close_scoped(state, {"tr"}, {"table", "tbody", "thead", "tfoot"})
        if tag in {"td", "th"}:
            self._close_scoped(state, {"td", "th"}, {"tr"})

    def _close_unscoped(self, state: _BuildState, tag: str) -> None:
        for index in range(len(state.stack) - 1, 0, -1):
            if state.stack[index].tag == tag:
                self._pop_through(state, index)
                return

    def _close_scoped(
        self,
        state: _BuildState,
        targets: set[str],
        scopes: set[str],
    ) -> None:
        for index in range(len(state.stack) - 1, 0, -1):
            tag = state.stack[index].tag
            if tag in targets:
                self._pop_through(state, index)
                return
            if tag in scopes:
                return


def _sanitized_attributes(tag: str, attrs: dict[str, str]) -> dict[str, str]:
    retained = _RETAINED_ATTRIBUTES.get(tag, frozenset())
    return {
        name: sanitize_attribute(value)
        for name, value in attrs.items()
        if name.lower() in retained
    }


def _find_base_url(
    document_url: ParsedUrl,
    source: str,
    parser: UrlParser,
    decoder: EntityDecoder,
) -> ParsedUrl:
    lower_source = source.lower()
    position = 0
    while True:
        position = lower_source.find("<base", position)
        if position < 0:
            return document_url
        name_end = position + 5
        if name_end < len(source) and source[name_end] not in " \t\n\f\r/>":
            position = name_end
            continue
        tag_end = _find_tag_end(source, position)
        if tag_end < 0:
            position = name_end
            continue
        href = _scan_href(source[position + 5 : tag_end], decoder)
        if href:
            try:
                candidate = parser.resolve(document_url, href)
            except (InvalidUrlError, UnsupportedSchemeError):
                candidate = None
            if candidate is not None:
                return candidate
        position = tag_end + 1


def _find_tag_end(source: str, start: int) -> int:
    quote = ""
    for index in range(start, len(source)):
        character = source[index]
        if quote:
            if character == quote:
                quote = ""
        elif character in "'\"":
            quote = character
        elif character == ">":
            return index
    return -1


def _scan_href(tag_body: str, decoder: EntityDecoder) -> str | None:
    index = 0
    while index < len(tag_body):
        while index < len(tag_body) and tag_body[index] in " \t\n\f\r/":
            index += 1
        name_start = index
        while index < len(tag_body) and tag_body[index] not in " \t\n\f\r/=":
            index += 1
        if name_start == index:
            index += 1
            continue
        name = tag_body[name_start:index].lower()
        while index < len(tag_body) and tag_body[index] in " \t\n\f\r":
            index += 1
        if name != "href" or index >= len(tag_body) or tag_body[index] != "=":
            continue
        index += 1
        while index < len(tag_body) and tag_body[index] in " \t\n\f\r":
            index += 1
        if index >= len(tag_body):
            return None
        if tag_body[index] in "'\"":
            quote = tag_body[index]
            index += 1
            value_start = index
            while index < len(tag_body) and tag_body[index] != quote:
                index += 1
            if index >= len(tag_body):
                return None
            value = tag_body[value_start:index]
        else:
            value_start = index
            while index < len(tag_body) and tag_body[index] not in " \t\n\f\r>":
                index += 1
            value = tag_body[value_start:index]
        return sanitize_attribute(decoder.decode_attribute(value)) or None
    return None


def _freeze(node: BuilderNode) -> Node:
    return Node(
        kind=node.kind,
        tag=node.tag,
        attrs=tuple(node.attrs.items()),
        text=node.text,
        children=tuple(_freeze(child) for child in node.children),
    )
