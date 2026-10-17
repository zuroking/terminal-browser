import ast
from pathlib import Path
from typing import Iterator

import pytest

from terminal_browser.core.errors import (
    BodyTooLargeError,
    HeaderTooLargeError,
    ProtocolError,
    TruncatedBodyError,
)
from terminal_browser.core.limits import Limits
from terminal_browser.net.wire import (
    HeaderFields,
    decode_chunked,
    parse_headers,
    parse_status_line,
)


LIMITS = Limits.defaults()
SINGLETON_FIELDS = (
    "Location",
    "Content-Type",
    "Content-Encoding",
    "ETag",
    "Last-Modified",
    "Age",
    "Date",
    "Expires",
)


def limited(**overrides: int) -> Limits:
    return Limits.model_validate({**LIMITS.model_dump(), **overrides})


def fragments(*values: bytes) -> Iterator[bytes]:
    yield from values


def test_valid_http_1_0_status_line() -> None:
    parsed = parse_status_line(b"HTTP/1.0 200 OK\r\n", LIMITS)

    assert parsed.version == "HTTP/1.0"
    assert parsed.status == 200
    assert parsed.reason == "OK"


def test_valid_http_1_1_status_line_without_reason() -> None:
    parsed = parse_status_line(b"HTTP/1.1 204\r\n", LIMITS)

    assert parsed.version == "HTTP/1.1"
    assert parsed.status == 204
    assert parsed.reason == ""


@pytest.mark.parametrize(
    "raw",
    (
        b"HTTP/2.0 200 OK\r\n",
        b"HTTP/1.1 20 OK\r\n",
        b"HTTP/1.1 2xx OK\r\n",
        b"HTTP/1.1 200\tOK\r\n",
    ),
)
def test_malformed_status_lines_raise_protocol_error(raw: bytes) -> None:
    with pytest.raises(ProtocolError):
        parse_status_line(raw, LIMITS)


def test_oversized_reason_phrase_is_rejected() -> None:
    with pytest.raises(HeaderTooLargeError):
        parse_status_line(b"HTTP/1.1 200 " + b"x" * 100, limited(max_header_size=32))


def test_valid_headers_preserve_order_and_lowercase_names() -> None:
    headers = parse_headers(
        b"X-First: one\r\nSet-Cookie: a=1\r\nset-cookie: b=2\r\n\r\n",
        LIMITS,
    )

    assert headers == (
        ("x-first", "one"),
        ("set-cookie", "a=1"),
        ("set-cookie", "b=2"),
    )


def test_obs_text_maps_latin1_code_point() -> None:
    headers = parse_headers(b"X-Text: \x80\xff\r\n", LIMITS)

    assert headers == (("x-text", "\u0080\u00ff"),)


@pytest.mark.parametrize("value", (b"\x00", b"\x01", b"\x7f", b"\r", b"\n"))
def test_control_bytes_in_header_value_are_rejected(value: bytes) -> None:
    with pytest.raises(ProtocolError):
        parse_headers(b"X-Test: a" + value + b"b\r\n", LIMITS)


@pytest.mark.parametrize("field_name", SINGLETON_FIELDS)
def test_repeated_singleton_header_is_rejected(field_name: str) -> None:
    raw = f"{field_name}: one\r\n{field_name.upper()}: two\r\n".encode("ascii")

    with pytest.raises(ProtocolError):
        parse_headers(raw, LIMITS)


def test_header_size_limit_is_checked_while_parsing() -> None:
    with pytest.raises(HeaderTooLargeError):
        parse_headers(b"X-Long: " + b"a" * 100 + b"\r\n", limited(max_header_size=16))


def test_header_count_limit_is_checked_while_parsing() -> None:
    raw = b"X-One: 1\r\nX-Two: 2\r\n"

    with pytest.raises(HeaderTooLargeError):
        parse_headers(raw, limited(max_header_count=1))


def test_obsolete_line_folding_is_rejected() -> None:
    with pytest.raises(ProtocolError):
        parse_headers(b"X-Test: one\r\n continued\r\n", LIMITS)


def test_chunked_single_chunk() -> None:
    body, trailers = decode_chunked(fragments(b"3\r\nabc\r\n0\r\n\r\n"), LIMITS)

    assert body == b"abc"
    assert trailers == ()


def test_chunked_multiple_chunks() -> None:
    body, trailers = decode_chunked(
        fragments(b"3\r\nabc\r\n", b"2\r\nde\r\n0\r\n\r\n"),
        LIMITS,
    )

    assert body == b"abcde"
    assert trailers == ()


def test_chunk_extensions_are_ignored() -> None:
    body, trailers = decode_chunked(
        fragments(b"4;name=value\r\nWiki\r\n0\r\n\r\n"),
        LIMITS,
    )

    assert body == b"Wiki"
    assert trailers == ()


def test_zero_chunk_only_is_empty_body() -> None:
    body, trailers = decode_chunked(fragments(b"0\r\n\r\n"), LIMITS)

    assert body == b""
    assert trailers == ()


def test_chunked_trailers_are_returned_separately() -> None:
    body, trailers = decode_chunked(
        fragments(b"0\r\nX-Trailer: yes\r\nX-Other: 2\r\n\r\n"),
        LIMITS,
    )

    assert body == b""
    assert trailers == (("x-trailer", "yes"), ("x-other", "2"))


@pytest.mark.parametrize("field_name", ("Content-Length", "Transfer-Encoding"))
def test_chunked_framing_trailers_are_rejected(field_name: str) -> None:
    raw = f"0\r\n{field_name}: 1\r\n\r\n".encode("ascii")

    with pytest.raises(ProtocolError):
        decode_chunked(fragments(raw), LIMITS)


def test_truncated_mid_chunk_data() -> None:
    with pytest.raises(TruncatedBodyError):
        decode_chunked(fragments(b"3\r\nab"), LIMITS)


def test_truncated_mid_size_line() -> None:
    with pytest.raises(TruncatedBodyError):
        decode_chunked(fragments(b"3\r"), LIMITS)


def test_invalid_chunk_size_hex() -> None:
    with pytest.raises(ProtocolError):
        decode_chunked(fragments(b"Z\r\nabc\r\n0\r\n\r\n"), LIMITS)


def test_missing_crlf_after_chunk_data() -> None:
    with pytest.raises(ProtocolError):
        decode_chunked(fragments(b"3\r\nabc0\r\n\r\n"), LIMITS)


def test_oversized_chunk_size_line() -> None:
    with pytest.raises(ProtocolError):
        decode_chunked(
            fragments(b"A" * 100 + b"\r\n"),
            limited(max_header_size=16),
        )


def test_body_limit_rejects_before_consuming_next_fragment() -> None:
    consumed: list[int] = []

    def bounded_fragments() -> Iterator[bytes]:
        consumed.append(1)
        yield b"4\r\n"
        consumed.append(2)
        raise AssertionError("body data was over-consumed")

    with pytest.raises(BodyTooLargeError):
        decode_chunked(
            bounded_fragments(),
            limited(
                max_body_bytes=3,
                max_charset_prescan_bytes=3,
                chunk_read_size=3,
            ),
        )

    assert consumed == [1]


def test_wire_source_has_only_locked_import_dependencies() -> None:
    source_path = (
        Path(__file__).parents[1]
        / "src"
        / "terminal_browser"
        / "net"
        / "wire.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    allowed_modules = {
        "collections.abc",
        "typing",
        "pydantic",
        "core.errors",
        "core.limits",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name in allowed_modules
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert module in allowed_modules
