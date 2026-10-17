import ast
from pathlib import Path

import pytest

from terminal_browser.core.errors import FormError, UnsupportedSchemeError
from terminal_browser.core.limits import Limits
from terminal_browser.forms import FormField, FormSpec, extract_forms, serialize_form
from terminal_browser.html.tree import Node, TreeBuilderImpl


LIMITS = Limits.defaults()
URL = "https://example.test/dir/page.html"


def make_limits(**overrides: int | float) -> Limits:
    values: dict[str, int | float] = {**LIMITS.model_dump(), **overrides}
    return Limits.model_validate(values)


def root(source: str) -> Node:
    return TreeBuilderImpl().parse(URL, source, LIMITS).root


def only_form(source: str) -> FormSpec:
    forms = extract_forms(root(source), URL, LIMITS)
    assert len(forms) == 1
    return forms[0]


def test_ast_import_boundaries() -> None:
    source_path = Path(__file__).parents[1] / "src" / "terminal_browser" / "forms.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    allowed_stdlib = {"__future__", "collections", "typing", "urllib", "pydantic"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name.split(".")[0] in allowed_stdlib for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                assert node.module is not None
                assert node.module.split(".")[0] in allowed_stdlib
            else:
                assert node.level == 1
                assert node.module in {"core.errors", "core.limits", "core.sanitize", "html.tree", "url"}


def test_field_type_mapping() -> None:
    form = only_form(
        "<form>"
        "<input name='text'><input type='password' name='password'>"
        "<input type='hidden' name='hidden'><input type='checkbox' name='check'>"
        "<input type='radio' name='choice'><input type='submit' name='submit'>"
        "<input type='reset' name='reset'><input type='image' name='image'>"
        "<input type='button' name='button'><button type='submit' name='button-submit'>"
        "<button type='button' name='ignored'>"
        "</form>"
    )
    assert [(field.name, field.field_type) for field in form.fields] == [
        ("text", "text"),
        ("password", "password"),
        ("hidden", "hidden"),
        ("check", "checkbox"),
        ("choice", "radio"),
        ("submit", "submit"),
        ("button-submit", "submit"),
    ]


def test_label_resolution() -> None:
    form = only_form(
        "<form>"
        "<label for='named'>Named label</label><input name='named'>"
        "<label>Ancestor label <input name='ancestor'></label>"
        "<input name='aria' aria-label='Aria label'>"
        "<input name='placeholder' placeholder='Placeholder label'>"
        "<input name='fallback'>"
        "</form>"
    )
    assert [field.label for field in form.fields] == [
        "Named label",
        "Ancestor label",
        "Aria label",
        "Placeholder label",
        "fallback",
    ]


def test_successful_controls_and_duplicate_names() -> None:
    form = only_form(
        "<form>"
        "<input name='radio' type='radio' value='a'>"
        "<input name='radio' type='radio' value='b'>"
        "<input name='submit' type='submit' value='one'>"
        "<input name='submit' type='submit' value='two'>"
        "<input type='checkbox' name='disabled' disabled>"
        "<input type='text'>"
        "</form>"
    )
    assert [field.name for field in form.fields] == ["radio", "radio", "submit", "submit"]
    with pytest.raises(FormError):
        only_form("<form><input type='checkbox' name='same'><input type='checkbox' name='same'></form>")


def test_checkbox_radio_overrides_and_defaults() -> None:
    form = only_form(
        "<form>"
        "<input type='checkbox' name='check' value='off' checked>"
        "<input type='radio' name='choice' value='a'>"
        "<input type='radio' name='choice' value='b' checked>"
        "</form>"
    )
    assert serialize_form(form, {}, LIMITS) == (
        f"{URL}?check=off&choice=b",
        b"",
    )
    assert serialize_form(form, {"check": "0", "choice": "a"}, LIMITS) == (
        f"{URL}?choice=a",
        b"",
    )
    assert serialize_form(form, {"check": "off"}, LIMITS) == (
        f"{URL}?check=off&choice=b",
        b"",
    )


def test_select_extraction_and_multiple_submit_error() -> None:
    single = only_form(
        "<form><select name='choice'>"
        "<option value='first' disabled>First</option>"
        "<option value='second'>Second</option>"
        "</select></form>"
    )
    assert single.fields[0].options == (("second", "Second"),)
    assert single.fields[0].selected_options == ("second",)
    assert serialize_form(single, {}, LIMITS) == (
        f"{URL}?choice=second",
        b"",
    )
    with pytest.raises(FormError):
        serialize_form(single, {"choice": "first"}, LIMITS)

    multiple = only_form(
        "<form><select name='many' multiple>"
        "<option value='a' selected>A</option><option value='b' selected>B</option>"
        "</select></form>"
    )
    assert multiple.fields[0].selected_options == ("a", "b")
    with pytest.raises(FormError):
        serialize_form(multiple, {}, LIMITS)


def test_url_encoding_and_get_post_serialization() -> None:
    get_form = only_form(
        "<form method='GET' action='/search?old=1'><input name='q' value='a b'></form>"
    )
    assert serialize_form(get_form, {}, LIMITS) == (
        "https://example.test/search?q=a+b",
        b"",
    )
    post_form = only_form(
        "<form method='POST' action='/submit'><input name='q' value='a+b&c'></form>"
    )
    assert serialize_form(post_form, {}, LIMITS) == (
        "https://example.test/submit",
        b"q=a%2Bb%26c",
    )


def test_form_limits_enforced() -> None:
    field_limits = make_limits(
        max_form_fields=1,
        max_nodes=10,
        max_tokens=100,
        max_dom_depth=2,
        max_repl_tokens=1,
    )
    with pytest.raises(FormError):
        extract_forms(
            root("<form><input name='a'><input name='b'></form>"),
            URL,
            field_limits,
        )
    byte_limits = make_limits(
        max_form_bytes=5,
        max_form_fields=10,
        max_nodes=20,
        max_tokens=100,
        max_dom_depth=2,
        max_repl_tokens=1,
        max_repl_line_bytes=5,
    )
    with pytest.raises(FormError):
        serialize_form(
            only_form("<form><input name='a' value='long value'></form>"),
            {},
            byte_limits,
        )


def test_unsupported_action_scheme_retained_but_refuses_submit() -> None:
    form = only_form("<form action='javascript:alert(1)'><input name='a'></form>")
    assert form.action == "javascript:alert(1)"
    with pytest.raises(UnsupportedSchemeError):
        serialize_form(form, {}, LIMITS)


def test_no_default_submit_selected() -> None:
    form = only_form(
        "<form><input type='submit' name='go' value='Go'><button type='submit' name='go' value='Again'>Again</button></form>"
    )
    assert serialize_form(form, {}, LIMITS) == (URL, b"")
    assert serialize_form(form, {"go": "1"}, LIMITS) == (
        "https://example.test/dir/page.html?go=Go",
        b"",
    )
