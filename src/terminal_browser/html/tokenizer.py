from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal, Protocol

from ..core.errors import TokenLimitError
from ..core.limits import Limits
from .entities import EntityDecoder


@dataclass(slots=True)
class Token:
    kind: Literal["start", "end", "text", "comment", "doctype", "eof"]
    name: str
    attrs: dict[str, str]
    data: str
    self_closing: bool


class Tokenizer(Protocol):
    def tokenize(self, source: str, limits: Limits) -> Iterator[Token]: ...


_VOID_ELEMENTS = frozenset({"br", "hr", "img", "input", "meta", "link", "wbr", "base"})
_RAW_TEXT_ELEMENTS = frozenset({"script", "style"})
_RCDATA_ELEMENTS = frozenset({"title", "textarea"})
_WHITESPACE = frozenset(" \t\n\f\r")


class TokenizerImpl:
    def tokenize(self, source: str, limits: Limits) -> Iterator[Token]:
        normalized = source.replace("\x00", "\ufffd")
        decoder = EntityDecoder(limits)
        token_count = 0

        def counted(token: Token | None) -> Iterator[Token]:
            nonlocal token_count
            if token is None:
                return
            token_count += 1
            if token_count > limits.max_tokens:
                raise TokenLimitError("token limit exceeded")
            yield token

        index = 0
        raw_text_tag: str | None = None
        rcdata_tag: str | None = None
        while index < len(normalized):
            if raw_text_tag is not None or rcdata_tag is not None:
                mode_tag = raw_text_tag if raw_text_tag is not None else rcdata_tag
                if mode_tag is None:
                    continue
                closing = _find_closing_tag(normalized, index, mode_tag)
                if closing < 0:
                    data = normalized[index:]
                    index = len(normalized)
                    if data:
                        decoded = decoder.decode_text(data) if rcdata_tag is not None else data
                        yield from counted(
                            Token(
                                kind="text",
                                name="",
                                attrs={},
                                data=decoded,
                                self_closing=False,
                            )
                        )
                    raw_text_tag = None
                    rcdata_tag = None
                    break
                data = normalized[index:closing]
                index = closing
                raw_text_tag = None
                rcdata_tag = None
                if data:
                    decoded = decoder.decode_text(data) if mode_tag in _RCDATA_ELEMENTS else data
                    yield from counted(
                        Token(
                            kind="text",
                            name="",
                            attrs={},
                            data=decoded,
                            self_closing=False,
                        )
                    )
                continue

            if normalized[index] != "<":
                next_markup = _find_next_markup(normalized, index + 1)
                end = len(normalized) if next_markup < 0 else next_markup
                data = decoder.decode_text(normalized[index:end])
                index = end
                if data:
                    yield from counted(
                        Token(
                            kind="text",
                            name="",
                            attrs={},
                            data=data,
                            self_closing=False,
                        )
                    )
                continue

            if normalized.startswith("<!--", index):
                index = _consume_comment(normalized, index)
                continue
            if normalized.startswith("<![CDATA[", index):
                index = _consume_bogus(normalized, index)
                continue
            if normalized.startswith("<?", index):
                index = _consume_bogus(normalized, index)
                continue
            if normalized.startswith("<!", index):
                index = _consume_bogus(normalized, index)
                continue
            if normalized.startswith("</", index):
                end_tag, next_index = _parse_end_tag(normalized, index)
                index = next_index
                if end_tag is not None:
                    yield from counted(end_tag)
                else:
                    yield from counted(
                        Token(
                            kind="text",
                            name="",
                            attrs={},
                            data="<",
                            self_closing=False,
                        )
                    )
                continue
            if index + 1 >= len(normalized) or not _is_tag_start(normalized[index + 1]):
                next_markup = _find_next_markup(normalized, index + 1)
                end = len(normalized) if next_markup < 0 else next_markup
                data = decoder.decode_text(normalized[index:end])
                index = end
                if data:
                    yield from counted(
                        Token(
                            kind="text",
                            name="",
                            attrs={},
                            data=data,
                            self_closing=False,
                        )
                    )
                continue
            start_token, next_index, unfinished = _parse_start_tag(
                normalized,
                index,
                decoder,
            )
            index = next_index
            if unfinished is not None:
                yield from counted(unfinished)
                break
            if start_token is None:
                continue
            yield from counted(start_token)
            if start_token.name in _RAW_TEXT_ELEMENTS:
                raw_text_tag = start_token.name
            elif start_token.name in _RCDATA_ELEMENTS:
                rcdata_tag = start_token.name
        yield from counted(
            Token(
                kind="eof",
                name="",
                attrs={},
                data="",
                self_closing=False,
            )
        )


TokenizerImplProtocol = TokenizerImpl


def _find_next_markup(source: str, start: int) -> int:
    position = source.find("<", start)
    while position >= 0:
        if _is_markup_start(source, position):
            return position
        position = source.find("<", position + 1)
    return -1


def _is_markup_start(source: str, index: int) -> bool:
    return (
        source.startswith("<!--", index)
        or source.startswith("<![CDATA[", index)
        or source.startswith("<?", index)
        or source.startswith("<!", index)
        or source.startswith("</", index)
        or (
            index + 1 < len(source)
            and _is_tag_start(source[index + 1])
        )
    )


def _is_tag_start(character: str) -> bool:
    return "a" <= character <= "z" or "A" <= character <= "Z"


def _is_tag_name_character(character: str) -> bool:
    return _is_tag_start(character) or "0" <= character <= "9" or character in "-_:."


def _consume_comment(source: str, start: int) -> int:
    comment_start = start + 4
    if source.startswith(">", comment_start):
        return comment_start + 1
    normal_end = source.find("-->", comment_start)
    special_end = source.find("--!>", comment_start)
    if special_end >= 0 and (normal_end < 0 or special_end < normal_end):
        return special_end + 4
    if normal_end < 0:
        return len(source)
    return normal_end + 3


def _consume_bogus(source: str, start: int) -> int:
    end = source.find(">", start)
    return len(source) if end < 0 else end + 1


def _find_closing_tag(source: str, start: int, tag: str) -> int:
    needle = "</" + tag
    lower_source = source.lower()
    position = lower_source.find(needle, start)
    while position >= 0:
        boundary = position + len(needle)
        if boundary == len(source) or source[boundary] in _WHITESPACE or source[boundary] in "/>":
            return position
        position = lower_source.find(needle, boundary)
    return -1


def _parse_end_tag(
    source: str,
    start: int,
) -> tuple[Token | None, int]:
    index = start + 2
    while index < len(source) and source[index] in _WHITESPACE:
        index += 1
    name_start = index
    while index < len(source) and _is_tag_name_character(source[index]):
        index += 1
    if name_start == index:
        return None, start + 1
    name = source[name_start:index].lower()
    while index < len(source) and source[index] != ">":
        index += 1
    if index < len(source):
        index += 1
    return (
        Token(
            kind="end",
            name=name,
            attrs={},
            data="",
            self_closing=False,
        ),
        index,
    )


def _parse_start_tag(
    source: str,
    start: int,
    decoder: EntityDecoder,
) -> tuple[Token | None, int, Token | None]:
    index = start + 1
    name_start = index
    while index < len(source) and _is_tag_name_character(source[index]):
        index += 1
    if name_start == index:
        return None, start + 1, None
    name = source[name_start:index].lower()
    attrs: dict[str, str] = {}
    self_closing = False
    finished = False
    while index < len(source):
        while index < len(source) and source[index] in _WHITESPACE:
            index += 1
        if index >= len(source):
            return None, len(source), _unfinished_text(source, start)
        if source[index] == ">":
            index += 1
            finished = True
            break
        if source.startswith("/>", index):
            self_closing = name in _VOID_ELEMENTS
            index += 2
            finished = True
            break
        if source[index] == "/":
            index += 1
            continue
        attribute_start = index
        while index < len(source) and (
            source[index] not in _WHITESPACE
            and source[index] not in "/>="
        ):
            index += 1
        if attribute_start == index:
            index += 1
            continue
        attribute_name = source[attribute_start:index].lower()
        while index < len(source) and source[index] in _WHITESPACE:
            index += 1
        value = ""
        if index < len(source) and source[index] == "=":
            index += 1
            while index < len(source) and source[index] in _WHITESPACE:
                index += 1
            if index < len(source) and source[index] in "'\"":
                quote = source[index]
                index += 1
                value_start = index
                while index < len(source) and source[index] != quote:
                    index += 1
                if index >= len(source):
                    return None, len(source), _unfinished_text(source, start)
                value = source[value_start:index]
                index += 1
            else:
                value_start = index
                while index < len(source) and source[index] not in _WHITESPACE and source[index] != ">":
                    index += 1
                value = source[value_start:index]
        if attribute_name not in attrs:
            attrs[attribute_name] = decoder.decode_attribute(value)
    if not finished:
        return None, len(source), _unfinished_text(source, start)
    return (
        Token(
            kind="start",
            name=name,
            attrs=attrs,
            data="",
            self_closing=self_closing,
        ),
        index,
        None,
    )


def _unfinished_text(source: str, start: int) -> Token:
    return Token(
        kind="text",
        name="",
        attrs={},
        data=source[start:],
        self_closing=False,
    )
