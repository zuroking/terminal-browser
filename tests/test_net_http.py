import ast
from pathlib import Path
import socket
import ssl
from typing import cast
import zlib

import pytest

from terminal_browser.core.clock import FakeClock
from terminal_browser.core.errors import (
    DecompressionError,
    ProtocolError,
    RedirectError,
    ResponseTimeoutError,
    TooManyRedirectsError,
    UnsupportedSchemeError,
)
from terminal_browser.core.limits import Limits
from terminal_browser.net.cache import CacheEntry, CacheKey, build_entry
from terminal_browser.net.cookies import Cookie, CookieHeader
from terminal_browser.net.http import HttpClientImpl, HttpRequest
from terminal_browser.net.transport import TcpTarget, TlsPolicy
from terminal_browser.net.wire import HeaderFields
from terminal_browser.url import ParsedUrl


LIMITS = Limits.defaults()


def make_limits(**overrides: int | float) -> Limits:
    values: dict[str, int | float] = {**LIMITS.model_dump(), **overrides}
    return Limits.model_validate(values)


class ScriptedTransport:
    def __init__(
        self,
        responses: tuple[bytes, ...] = (),
        clock: FakeClock | None = None,
        read_delay: float = 0.0,
        connect_delay: float = 0.0,
        send_delay: float = 0.0,
    ) -> None:
        self._responses = list(responses)
        self._clock = clock or FakeClock(0.0, 100.0)
        self._read_delay = read_delay
        self._connect_delay = connect_delay
        self._send_delay = send_delay
        self._response = b""
        self._offset = 0
        self.sent: list[bytes] = []
        self.connect_calls = 0
        self.close_calls = 0

    def resolve(
        self,
        host: str,
        port: int,
        dns_timeout_sec: float,
    ) -> list[socket.AddressInfo]:
        return []

    def connect(
        self,
        target: TcpTarget,
        remaining_sec: float,
    ) -> socket.socket:
        self.connect_calls += 1
        if not self._responses:
            raise AssertionError("unexpected transport connection")
        self._response = self._responses.pop(0)
        self._offset = 0
        self._clock.advance(self._connect_delay)
        return cast(socket.socket, object())

    def upgrade_to_tls(
        self,
        sock: socket.socket,
        target: TcpTarget,
        policy: TlsPolicy,
        remaining_sec: float,
    ) -> ssl.SSLSocket:
        return cast(ssl.SSLSocket, sock)

    def send_all(
        self,
        sock: socket.socket,
        data: bytes,
        remaining_sec: float,
    ) -> None:
        self.sent.append(data)
        self._clock.advance(self._send_delay)

    def recv_bounded(
        self,
        sock: socket.socket,
        max_bytes: int,
        remaining_sec: float,
        chunk_size: int,
    ) -> bytes:
        if self._offset >= len(self._response):
            self._clock.advance(self._read_delay)
            return b""
        length = min(max_bytes, chunk_size, len(self._response) - self._offset)
        start = self._offset
        self._offset += length
        self._clock.advance(self._read_delay)
        return self._response[start : start + length]

    def close(self, sock: socket.socket) -> None:
        self.close_calls += 1


class FakeCache:
    def __init__(self, entries: tuple[CacheEntry, ...] = ()) -> None:
        self.entries = {entry.key: entry for entry in entries}
        self.get_keys: list[CacheKey] = []
        self.put_entries: list[CacheEntry] = []

    def get(self, key: CacheKey) -> CacheEntry | None:
        self.get_keys.append(key)
        return self.entries.get(key)

    def put(self, entry: CacheEntry) -> bool:
        self.put_entries.append(entry)
        self.entries[entry.key] = entry
        return True

    def invalidate(self, normalized_url: str) -> int:
        key = CacheKey(method="GET", normalized_url=normalized_url)
        return int(self.entries.pop(key, None) is not None)

    def byte_size(self) -> int:
        return sum(len(entry.body) for entry in self.entries.values())

    def close(self) -> None:
        return None


class FakeCookieJar:
    def __init__(self, header: CookieHeader | None = None) -> None:
        self.header = header or CookieHeader(value=None, notice=None)
        self.stored: list[tuple[ParsedUrl, tuple[str, ...]]] = []

    def store_from_headers(
        self,
        url: ParsedUrl,
        set_cookie_values: tuple[str, ...],
    ) -> None:
        self.stored.append((url, set_cookie_values))

    def header_for(self, url: ParsedUrl) -> CookieHeader:
        return self.header

    def snapshot(self) -> tuple[Cookie, ...]:
        return ()

    def clear_expired(self) -> int:
        return 0

    def total_bytes(self) -> int:
        return 0


def response(
    status: int = 200,
    body: bytes = b"body",
    headers: HeaderFields | None = None,
    reason: str = "OK",
) -> bytes:
    fields = list(
        headers
        if headers is not None
        else (
            ("Content-Type", "text/html"),
            ("Content-Length", str(len(body))),
        )
    )
    rendered = f"HTTP/1.1 {status} {reason}\r\n"
    rendered += "".join(f"{name}: {value}\r\n" for name, value in fields)
    return rendered.encode("latin-1") + b"\r\n" + body


def stale_entry(
    url: str = "http://example.com/path?x=1",
    body: bytes = b"cached",
    headers: HeaderFields = (
        ("Content-Type", "text/html"),
        ("Cache-Control", "max-age=0"),
        ("ETag", "\"old\""),
        ("Last-Modified", "Thu, 01 Jan 1970 00:00:00 GMT"),
    ),
) -> CacheEntry:
    result = build_entry(
        CacheKey(method="GET", normalized_url=url),
        200,
        "GET",
        headers,
        body,
        100.0,
        LIMITS,
    )
    assert result is not None
    return result


def request(
    method: str = "GET",
    url: str = "http://example.com/path?x=1",
    headers: HeaderFields = (),
    body: bytes = b"",
    content_type: str | None = None,
) -> HttpRequest:
    return HttpRequest.model_validate(
        {
            "method": method,
            "url": url,
            "headers": headers,
            "body": body,
            "content_type": content_type,
        }
    )


def make_client(
    transport: ScriptedTransport,
    clock: FakeClock,
    cache: FakeCache | None = None,
    cookie_jar: FakeCookieJar | None = None,
    limits: Limits = LIMITS,
) -> HttpClientImpl:
    return HttpClientImpl(limits, transport, clock, cache, cookie_jar)


def test_ast_import_boundaries() -> None:
    source_path = Path(__file__).parents[1] / "src" / "terminal_browser" / "net" / "http.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    allowed_absolute = {
        "ast",
        "collections",
        "dataclasses",
        "socket",
        "ssl",
        "typing",
        "zlib",
        "pydantic",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name.split(".")[0] in allowed_absolute for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                assert node.module is not None
                assert node.module.split(".")[0] in allowed_absolute
            elif node.level == 1:
                assert node.module is not None
                assert node.module.split(".")[0] in {
                    "cache",
                    "cookies",
                    "transport",
                    "wire",
                }
            else:
                assert node.level == 2
                assert node.module is not None
                assert node.module.split(".")[0] in {"core", "url"}


def test_request_header_deterministic_order() -> None:
    clock = FakeClock(0.0, 100.0)
    transport = ScriptedTransport((response(body=b"ok"),), clock)
    client = make_client(transport, clock)
    result = client.request(
        request(headers=(("X-Zed", "z"), ("X-Alpha", "a"))),
        clock.now_monotonic() + 10.0,
    )
    assert result.status == 200
    head, body = transport.sent[0].split(b"\r\n\r\n", 1)
    assert body == b""
    assert head.split(b"\r\n") == [
        b"GET /path?x=1 HTTP/1.1",
        b"Host: example.com",
        b"User-Agent: terminal-browser/2",
        b"Accept: text/html, text/plain;q=0.9, */*;q=0.1",
        b"Accept-Encoding: gzip, deflate",
        b"Connection: close",
        b"X-Zed: z",
        b"X-Alpha: a",
    ]


def test_cache_hit_fresh_bypasses_transport() -> None:
    clock = FakeClock(0.0, 100.0)
    key = CacheKey(method="GET", normalized_url="http://example.com/path?x=1")
    entry = build_entry(
        key,
        200,
        "GET",
        (("Content-Type", "text/html"), ("Cache-Control", "max-age=60")),
        b"cached",
        100.0,
        LIMITS,
    )
    assert entry is not None
    cache = FakeCache((entry,))
    transport = ScriptedTransport(clock=clock)
    result = make_client(transport, clock, cache).request(
        request(),
        clock.now_monotonic() + 10.0,
    )
    assert result.body == b"cached"
    assert result.from_cache is True
    assert transport.connect_calls == 0


def test_cache_miss_fetches_and_stores() -> None:
    clock = FakeClock(0.0, 100.0)
    transport = ScriptedTransport(
        (
            response(
                headers=(
                    ("Content-Type", "text/html"),
                    ("Cache-Control", "max-age=60"),
                    ("Content-Length", "2"),
                ),
                body=b"ok",
            ),
        ),
        clock,
    )
    cache = FakeCache()
    result = make_client(transport, clock, cache).request(
        request(),
        clock.now_monotonic() + 10.0,
    )
    assert result.body == b"ok"
    assert result.from_cache is False
    assert transport.connect_calls == 1
    assert len(cache.put_entries) == 1
    assert cache.put_entries[0].body == b"ok"


def test_gzip_deflate_decompression_and_limits() -> None:
    body = b"decompressed body"
    for coding, compressed in (
        ("gzip", zlib.compress(body, wbits=16 + zlib.MAX_WBITS)),
        ("deflate", zlib.compress(body)),
    ):
        clock = FakeClock(0.0, 100.0)
        wire = response(
            body=compressed,
            headers=(
                ("Content-Type", "text/html"),
                ("Content-Encoding", coding),
                ("Content-Length", str(len(compressed))),
            ),
        )
        transport = ScriptedTransport((wire,), clock)
        result = make_client(transport, clock).request(
            request(),
            clock.now_monotonic() + 10.0,
        )
        assert result.body == body

        limited_clock = FakeClock(0.0, 100.0)
        limited_transport = ScriptedTransport((wire,), limited_clock)
        with pytest.raises(DecompressionError):
            make_client(
                limited_transport,
                limited_clock,
                limits=make_limits(max_decompressed_bytes=3),
            ).request(request(), limited_clock.now_monotonic() + 10.0)


def test_total_response_timeout_enforced() -> None:
    clock = FakeClock(0.0, 100.0)
    body = b"x" * 20_000
    transport = ScriptedTransport((response(body=body),), clock, read_delay=1.5)
    client = make_client(
        transport,
        clock,
        limits=make_limits(
            total_response_timeout_sec=2.0,
            read_timeout_sec=2.0,
            max_body_bytes=40_000,
            chunk_read_size=1_024,
        ),
    )
    with pytest.raises(ResponseTimeoutError):
        client.request(request(), clock.now_monotonic() + 100.0)


def test_chunked_vs_content_length_dispatch() -> None:
    body = b"same body"
    content_length_wire = response(body=body)
    chunked_wire = response(
        body=b"4\r\nsame\r\n5\r\n body\r\n0\r\nX-Trailer: yes\r\n\r\n",
        headers=(
            ("Content-Type", "text/html"),
            ("Transfer-Encoding", "chunked"),
        ),
    )
    for wire, expected_trailer in ((content_length_wire, False), (chunked_wire, True)):
        clock = FakeClock(0.0, 100.0)
        transport = ScriptedTransport((wire,), clock)
        result = make_client(transport, clock).request(
            request(),
            clock.now_monotonic() + 10.0,
        )
        assert result.body == body
        assert (("x-trailer", "yes") in result.headers) is expected_trailer


def test_cookie_header_injection() -> None:
    clock = FakeClock(0.0, 100.0)
    jar = FakeCookieJar(CookieHeader(value="sid=abc", notice=None))
    transport = ScriptedTransport(
        (
            response(
                headers=(
                    ("Content-Type", "text/html"),
                    ("Set-Cookie", "next=1; Path=/"),
                    ("Content-Length", "2"),
                ),
                body=b"ok",
            ),
        ),
        clock,
    )
    result = make_client(transport, clock, cookie_jar=jar).request(
        request(),
        clock.now_monotonic() + 10.0,
    )
    assert result.status == 200
    assert b"Cookie: sid=abc" in transport.sent[0]
    assert jar.stored[0][1] == ("next=1; Path=/",)


def test_4xx_5xx_returned_as_normal_responses() -> None:
    for status in (404, 500):
        clock = FakeClock(0.0, 100.0)
        transport = ScriptedTransport((response(status=status, body=b"error"),), clock)
        result = make_client(transport, clock).request(
            request(),
            clock.now_monotonic() + 10.0,
        )
        assert result.status == status
        assert result.body == b"error"


def test_3xx_returned_without_redirect() -> None:
    clock = FakeClock(0.0, 100.0)
    transport = ScriptedTransport(
        (
            response(
                status=300,
                body=b"redirect",
                headers=(
                    ("Location", "/next"),
                    ("Content-Type", "text/plain"),
                    ("Content-Length", "8"),
                ),
                reason="Multiple Choices",
            ),
        ),
        clock,
    )
    result = make_client(transport, clock).request(
        request(),
        clock.now_monotonic() + 10.0,
    )
    assert result.status == 300
    assert result.body == b"redirect"
    assert result.redirect_chain == ()
    assert transport.connect_calls == 1


def test_redirect_301_302_303_changes_post_to_get() -> None:
    for status in (301, 302, 303):
        clock = FakeClock(0.0, 100.0)
        transport = ScriptedTransport(
            (
                response(
                    status=status,
                    body=b"redirect",
                    headers=(
                        ("Location", "/next"),
                        ("Content-Type", "text/plain"),
                        ("Content-Length", "8"),
                    ),
                    reason="Redirect",
                ),
                response(body=b"final"),
            ),
            clock,
        )
        result = make_client(transport, clock).request(
            request(
                method="POST",
                body=b"a=b",
                content_type="application/x-www-form-urlencoded",
            ),
            clock.now_monotonic() + 10.0,
        )
        assert result.status == 200
        assert result.redirect_chain == ("http://example.com/path?x=1",)
        assert transport.sent[0].startswith(b"POST /path?x=1 HTTP/1.1\r\n")
        assert transport.sent[0].endswith(b"\r\n\r\na=b")
        assert transport.sent[1].startswith(b"GET /next HTTP/1.1\r\n")
        assert transport.sent[1].endswith(b"\r\n\r\n")
        assert b"Content-Type:" not in transport.sent[1]
        assert b"Content-Length:" not in transport.sent[1]


def test_redirect_307_308_preserves_post_and_body() -> None:
    for status in (307, 308):
        clock = FakeClock(0.0, 100.0)
        transport = ScriptedTransport(
            (
                response(
                    status=status,
                    body=b"redirect",
                    headers=(
                        ("Location", "/next"),
                        ("Content-Type", "text/plain"),
                        ("Content-Length", "8"),
                    ),
                    reason="Redirect",
                ),
                response(body=b"final"),
            ),
            clock,
        )
        result = make_client(transport, clock).request(
            request(
                method="POST",
                body=b"a=b",
                content_type="application/x-www-form-urlencoded",
            ),
            clock.now_monotonic() + 10.0,
        )
        assert result.status == 200
        assert result.redirect_chain == ("http://example.com/path?x=1",)
        assert transport.sent[1].startswith(b"POST /next HTTP/1.1\r\n")
        assert b"Content-Type: application/x-www-form-urlencoded" in transport.sent[1]
        assert b"Content-Length: 3" in transport.sent[1]
        assert transport.sent[1].endswith(b"\r\n\r\na=b")


def test_redirect_max_hops_raises_too_many_redirects() -> None:
    clock = FakeClock(0.0, 100.0)
    transport = ScriptedTransport(
        (
            response(
                status=302,
                body=b"",
                headers=(("Location", "/one"), ("Content-Length", "0")),
                reason="Found",
            ),
            response(
                status=302,
                body=b"",
                headers=(("Location", "/two"), ("Content-Length", "0")),
                reason="Found",
            ),
            response(body=b"never"),
        ),
        clock,
    )
    with pytest.raises(TooManyRedirectsError):
        make_client(transport, clock, limits=make_limits(max_redirects=1)).request(
            request(),
            clock.now_monotonic() + 10.0,
        )
    assert transport.connect_calls == 2


def test_redirect_https_to_http_downgrade_refused() -> None:
    clock = FakeClock(0.0, 100.0)
    transport = ScriptedTransport(
        (
            response(
                status=302,
                body=b"",
                headers=(
                    ("Location", "http://example.com/next"),
                    ("Content-Length", "0"),
                ),
                reason="Found",
            ),
        ),
        clock,
    )
    with pytest.raises(RedirectError):
        make_client(transport, clock).request(
            request(url="https://example.com/path"),
            clock.now_monotonic() + 10.0,
        )


def test_redirect_unsupported_scheme_raises_error() -> None:
    for location in ("javascript:alert(1)", "data:text/plain,x"):
        clock = FakeClock(0.0, 100.0)
        transport = ScriptedTransport(
            (
                response(
                    status=302,
                    body=b"",
                    headers=(("Location", location), ("Content-Length", "0")),
                    reason="Found",
                ),
            ),
            clock,
        )
        with pytest.raises(UnsupportedSchemeError):
            make_client(transport, clock).request(
                request(),
                clock.now_monotonic() + 10.0,
            )


def test_redirect_chain_populated_in_response() -> None:
    clock = FakeClock(0.0, 100.0)
    transport = ScriptedTransport(
        (
            response(
                status=302,
                body=b"",
                headers=(("Location", "/two"), ("Content-Length", "0")),
                reason="Found",
            ),
            response(
                status=307,
                body=b"",
                headers=(("Location", "/final"), ("Content-Length", "0")),
                reason="Temporary Redirect",
            ),
            response(body=b"final"),
        ),
        clock,
    )
    result = make_client(transport, clock).request(
        request(url="http://example.com/start"),
        clock.now_monotonic() + 10.0,
    )
    assert result.url == "http://example.com/final"
    assert result.redirect_chain == (
        "http://example.com/start",
        "http://example.com/two",
    )


def test_conditional_get_sends_etag_and_last_modified() -> None:
    clock = FakeClock(0.0, 100.0)
    cache = FakeCache((stale_entry(),))
    transport = ScriptedTransport((response(body=b"new"),), clock)
    result = make_client(transport, clock, cache).request(
        request(),
        clock.now_monotonic() + 10.0,
    )
    assert result.status == 200
    assert b"If-None-Match: \"old\"" in transport.sent[0]
    assert b"If-Modified-Since: Thu, 01 Jan 1970 00:00:00 GMT" in transport.sent[0]


def test_304_revalidation_merges_and_updates_cache() -> None:
    clock = FakeClock(0.0, 100.0)
    cache = FakeCache((stale_entry(),))
    transport = ScriptedTransport(
        (
            response(
                status=304,
                body=b"",
                headers=(
                    ("ETag", "\"new\""),
                    ("Cache-Control", "max-age=60"),
                    ("Date", "Thu, 01 Jan 1970 00:01:40 GMT"),
                ),
                reason="Not Modified",
            ),
        ),
        clock,
    )
    result = make_client(transport, clock, cache).request(
        request(),
        clock.now_monotonic() + 10.0,
    )
    assert result.status == 200
    assert result.body == b"cached"
    assert result.from_cache is True
    assert result.revalidated is True
    assert ("etag", "\"new\"") in result.headers
    assert any(
        name.lower() == "content-type" and value == "text/html"
        for name, value in result.headers
    )
    assert len(cache.put_entries) == 1
    assert cache.put_entries[0].body == b"cached"
    assert cache.put_entries[0].stored_at_epoch == 100.0
    assert cache.put_entries[0].fresh_until_epoch == 160.0


def test_unsolicited_304_returns_empty_with_notice() -> None:
    clock = FakeClock(0.0, 100.0)
    transport = ScriptedTransport(
        (response(status=304, body=b"", reason="Not Modified"),),
        clock,
    )
    result = make_client(transport, clock).request(
        request(),
        clock.now_monotonic() + 10.0,
    )
    assert result.status == 304
    assert result.body == b""
    assert "[notice] not modified without cached content" in result.notices


def test_redirect_ambiguous_framing_raises_protocol_error() -> None:
    clock = FakeClock(0.0, 100.0)
    transport = ScriptedTransport(
        (
            response(
                status=302,
                body=b"",
                headers=(
                    ("Location", "/next"),
                    ("Content-Length", "0"),
                    ("Transfer-Encoding", "chunked"),
                ),
                reason="Found",
            ),
        ),
        clock,
    )
    with pytest.raises(ProtocolError):
        make_client(transport, clock).request(
            request(),
            clock.now_monotonic() + 10.0,
        )
