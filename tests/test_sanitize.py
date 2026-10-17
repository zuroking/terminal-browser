import ast
from pathlib import Path
import random
import unicodedata

import pytest

from terminal_browser.core.sanitize import sanitize_attribute, sanitize_text


REMOVED_CONTROLS = (
    "\x00",
    "\x01",
    "\x1b",
    "\x1f",
    "\x7f",
    "\x85",
    "\u202a",
    "\u202b",
    "\u202c",
    "\u202d",
    "\u202e",
    "\u2066",
    "\u2067",
    "\u2068",
    "\u2069",
    "\ufeff",
    "\u200b",
    "\u200c",
    "\u200d",
    "\u200e",
    "\u200f",
)


def assert_no_removed_controls(value: str, allow_text_controls: bool) -> None:
    for character in value:
        codepoint = ord(character)
        if allow_text_controls and character in "\n\t":
            continue
        assert not (codepoint <= 0x1F)
        assert codepoint != 0x7F
        assert not (0x80 <= codepoint <= 0x9F)
        assert unicodedata.category(character) != "Cf"


@pytest.mark.parametrize("character", REMOVED_CONTROLS)
def test_text_strips_each_named_control(character: str) -> None:
    assert sanitize_text(f"before{character}after") == "beforeafter"


def test_text_preserves_newline_and_tab() -> None:
    assert sanitize_text("a\n\tb") == "a\n\tb"


def test_attribute_converts_newline_and_tab_to_single_spaces() -> None:
    assert sanitize_attribute("a\n\tb") == "a  b"


@pytest.mark.parametrize("value", ("\r", "\r\n", "\n\r"))
def test_carriage_return_is_removed_in_both_modes(value: str) -> None:
    text_result = sanitize_text(value)
    attribute_result = sanitize_attribute(value)

    assert "\r" not in text_result
    assert "\r" not in attribute_result


def test_mixed_text_removes_only_controls() -> None:
    value = "Привет\u202eLatin\u200b中文\u0301"

    assert sanitize_text(value) == "ПриветLatin中文\u0301"


def test_sanitizers_are_idempotent_for_adversarial_inputs() -> None:
    values = (
        "",
        "plain",
        "a\x00b\x1bc\u202ed\ufeff",
        "line\nnext\ttab",
        "attribute\r\nvalue",
        "中文\u200b\u0301\u00a0",
    )

    for value in values:
        text_once = sanitize_text(value)
        attribute_once = sanitize_attribute(value)
        assert sanitize_text(text_once) == text_once
        assert sanitize_attribute(attribute_once) == attribute_once


def test_random_unicode_inputs_never_raise_and_preserve_invariants() -> None:
    generator = random.Random(20260924)
    private_use_ranges = ((0xE000, 0xF8FF), (0xF0000, 0xFFFFD), (0x100000, 0x10FFFD))
    unassigned_codepoints = (0x0378, 0x0380, 0x10FFFF)

    for _ in range(500):
        characters: list[str] = []
        for _ in range(generator.randrange(64)):
            choice = generator.randrange(5)
            if choice == 0:
                codepoint = generator.randrange(0x20)
            elif choice == 1:
                codepoint = generator.randrange(0x7F, 0xA0)
            elif choice == 2:
                start, end = private_use_ranges[generator.randrange(len(private_use_ranges))]
                codepoint = generator.randrange(start, end + 1)
            elif choice == 3:
                codepoint = unassigned_codepoints[generator.randrange(len(unassigned_codepoints))]
            else:
                codepoint = generator.randrange(0x110000)
            characters.append(chr(codepoint))
        value = "".join(characters)

        text_result = sanitize_text(value)
        attribute_result = sanitize_attribute(value)
        assert_no_removed_controls(text_result, allow_text_controls=True)
        assert_no_removed_controls(attribute_result, allow_text_controls=False)


def test_empty_string_round_trips() -> None:
    assert sanitize_text("") == ""
    assert sanitize_attribute("") == ""


def test_very_long_mixed_string_terminates() -> None:
    value = "a中\u200b\u0301\x1b" * 20_000

    text_result = sanitize_text(value)
    attribute_result = sanitize_attribute(value)

    assert len(text_result) == 60_000
    assert len(attribute_result) == 60_000


def test_sanitize_source_has_no_forbidden_imports() -> None:
    source_path = (
        Path(__file__).parents[1]
        / "src"
        / "terminal_browser"
        / "core"
        / "sanitize.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    forbidden_prefixes = (
        "core.errors",
        "net.",
        "html.",
        "render.",
        "term.",
        "session.",
    )

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith(forbidden_prefixes)
                assert alias.name not in {"net", "html", "render", "term", "session"}
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert not module.startswith(forbidden_prefixes)
            for alias in node.names:
                assert f"{module}.{alias.name}" not in forbidden_prefixes
