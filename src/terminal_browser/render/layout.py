from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from ..core.errors import RenderError
from ..core.limits import Limits
from ..core.text import display_width
from ..html.tree import Document, Node


RenderedLineKind = Literal[
    "heading",
    "para",
    "item",
    "pre",
    "rule",
    "table",
    "blank",
    "form",
    "notice",
]
TruncationReason = Literal["T", "N", "D", "R", "P"]


class RenderedLine(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    text: str
    kind: RenderedLineKind


class Link(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    href: str
    text: str
    index: int


class RenderedPage(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    url: str
    title: str
    lines: tuple[RenderedLine, ...]
    links: list[Link]
    width: int
    truncated: bool
    truncation_reasons: tuple[TruncationReason, ...]


class LayoutEngine(Protocol):
    def render(self, document: Document, width: int) -> RenderedPage: ...


@dataclass(slots=True)
class _RenderState:
    width: int
    limits: Limits
    links: list[Link]
    pre_cut: bool = False


_BLOCK_TAGS = frozenset(
    {
        "p",
        "div",
        "section",
        "article",
        "header",
        "footer",
        "main",
        "nav",
        "aside",
        "blockquote",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "ul",
        "ol",
        "dl",
        "pre",
        "table",
        "hr",
        "form",
    }
)
_HEADING_LEVELS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}


class LayoutEngineImpl:
    def render(self, document: Document, width: int) -> RenderedPage:
        effective_width = max(
            document_limits(document).min_layout_width,
            min(width, document_limits(document).max_line_width),
        )
        state = _RenderState(effective_width, document_limits(document), [])
        content: list[RenderedLine] = []
        if document.title:
            title_lines = _wrap_text(document.title, effective_width, "heading")
            _append_block(content, title_lines)
        for child in document.root.children:
            if child.kind != "element":
                continue
            block = _render_block(child, state)
            _append_block(content, block)
        reasons: set[TruncationReason] = set()
        if document.truncated:
            if document.truncation_reason == "tokens":
                reasons.add("T")
            elif document.truncation_reason == "nodes":
                reasons.add("N")
            elif document.truncation_reason == "depth":
                reasons.add("D")
        if state.pre_cut:
            reasons.add("P")
        if len(content) > state.limits.max_render_lines:
            reasons.add("R")
        if reasons:
            notice_lines = _notice_lines(reasons, state.width)
            available = state.limits.max_render_lines - len(notice_lines)
            if available < 0:
                raise RenderError("render limit cannot reserve truncation notice")
            if len(content) > available:
                content = content[:available]
                reasons.add("R")
                notice_lines = _notice_lines(reasons, state.width)
                available = state.limits.max_render_lines - len(notice_lines)
                if available < 0:
                    raise RenderError("render limit cannot reserve truncation notice")
                content = content[:available]
            content.extend(notice_lines)
        return RenderedPage(
            url=document.url,
            title=document.title,
            lines=tuple(content),
            links=state.links,
            width=effective_width,
            truncated=bool(reasons),
            truncation_reasons=_ordered_reasons(reasons),
        )


def document_limits(document: Document) -> Limits:
    return Limits.defaults()


def _render_block(node: Node, state: _RenderState) -> list[RenderedLine]:
    tag = node.tag
    if tag in _HEADING_LEVELS:
        return _render_heading(node, state)
    if tag in {"ul", "ol"}:
        return _render_list(node, state, 0)
    if tag == "dl":
        return _render_definition_list(node, state)
    if tag == "pre":
        return _render_pre(node, state)
    if tag == "table":
        return _render_table(node, state)
    if tag == "form":
        return _render_form(node, state)
    if tag == "hr":
        return [RenderedLine(text="-" * state.width, kind="rule")]
    if tag == "img":
        alt = _attrs(node).get("alt", "[image]")
        return _wrap_text(alt or "[image]", state.width, "para")
    if tag in _BLOCK_TAGS or tag in {"body", "head", "html"}:
        return _render_container(node, state)
    text = _inline_text(node, state)
    return _wrap_text(text, state.width, "para")


def _render_container(node: Node, state: _RenderState) -> list[RenderedLine]:
    result: list[RenderedLine] = []
    for child in node.children:
        if child.kind == "text":
            result.extend(_wrap_text(_collapse(child.text), state.width, "para"))
        elif child.kind == "element":
            if child.tag in _BLOCK_TAGS:
                block = _render_block(child, state)
                _append_block(result, block)
            else:
                result.extend(_wrap_text(_inline_text(child, state), state.width, "para"))
    return result


def _render_heading(node: Node, state: _RenderState) -> list[RenderedLine]:
    level = _HEADING_LEVELS[node.tag]
    text = _inline_text(node, state)
    if level == 1:
        text = text.upper()
        lines = _wrap_text(text, state.width, "heading")
        underline_width = min(state.width, max(1, display_width(text)))
        lines.append(RenderedLine(text="=" * underline_width, kind="heading"))
        return lines
    prefix = "#" * (level - 1) + " "
    return _wrap_text(prefix + text, state.width, "heading")


def _render_list(node: Node, state: _RenderState, level: int) -> list[RenderedLine]:
    if level >= 8:
        level = 7
    result: list[RenderedLine] = []
    number = 1
    for child in node.children:
        if child.kind != "element" or child.tag != "li":
            continue
        text = _inline_text_without_lists(child, state)
        marker = "- " if node.tag == "ul" else f"{number}. "
        number += 1
        prefix = "  " * level + marker
        continuation = "  " * level + "  "
        result.extend(_wrap_prefixed(text, state.width, "item", prefix, continuation))
        for nested in child.children:
            if nested.kind == "element" and nested.tag in {"ul", "ol"}:
                nested_lines = _render_list(nested, state, level + 1)
                result.extend(nested_lines)
    return result


def _render_definition_list(node: Node, state: _RenderState) -> list[RenderedLine]:
    result: list[RenderedLine] = []
    for child in node.children:
        if child.kind != "element":
            continue
        text = _inline_text(child, state)
        if child.tag == "dt":
            result.extend(_wrap_text(text, state.width, "item"))
        elif child.tag == "dd":
            result.extend(_wrap_prefixed(text, state.width, "item", "    ", "    "))
    return result


def _render_pre(node: Node, state: _RenderState) -> list[RenderedLine]:
    result: list[RenderedLine] = []
    for source_line in _node_text(node).splitlines() or [""]:
        expanded = _expand_tabs(source_line)
        line, cut = _hard_cut(expanded, state.width)
        if cut:
            state.pre_cut = True
        result.append(RenderedLine(text=line.rstrip(" "), kind="pre"))
    return result


def _render_table(node: Node, state: _RenderState) -> list[RenderedLine]:
    rows: list[tuple[bool, list[str]]] = []
    for row in _walk_elements(node):
        if row.tag != "tr":
            continue
        cells = [
            _inline_text(cell, state)
            for cell in row.children
            if cell.kind == "element" and cell.tag in {"td", "th"}
        ]
        if cells:
            rows.append((any(cell.tag == "th" for cell in row.children if cell.kind == "element"), cells))
    result: list[RenderedLine] = []
    for _is_header, cells in rows:
        result.extend(_wrap_text(" | ".join(cells), state.width, "table"))
    return result


def _render_form(node: Node, state: _RenderState) -> list[RenderedLine]:
    result: list[RenderedLine] = []
    for control in _walk_elements(node):
        field_type = _form_control_type(control)
        if field_type is None:
            continue
        attrs = _attrs(control)
        name = attrs.get("name", "")
        if not name or "disabled" in attrs:
            continue
        label = attrs.get("aria-label", attrs.get("placeholder", name))
        if field_type == "password":
            value = "[password]"
        elif field_type == "hidden":
            value = "[hidden]"
        elif field_type == "textarea":
            value = _node_text(control)
        elif field_type == "select":
            value = " ".join(
                _inline_text(option, state)
                for option in _walk_elements(control)
                if option.tag == "option"
            )
        elif field_type in {"checkbox", "radio"}:
            value = "[x]" if "checked" in attrs else "[ ]"
        else:
            value = attrs.get("value", "")
        result.extend(
            _wrap_text(
                f"{label}: {name}={value}",
                state.width,
                "form",
            )
        )
    return result


def _form_control_type(node: Node) -> str | None:
    attrs = _attrs(node)
    if node.tag == "textarea":
        return "textarea"
    if node.tag == "select":
        return "select"
    if node.tag == "button":
        return "submit" if attrs.get("type", "").lower() == "submit" else None
    if node.tag != "input":
        return None
    input_type = attrs.get("type", "text").lower()
    if input_type in {"text", "password", "hidden", "checkbox", "radio", "submit"}:
        return input_type
    return None


def _inline_text(node: Node, state: _RenderState) -> str:
    parts: list[str] = []
    _collect_inline(node, parts, state)
    return "".join(parts)


def _inline_text_without_lists(node: Node, state: _RenderState) -> str:
    parts: list[str] = []
    _collect_inline_without_lists(node, parts, state)
    return "".join(parts)


def _collect_inline(node: Node, parts: list[str], state: _RenderState) -> None:
    if node.kind == "text":
        parts.append(node.text)
        return
    if node.tag == "br":
        parts.append("\n")
        return
    if node.tag == "a":
        start = len(parts)
        for child in node.children:
            _collect_inline(child, parts, state)
        href = _attrs(node).get("href")
        text = "".join(parts[start:]).strip(" ")
        if href is not None and href.startswith(("http://", "https://")):
            index = len(state.links) + 1
            state.links.append(Link(href=href, text=text or href, index=index))
            parts.append(f"[{index}]")
        return
    for child in node.children:
        _collect_inline(child, parts, state)


def _collect_inline_without_lists(node: Node, parts: list[str], state: _RenderState) -> None:
    if node.kind == "text":
        parts.append(node.text)
        return
    if node.tag in {"ul", "ol"}:
        return
    if node.tag == "a":
        start = len(parts)
        for child in node.children:
            _collect_inline_without_lists(child, parts, state)
        href = _attrs(node).get("href")
        text = "".join(parts[start:]).strip(" ")
        if href is not None and href.startswith(("http://", "https://")):
            index = len(state.links) + 1
            state.links.append(Link(href=href, text=text or href, index=index))
            parts.append(f"[{index}]")
        return
    for child in node.children:
        _collect_inline_without_lists(child, parts, state)


def _walk_elements(node: Node) -> Iterator[Node]:
    if node.kind == "element":
        yield node
    for child in node.children:
        if child.kind == "element":
            yield from _walk_elements(child)


def _attrs(node: Node) -> dict[str, str]:
    return dict(node.attrs)


def _node_text(node: Node) -> str:
    return "".join(
        child.text if child.kind == "text" else _node_text(child)
        for child in node.children
    )


def _collapse(text: str) -> str:
    normalized = "".join(" " if character in " \t\n\r\f" else character for character in text)
    while "  " in normalized:
        normalized = normalized.replace("  ", " ")
    return normalized.strip(" ")


def _wrap_text(text: str, width: int, kind: RenderedLineKind) -> list[RenderedLine]:
    if not text:
        return []
    result: list[RenderedLine] = []
    for paragraph in text.split("\n"):
        normalized = _collapse(paragraph)
        if not normalized:
            result.append(RenderedLine(text="", kind="blank"))
            continue
        current = ""
        for word in normalized.split(" "):
            if not current:
                current = word
            elif display_width(current + " " + word) <= width:
                current = current + " " + word
            else:
                result.append(RenderedLine(text=current.rstrip(" "), kind=kind))
                current = word
            while display_width(current) > width:
                head, current = _hard_cut(current, width)
                result.append(RenderedLine(text=head.rstrip(" "), kind=kind))
        if current:
            result.append(RenderedLine(text=current.rstrip(" "), kind=kind))
    return result


def _wrap_prefixed(
    text: str,
    width: int,
    kind: RenderedLineKind,
    prefix: str,
    continuation: str,
) -> list[RenderedLine]:
    normalized = _collapse(text)
    if not normalized:
        return []
    words = normalized.split(" ")
    result: list[RenderedLine] = []
    current = prefix
    first = True
    for word in words:
        candidate = prefix + word if first else current + " " + word
        first = False
        if display_width(candidate) <= width:
            current = candidate
            continue
        result.append(RenderedLine(text=current.rstrip(" "), kind=kind))
        current = continuation + word
        while display_width(current) > width:
            head, current = _hard_cut(current, width)
            result.append(RenderedLine(text=head.rstrip(" "), kind=kind))
    if current.strip(" "):
        result.append(RenderedLine(text=current.rstrip(" "), kind=kind))
    return result


def _hard_cut(text: str, width: int) -> tuple[str, str]:
    current = ""
    for character in text:
        character_width = display_width(character)
        if current and display_width(current) + character_width > width:
            return current, text[len(current) :]
        current += character
    return current, ""


def _expand_tabs(text: str) -> str:
    result: list[str] = []
    column = 0
    for character in text:
        if character == "\t":
            spaces = 8 - (column % 8)
            result.append(" " * spaces)
            column += spaces
        else:
            result.append(character)
            column += display_width(character)
    return "".join(result)


def _append_block(target: list[RenderedLine], block: list[RenderedLine]) -> None:
    if not block:
        return
    if target and target[-1].text != "":
        target.append(RenderedLine(text="", kind="blank"))
    target.extend(block)


def _notice_lines(reasons: set[TruncationReason], width: int) -> list[RenderedLine]:
    text = "[truncated: " + ",".join(_ordered_reasons(reasons)) + "]"
    return _wrap_text(text, width, "notice")


def _ordered_reasons(reasons: set[TruncationReason]) -> tuple[TruncationReason, ...]:
    order: tuple[TruncationReason, ...] = ("T", "N", "D", "R", "P")
    return tuple(reason for reason in order if reason in reasons)
