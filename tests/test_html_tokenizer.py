import ast
from pathlib import Path

import pytest

from terminal_browser.core.errors import TokenLimitError
from terminal_browser.core.limits import Limits
from terminal_browser.html.tokenizer import Token, TokenizerImpl


LIMITS = Limits.defaults()


def make_limits(**overrides: int | float) -> Limits:
    values: dict[str, int | float] = {**LIMITS.model_dump(), **overrides}
    return Limits.model_validate(values)


def tokenize(source: str, limits: Limits = LIMITS) -> list[Token]:
    return list(TokenizerImpl().tokenize(source, limits))


def test_ast_import_boundaries() -> None:
    source_path = Path(__file__).parents[1] / "src" / "terminal_browser" / "html" / "tokenizer.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    allowed_stdlib = {"collections", "dataclasses", "typing"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name.split(".")[0] in allowed_stdlib for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                assert node.module is not None
                assert node.module.split(".")[0] in allowed_stdlib
            elif node.level == 1:
                assert node.module == "entities"
            else:
                assert node.level == 2
                assert node.module in {"core.errors", "core.limits"}


def test_token_generator_is_lazy() -> None:
    iterator = TokenizerImpl().tokenize("<a><b></b></a>", LIMITS)
    assert iter(iterator) is iterator
    assert next(iterator).name == "a"
    assert next(iterator).name == "b"


def test_max_tokens_raises_token_limit_error() -> None:
    with pytest.raises(TokenLimitError):
        tokenize(
            "<a>" * 100,
            make_limits(
                max_tokens=100,
                max_nodes=99,
                max_form_fields=10,
                max_repl_tokens=10,
            ),
        )


def test_rcdata_decodes_entities() -> None:
    tokens = tokenize("<title>&amp;</title><textarea>&lt;</textarea>")
    assert [(token.kind, token.name, token.data) for token in tokens] == [
        ("start", "title", ""),
        ("text", "", "&"),
        ("end", "title", ""),
        ("start", "textarea", ""),
        ("text", "", "<"),
        ("end", "textarea", ""),
        ("eof", "", ""),
    ]


def test_raw_text_does_not_decode_entities() -> None:
    tokens = tokenize("<script>&amp;</script><style>&lt;</style>")
    assert [(token.kind, token.name, token.data) for token in tokens] == [
        ("start", "script", ""),
        ("text", "", "&amp;"),
        ("end", "script", ""),
        ("start", "style", ""),
        ("text", "", "&lt;"),
        ("end", "style", ""),
        ("eof", "", ""),
    ]


def test_normal_text_decodes_entities() -> None:
    tokens = tokenize("A &amp; B")
    assert [(token.kind, token.data) for token in tokens] == [
        ("text", "A & B"),
        ("eof", ""),
    ]


def test_unterminated_raw_text_still_emits_eof() -> None:
    tokens = tokenize("<script>&amp;")
    assert [(token.kind, token.data) for token in tokens] == [
        ("start", ""),
        ("text", "&amp;"),
        ("eof", ""),
    ]


def test_void_elements_self_closing() -> None:
    tokens = tokenize("<br/><img/>")
    assert [token.self_closing for token in tokens if token.kind == "start"] == [True, True]
    assert [token.name for token in tokens if token.kind == "start"] == ["br", "img"]


def test_non_void_ignores_self_closing_slash() -> None:
    tokens = tokenize("<div/>")
    start = next(token for token in tokens if token.kind == "start")
    assert start.name == "div"
    assert start.self_closing is False


def test_comment_parsing_and_eof() -> None:
    tokens = tokenize("<!-- comment --><!--><!-- unterminated")
    assert [(token.kind, token.data) for token in tokens] == [("eof", "")]


def test_doctype_and_bogus_comments() -> None:
    tokens = tokenize("<!DOCTYPE html><?xml version='1'?><![CDATA[x]]>")
    assert [(token.kind, token.data) for token in tokens] == [("eof", "")]


def test_nul_replaced_with_fffd() -> None:
    tokens = tokenize("a\x00b<div data=\"x\x00\">\x00")
    assert tokens[0].data == "a\ufffdb"
    assert tokens[1].attrs == {"data": "x\ufffd"}
    assert tokens[2].data == "\ufffd"


def test_duplicate_attributes_first_wins() -> None:
    tokens = tokenize('<a href="1" href="2">')
    start = next(token for token in tokens if token.kind == "start")
    assert start.attrs == {"href": "1"}


def test_unterminated_start_tag_is_literal_text() -> None:
    tokens = tokenize('<div class=" unfinished')
    assert len(tokens) == 2
    assert tokens[0].kind == "text"
    assert tokens[0].data == '<div class=" unfinished'
    assert tokens[1].kind == "eof"
