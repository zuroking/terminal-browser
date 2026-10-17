import ast
from pathlib import Path

from terminal_browser.core.limits import Limits
from terminal_browser.html.entities import HTML4_ENTITIES, EntityDecoder


def decoder() -> EntityDecoder:
    return EntityDecoder(Limits.defaults())


def test_ast_import_boundaries() -> None:
    source_path = Path(__file__).parents[1] / "src" / "terminal_browser" / "html" / "entities.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            raise AssertionError("entities.py must not use absolute imports")
        if isinstance(node, ast.ImportFrom):
            assert node.level == 2
            assert node.module in {"core.errors", "core.limits"}


def test_numeric_decimal_valid_and_invalid() -> None:
    instance = decoder()
    assert instance.decode_text("&#65;") == "A"
    assert instance.decode_text("&#8364;") == "€"
    assert instance.decode_text("&#9;&#10;&#12;&#13;") == "\t\n\f\r"
    for reference in (
        "&#0;",
        "&#11;",
        "&#31;",
        "&#127;",
        "&#xD800;",
        "&#xDFFF;",
        "&#x110000;",
        "&#x1000000000000000000000000000000000000000;",
    ):
        assert instance.decode_text(reference) == "\ufffd"


def test_numeric_hexadecimal_valid_and_invalid() -> None:
    instance = decoder()
    assert instance.decode_text("&#x41;") == "A"
    assert instance.decode_text("&#X1F600;") == "\U0001f600"
    for reference in (
        "&#x0;",
        "&#xB;",
        "&#x1F;",
        "&#x7F;",
        "&#x80;",
        "&#x9F;",
        "&#xD800;",
        "&#xDFFF;",
        "&#x110000;",
    ):
        assert instance.decode_text(reference) == "\ufffd"
    assert instance.decode_text("&#x;") == "&#x;"
    assert instance.decode_text("&#xZZ;") == "&#xZZ;"


def test_named_legacy_text_decodes() -> None:
    instance = decoder()
    assert instance.decode_text("&amp") == "&"
    assert instance.decode_text("&lt") == "<"
    assert instance.decode_text("&gt") == ">"
    assert instance.decode_text("&copy") == "©"
    assert instance.decode_text("&not-an-entity") == "¬-an-entity"


def test_named_legacy_attribute_context_rule() -> None:
    instance = decoder()
    assert instance.decode_attribute("&amp=") == "&amp="
    assert instance.decode_attribute("&amp1") == "&amp1"
    assert instance.decode_attribute("&ampZ") == "&ampZ"
    assert instance.decode_attribute("&amp-test") == "&-test"
    assert instance.decode_attribute("&amp;") == "&"


def test_named_non_legacy_requires_semicolon() -> None:
    instance = decoder()
    assert instance.decode_text("&nbsp") == "&nbsp"
    assert instance.decode_attribute("&nbsp") == "&nbsp"
    assert instance.decode_text("&nbsp;") == "\u00a0"
    assert instance.decode_text("&mdash") == "&mdash"
    assert instance.decode_text("&mdash;") == "—"


def test_unknown_named_reference_remains_literal() -> None:
    instance = decoder()
    assert instance.decode_text("&unknown;") == "&unknown;"
    assert instance.decode_attribute("&unknown;") == "&unknown;"
    assert instance.decode_text("before &notareal; after") == "before &notareal; after"


def test_core_table_entries_present() -> None:
    expected = {
        "amp": ("&", True),
        "lt": ("<", True),
        "gt": (">", True),
        "quot": ('"', True),
        "apos": ("'", False),
        "nbsp": ("\u00a0", False),
        "mdash": ("—", False),
        "ndash": ("–", False),
        "hellip": ("…", False),
        "laquo": ("«", True),
        "raquo": ("»", True),
        "rsquo": ("’", False),
        "lsquo": ("‘", False),
        "copy": ("©", True),
        "reg": ("®", True),
        "trade": ("™", False),
    }
    for name, value in expected.items():
        assert HTML4_ENTITIES[name] == value
        assert isinstance(HTML4_ENTITIES[name][1], bool)
