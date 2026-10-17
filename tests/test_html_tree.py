import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from terminal_browser.core.limits import Limits
from terminal_browser.html.tree import Document, Node, TreeBuilderImpl


LIMITS = Limits.defaults()
URL = "https://example.test/dir/document.html"


def make_limits(**overrides: int | float) -> Limits:
    values: dict[str, int | float] = {**LIMITS.model_dump(), **overrides}
    return Limits.model_validate(values)


def element_children(node: Node) -> tuple[Node, ...]:
    return tuple(child for child in node.children if child.kind == "element")


def text_content(node: Node) -> str:
    return "".join(child.text for child in node.children if child.kind == "text")


def test_ast_import_boundaries() -> None:
    source_path = Path(__file__).parents[1] / "src" / "terminal_browser" / "html" / "tree.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    allowed_stdlib = {"__future__", "collections", "dataclasses", "typing", "pydantic"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name.split(".")[0] in allowed_stdlib for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                assert node.module is not None
                assert node.module.split(".")[0] in allowed_stdlib
            elif node.level == 1:
                assert node.module in {"entities", "tokenizer"}
            else:
                assert node.level == 2
                assert node.module in {"core.errors", "core.limits", "core.sanitize", "url"}


def test_base_href_prescan_resolves_links() -> None:
    builder = TreeBuilderImpl()
    document = builder.parse(
        URL,
        '<base href="javascript:bad"><base href="/root/"><a href="page">Page</a>',
        LIMITS,
    )
    assert document.title == ""
    assert len(builder.links) == 1
    assert builder.links[0].href == "https://example.test/root/page"
    assert builder.links[0].text == "Page"


def test_implied_end_tags_p_li_dt_dd_tr_td() -> None:
    builder = TreeBuilderImpl()
    document = builder.parse(
        URL,
        "<p>one<div>two</div><ul><li>first<li>second</ul>"
        "<dl><dt>term<dd>description</dl>"
        "<table><tr><td>cell<td>second</table>",
        LIMITS,
    )
    root_tags = [child.tag for child in element_children(document.root)]
    assert root_tags == ["p", "div", "ul", "dl", "table"]
    paragraph = element_children(document.root)[0]
    list_node = element_children(document.root)[2]
    assert [child.tag for child in element_children(list_node)] == ["li", "li"]
    description_list = element_children(document.root)[3]
    assert [child.tag for child in element_children(description_list)] == ["dt", "dd"]
    table = element_children(document.root)[4]
    row = element_children(table)[0]
    assert [child.tag for child in element_children(row)] == ["td", "td"]
    assert text_content(paragraph) == "one"


def test_mismatched_explicit_close_pops_unmatched() -> None:
    document = TreeBuilderImpl().parse(URL, "<b><i>text</b>tail", LIMITS)
    root_children = element_children(document.root)
    assert [child.tag for child in root_children] == ["b"]
    assert [child.tag for child in element_children(root_children[0])] == ["i"]
    assert text_content(element_children(root_children[0])[0]) == "text"


def test_nested_tables_flattened() -> None:
    document = TreeBuilderImpl().parse(
        URL,
        "<table><tr><td>outer<table><tr><td>inner</td></tr></table> tail</td></tr></table>",
        LIMITS,
    )
    table = element_children(document.root)[0]
    cell = element_children(element_children(table)[0])[0]
    assert not any(child.tag == "table" for child in cell.children)
    assert "inner" in text_content(cell)
    assert "tail" in text_content(cell)


def test_title_extracted_and_omitted_from_body() -> None:
    document = TreeBuilderImpl().parse(URL, "<title>Page &amp; Title</title><p>Body</p>", LIMITS)
    assert document.title == "Page & Title"
    assert not any(child.tag == "title" for child in document.root.children)
    assert [child.tag for child in element_children(document.root)] == ["p"]


def test_script_and_style_subtrees_are_dropped() -> None:
    document = TreeBuilderImpl().parse(
        URL,
        "<style>body{color:red}</style><script>alert('x')</script><p>visible</p>",
        LIMITS,
    )
    body = element_children(document.root)[0]
    assert body.tag == "p"
    assert text_content(body) == "visible"
    assert not any(child.tag in {"script", "style"} for child in document.root.children)


    builder = TreeBuilderImpl()
    document = builder.parse(
        URL,
        '<a href="/one">One</a><a href="javascript:alert(1)">Bad</a>',
        LIMITS,
    )
    assert len(builder.links) == 1
    assert builder.links[0].href == "https://example.test/one"
    anchors = element_children(document.root)
    assert len(anchors) == 2
    assert "[unsupported: javascript]" in text_content(anchors[1])


def test_token_limit_truncates_with_reason() -> None:
    limits = make_limits(
        max_tokens=100,
        max_nodes=100,
        max_form_fields=3,
        max_repl_tokens=3,
    )
    document = TreeBuilderImpl().parse(URL, "<div></div>" * 50, limits)
    assert document.truncated is True
    assert document.truncation_reason == "tokens"


def test_node_and_depth_limits_truncate_with_reason() -> None:
    node_limits = make_limits(
        max_nodes=3,
        max_tokens=100,
        max_dom_depth=2,
        max_form_fields=3,
        max_repl_tokens=3,
    )
    node_document = TreeBuilderImpl().parse(
        URL,
        "<div>one<!-- comment -->two</div>",
        node_limits,
    )
    assert node_document.truncated is True
    assert node_document.truncation_reason == "nodes"

    depth_limits = make_limits(max_dom_depth=2)
    depth_document = TreeBuilderImpl().parse(
        URL,
        "<div><span>text</span></div>",
        depth_limits,
    )
    assert depth_document.truncated is True
    assert depth_document.truncation_reason == "depth"


def test_construction_sanitizer_applied_to_text_and_attrs() -> None:
    document = TreeBuilderImpl().parse(
        URL,
        '<a href="x\ny">A\x1bB &amp;</a>',
        LIMITS,
    )
    anchor = element_children(document.root)[0]
    assert anchor.attrs == (("href", "https://example.test/dir/x%20y"),)
    assert text_content(anchor) == "AB &"


def test_tree_freezes_to_pydantic_models() -> None:
    document = TreeBuilderImpl().parse(URL, "<p>text</p>", LIMITS)
    assert isinstance(document, Document)
    assert isinstance(document.root, Node)
    assert isinstance(document.root.children, tuple)
    assert isinstance(element_children(document.root)[0].attrs, tuple)
    with pytest.raises(ValidationError):
        setattr(document.root, "tag", "changed")
