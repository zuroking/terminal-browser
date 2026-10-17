from __future__ import annotations

from collections.abc import Iterator
from typing import Literal, cast
from urllib.parse import urlencode, urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict

from .core.errors import FormError, InvalidUrlError, UnsupportedSchemeError
from .core.limits import Limits
from .core.sanitize import sanitize_attribute, sanitize_text
from .html.tree import Node
from .url import ParsedUrl, UrlParserImpl


FormFieldType = Literal[
    "text",
    "password",
    "hidden",
    "checkbox",
    "radio",
    "select",
    "textarea",
    "submit",
]


class FormField(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    name: str
    field_type: FormFieldType
    label: str
    value: str
    checked: bool
    required: bool
    disabled: bool
    options: tuple[tuple[str, str], ...]
    selected_options: tuple[str, ...]


class FormSpec(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    index: int
    action: str
    method: Literal["GET", "POST"]
    fields: tuple[FormField, ...]


def extract_forms(
    root: Node,
    document_url: str,
    limits: Limits,
) -> tuple[FormSpec, ...]:
    parser = UrlParserImpl(limits)
    parsed_document = parser.parse(document_url)
    labels = tuple(
        node
        for node in _walk_elements(root)
        if node.tag == "label"
    )
    forms: list[FormSpec] = []
    for form in _walk_elements(root):
        if form.tag != "form":
            continue
        fields = _extract_fields(form, labels, limits)
        method = _form_method(_attrs(form).get("method"))
        action = _form_action(_attrs(form).get("action"), parsed_document, parser)
        forms.append(
            FormSpec(
                index=len(forms) + 1,
                action=action,
                method=method,
                fields=tuple(fields),
            )
        )
    return tuple(forms)


def serialize_form(
    form: FormSpec,
    field_values: dict[str, str],
    limits: Limits,
) -> tuple[str, bytes]:
    names = {field.name for field in form.fields}
    unknown = set(field_values) - names
    if unknown:
        raise FormError("field override names an unknown control")
    pairs = _successful_pairs(form, field_values)
    if len(pairs) > limits.max_form_fields:
        raise FormError("form field count exceeds max_form_fields")
    encoded = urlencode(pairs, doseq=True).encode("utf-8")
    if len(encoded) > limits.max_form_bytes:
        raise FormError("form encoding exceeds max_form_bytes")
    parser = UrlParserImpl(limits)
    scheme = parser.scheme_of(form.action)
    if scheme not in {"http", "https"}:
        raise UnsupportedSchemeError("form action uses an unsupported scheme")
    action = parser.parse(form.action)
    if form.method == "GET":
        parts = urlsplit(action.normalized_url)
        query = encoded.decode("ascii")
        normalized = urlunsplit(
            (parts.scheme, parts.netloc, parts.path, query, "")
        )
        return normalized, b""
    return action.normalized_url, encoded


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


def _extract_fields(
    form: Node,
    labels: tuple[Node, ...],
    limits: Limits,
) -> list[FormField]:
    fields: list[FormField] = []
    for node in _walk_elements(form):
        field_type = _field_type(node)
        if field_type is None:
            continue
        attrs = _attrs(node)
        name = sanitize_attribute(attrs.get("name", ""))
        if not name or "disabled" in attrs:
            continue
        label = _label_for(form, node, name, labels)
        if field_type == "select":
            options, selected = _select_options(node)
            value = ""
        elif field_type == "textarea":
            options = ()
            selected = ()
            value = sanitize_text(_node_text(node))
        else:
            options = ()
            selected = ()
            value = sanitize_attribute(attrs.get("value", ""))
            if field_type in {"checkbox", "radio"} and "value" not in attrs:
                value = "on"
        field = FormField(
            name=name,
            field_type=field_type,
            label=label,
            value=value,
            checked="checked" in attrs if field_type in {"checkbox", "radio"} else False,
            required="required" in attrs,
            disabled=False,
            options=options,
            selected_options=selected,
        )
        fields.append(field)
        if len(fields) > limits.max_form_fields:
            raise FormError("form field count exceeds max_form_fields")
    _validate_duplicate_names(fields)
    return fields


def _field_type(node: Node) -> FormFieldType | None:
    attrs = _attrs(node)
    if node.tag == "textarea":
        return "textarea"
    if node.tag == "select":
        return "select"
    if node.tag == "input":
        input_type = attrs.get("type", "text").lower()
        if input_type in {"", "text"}:
            return "text"
        if input_type in {"password", "hidden", "checkbox", "radio", "submit"}:
            return cast(FormFieldType, input_type)
        return None
    if node.tag == "button" and attrs.get("type", "").lower() == "submit":
        return "submit"
    return None


def _label_for(
    form: Node,
    node: Node,
    name: str,
    labels: tuple[Node, ...],
) -> str:
    for label in labels:
        if sanitize_attribute(_attrs(label).get("for", "")) == name:
            text = sanitize_text(_node_text(label)).strip()
            if text:
                return text
    ancestor = _ancestor_label(form, node)
    if ancestor is not None:
        text = sanitize_text(_node_text(ancestor)).strip()
        if text:
            return text
    attrs = _attrs(node)
    for attribute_name in ("aria-label", "placeholder"):
        value = sanitize_text(attrs.get(attribute_name, "")).strip()
        if value:
            return value
    return sanitize_text(name).strip()


def _ancestor_label(form: Node, node: Node) -> Node | None:
    current_path: list[Node] = []

    def visit(current: Node) -> Node | None:
        if current is node:
            for ancestor in current_path:
                if ancestor.tag == "label":
                    return ancestor
            return None
        if current.kind == "element":
            current_path.append(current)
            for child in current.children:
                if child.kind == "element":
                    result = visit(child)
                    if result is not None:
                        return result
            current_path.pop()
        return None

    return visit(form)


def _select_options(node: Node) -> tuple[tuple[tuple[str, str], ...], tuple[str, ...]]:
    options: list[tuple[str, str]] = []
    selected: list[str] = []
    multiple = "multiple" in _attrs(node)
    for option in _walk_elements(node):
        if option.tag != "option":
            continue
        attrs = _attrs(option)
        if "disabled" in attrs:
            continue
        value = sanitize_attribute(attrs.get("value", "")) or sanitize_text(
            _node_text(option)
        ).strip()
        options.append((value, sanitize_text(_node_text(option)).strip()))
        if "selected" in attrs:
            selected.append(value)
    if not multiple and not selected:
        enabled = next((value for value, _label in options if value), "")
        if enabled:
            selected.append(enabled)
    return tuple(options), tuple(selected)


def _validate_duplicate_names(fields: list[FormField]) -> None:
    by_name: dict[str, list[FormField]] = {}
    for field in fields:
        by_name.setdefault(field.name, []).append(field)
    for name, group in by_name.items():
        if len(group) == 1:
            continue
        field_type = group[0].field_type
        if field_type == "radio":
            if any(member.field_type != "radio" for member in group):
                raise FormError("duplicate form control name")
            if sum(member.checked for member in group) > 1:
                raise FormError("radio group has multiple checked members")
        elif field_type == "submit":
            if any(member.field_type != "submit" for member in group):
                raise FormError("duplicate form control name")
        else:
            raise FormError("duplicate form control name")


def _form_method(value: str | None) -> Literal["GET", "POST"]:
    if value is None:
        return "GET"
    normalized = value.strip()
    if not normalized.isascii():
        raise FormError("form method is invalid")
    method = normalized.upper()
    if method == "GET":
        return "GET"
    if method == "POST":
        return "POST"
    raise FormError("form method is invalid")


def _form_action(
    value: str | None,
    document_url: ParsedUrl,
    parser: UrlParserImpl,
) -> str:
    if value is None or not value.strip():
        return document_url.normalized_url
    action = value.strip()
    scheme = parser.scheme_of(action)
    if scheme not in {"", "http", "https"}:
        if len(action) <= len(scheme) + 1:
            raise FormError("form action is malformed")
        return action
    try:
        return parser.resolve(document_url, action).normalized_url
    except (InvalidUrlError, UnsupportedSchemeError) as error:
        raise FormError("form action is malformed") from error


def _successful_pairs(
    form: FormSpec,
    field_values: dict[str, str],
) -> list[tuple[str, str]]:
    radio_groups: dict[str, list[FormField]] = {}
    for field in form.fields:
        if field.field_type == "radio":
            radio_groups.setdefault(field.name, []).append(field)
    selected_radios: dict[str, FormField | None] = {}
    for name, group in radio_groups.items():
        override = field_values.get(name)
        if override is None:
            selected_radios[name] = next(
                (field for field in group if field.checked),
                None,
            )
            continue
        if override in {"0", "false", "off", ""}:
            selected_radios[name] = next(
                (
                    field
                    for field in group
                    if field.value == override and field.value != "on"
                ),
                None,
            )
            continue
        selected_radio = next((field for field in group if field.value == override), None)
        if selected_radio is None and override == "on" and all(
            field.value == "on" for field in group
        ):
            selected_radio = group[0]
        if selected_radio is None:
            raise FormError("radio override does not match an enabled value")
        selected_radios[name] = selected_radio
    selected_submit = next(
        (
            field
            for field in form.fields
            if field.field_type == "submit"
            and field.name in field_values
            and field_values[field.name]
        ),
        None,
    )
    pairs: list[tuple[str, str]] = []
    for field in form.fields:
        if field.field_type == "submit":
            if field is selected_submit:
                pairs.append((field.name, field.value))
            continue
        if field.field_type == "select":
            if len(field.selected_options) > 1:
                raise FormError("multiple select cannot be serialized")
            if field.name in field_values:
                selected = field_values[field.name]
                if not _option_enabled(field, selected):
                    raise FormError("select override is not an enabled option")
            else:
                selected = field.selected_options[0] if field.selected_options else ""
            if selected:
                pairs.append((field.name, selected))
            continue
        if field.field_type == "checkbox":
            checked = field.checked
            if field.name in field_values:
                checked = _override_checked(field, field_values[field.name])
            if checked:
                pairs.append((field.name, field.value))
            continue
        if field.field_type == "radio":
            if selected_radios.get(field.name) is field:
                pairs.append((field.name, field.value))
            continue
        pairs.append((field.name, field_values.get(field.name, field.value)))
    return pairs


def _option_enabled(field: FormField, value: str) -> bool:
    return any(option_value == value for option_value, _label in field.options)


def _override_checked(field: FormField, override: str) -> bool:
    false_tokens = {"0", "false", "off", ""}
    true_tokens = {"on", "1", "true", "yes"}
    if override in true_tokens:
        return True
    if override in false_tokens:
        return override == field.value and field.value != "on"
    return override == field.value
