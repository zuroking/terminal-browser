import ast
from pathlib import Path

from terminal_browser.core.limits import Limits
from terminal_browser.html.tree import Document, TreeBuilderImpl
from terminal_browser.render.layout import LayoutEngineImpl, RenderedLine


LIMITS = Limits.defaults()
URL = "https://example.test/dir/page.html"


def document(source: str) -> Document:
    return TreeBuilderImpl().parse(URL, source, LIMITS)


def test_ast_import_boundaries() -> None:
    source_path = Path(__file__).parents[1] / "src" / "terminal_browser" / "render" / "layout.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    allowed_stdlib = {"__future__", "collections", "dataclasses", "typing", "pydantic"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name.split(".")[0] in allowed_stdlib for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                assert node.module is not None
                assert node.module.split(".")[0] in allowed_stdlib
            else:
                assert node.level == 2
                assert node.module in {"core.errors", "core.limits", "core.text", "html.tree"}


def test_effective_width_clamping() -> None:
    source = document("<p>text</p>")
    assert LayoutEngineImpl().render(source, 1).width == LIMITS.min_layout_width
    assert LayoutEngineImpl().render(source, 1000).width == LIMITS.max_line_width


def test_whitespace_collapse_and_nbsp() -> None:
    page = LayoutEngineImpl().render(document("<p>  a \n b  c  </p>"), 20)
    assert "a b \u00a0c" in [line.text for line in page.lines]


def test_word_wrap_and_hard_breaks() -> None:
    page = LayoutEngineImpl().render(document("<p>one two abcdefgh</p>"), 5)
    assert [line.text for line in page.lines] == ["one", "two", "abcde", "fgh"]
    combining = LayoutEngineImpl().render(document("<p>e\u0301abcdef</p>"), 4)
    assert combining.lines[0].text == "e\u0301abc"


def test_headings_uppercase_before_width() -> None:
    page = LayoutEngineImpl().render(document("<h1>Straße</h1><h2>Heading</h2>"), 20)
    texts = [line.text for line in page.lines]
    assert "STRASSE" in texts
    assert "# Heading" in texts


def test_pre_hard_cut_and_truncation_reason() -> None:
    page = LayoutEngineImpl().render(document("<pre>abcdef\tXYZ</pre>"), 4)
    pre_lines = [line for line in page.lines if line.kind == "pre"]
    assert all(len(line.text) <= 4 for line in pre_lines)
    assert page.truncated is True
    assert "P" in page.truncation_reasons
    assert "truncated:" in "".join(line.text for line in page.lines)


def test_lists_markers_and_indentation() -> None:
    page = LayoutEngineImpl().render(
        document(
            "<ul><li>one<ul><li>nested</li></ul></li></ul>"
            "<ol><li>first</li><li>second</li></ol>"
            "<dl><dt>term</dt><dd>description</dd></dl>"
        ),
        30,
    )
    texts = [line.text for line in page.lines]
    assert "- one" in texts
    assert "  - nested" in texts
    assert "1. first" in texts
    assert "2. second" in texts
    assert "    description" in texts


def test_multiline_tables_and_headers() -> None:
    page = LayoutEngineImpl().render(
        document(
            "<table><tr><th>H1</th><th>H2</th></tr>"
            "<tr><td>long cell</td><td>next</td></tr></table>"
        ),
        10,
    )
    table_lines = [line.text for line in page.lines if line.kind == "table"]
    assert table_lines.count("H1 | H2") == 1
    assert len(table_lines) >= 3


def test_forms_passwords_and_hidden() -> None:
    page = LayoutEngineImpl().render(
        document(
            "<form><input type='password' name='pass'>"
            "<input type='hidden' name='token' value='secret'>"
            "<input type='submit' name='go' value='Go'></form>"
        ),
        40,
    )
    text = "\n".join(line.text for line in page.lines)
    assert "pass=[password]" in text
    assert "token=[hidden]" in text
    assert "secret" not in text
    assert "go" in text


def test_links_inline_markers_and_extraction() -> None:
    page = LayoutEngineImpl().render(
        document("<p><a href='/path'>Click</a> <a href='javascript:x'>Bad</a></p>"),
        40,
    )
    text = "\n".join(line.text for line in page.lines)
    assert "Click[1]" in text
    assert "Bad" in text
    assert len(page.links) == 1
    assert page.links[0].href == "https://example.test/path"
    assert page.links[0].text == "Click"


def test_truncation_notice_reserves_lines() -> None:
    page = LayoutEngineImpl().render(document("<p>x</p>" * 5001), 20)
    assert page.truncated is True
    assert "R" in page.truncation_reasons
    assert page.lines[-1].text.startswith("[truncated: ")
    assert len(page.lines) <= LIMITS.max_render_lines
