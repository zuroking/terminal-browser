import ast
from pathlib import Path
import random

from terminal_browser.core.encoding import CHARSET_ALLOWLIST, decode_body
from terminal_browser.core.limits import Limits


def test_charset_allowlist_is_exact() -> None:
    assert CHARSET_ALLOWLIST == frozenset(
        {
            "utf-8",
            "windows-1251",
            "koi8-r",
            "iso-8859-1",
            "windows-1252",
        }
    )


def test_valid_http_charset_decodes_cyrillic() -> None:
    body = "Привет".encode("windows-1251")

    decoded = decode_body(
        body,
        "text/html; charset=windows-1251",
        Limits.defaults(),
    )

    assert decoded == "Привет"


def test_allowlisted_http_charset_wins_over_conflicting_meta() -> None:
    body = '<meta charset="koi8-r">Привет'.encode("windows-1251")

    decoded = decode_body(
        body,
        "text/html; charset=windows-1251",
        Limits.defaults(),
    )

    assert decoded == '<meta charset="koi8-r">Привет'


def test_missing_http_charset_uses_meta_prescan() -> None:
    body = '<meta charset="koi8-r">Привет'.encode("koi8-r")

    decoded = decode_body(body, "text/html", Limits.defaults())

    assert decoded == '<meta charset="koi8-r">Привет'


def test_disallowed_http_charset_falls_through_to_meta() -> None:
    body = '<meta charset="koi8-r">Привет'.encode("koi8-r")

    decoded = decode_body(
        body,
        "text/html; charset=utf-7",
        Limits.defaults(),
    )

    assert decoded == '<meta charset="koi8-r">Привет'


def test_no_charset_defaults_to_utf8() -> None:
    body = "Привет".encode("utf-8")

    assert decode_body(body, "text/html", Limits.defaults()) == "Привет"


def test_malformed_content_type_does_not_raise() -> None:
    body = "Привет".encode("utf-8")

    assert decode_body(body, "\x00 not a media type", Limits.defaults()) == "Привет"


def test_prescan_respects_window_limit() -> None:
    limits = Limits.model_validate(
        {**Limits.defaults().model_dump(), "max_charset_prescan_bytes": 10}
    )
    body = ("x" * 10 + '<meta charset="koi8-r">Привет').encode("koi8-r")

    decoded = decode_body(body, "text/html", limits)

    assert decoded.startswith("xxxxxxxxxx")
    assert "Привет" not in decoded
    assert "�" in decoded


def test_prescan_handles_http_equiv_content_type() -> None:
    body = (
        '<meta http-equiv="Content-Type" content="text/html; charset=koi8-r">'
        "Привет"
    ).encode("koi8-r")

    decoded = decode_body(body, "text/html", Limits.defaults())

    assert "Привет" in decoded


def test_prescan_handles_unquoted_charset() -> None:
    body = "<meta charset=koi8-r>Привет".encode("koi8-r")

    decoded = decode_body(body, "text/html", Limits.defaults())

    assert "Привет" in decoded


def test_invalid_utf8_uses_replacement_character() -> None:
    decoded = decode_body(b"\xff", None, Limits.defaults())

    assert "�" in decoded


def test_random_inputs_never_raise() -> None:
    generator = random.Random(20260924)
    limits = Limits.defaults()
    adversarial_headers = (
        "",
        "\x00",
        "text/html; charset=utf-7",
        "text/html; charset=" + "x" * 4096,
        "not a media type",
        "text/html; charset=\"unterminated",
        "text/html; charset=\ud800",
    )

    for index in range(200):
        if index < len(adversarial_headers):
            header = adversarial_headers[index]
        else:
            header = "".join(
                chr(generator.randrange(0x11000))
                for _ in range(generator.randrange(32))
            )
        body = bytes(generator.randrange(256) for _ in range(generator.randrange(128)))
        decode_body(body, header, limits)


def test_encoding_source_has_no_forbidden_imports() -> None:
    source_path = (
        Path(__file__).parents[1]
        / "src"
        / "terminal_browser"
        / "core"
        / "encoding.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    forbidden = {"core.errors", "html.tokenizer", "html.tree"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in forbidden
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert module not in forbidden
            for alias in node.names:
                assert f"{module}.{alias.name}" not in forbidden
