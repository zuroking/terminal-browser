from collections.abc import Iterator
from dataclasses import dataclass
import socket
import ssl
from typing import Literal, Protocol
import zlib

from pydantic import BaseModel, ConfigDict

from ..core.clock import Clock
from ..core.errors import (
    BodyTooLargeError,
    DecompressionError,
    HeaderTooLargeError,
    InvalidUrlError,
    NavigationTimeoutError,
    ProtocolError,
    RedirectError,
    ResponseTimeoutError,
    TooManyRedirectsError,
    TruncatedBodyError,
    UnsupportedEncodingError,
    UnsupportedSchemeError,
)
from ..core.limits import Limits
from ..url import ParsedUrl, UrlParser, UrlParserImpl
from .cache import (
    Cache,
    CacheEntry,
    CacheKey,
    build_entry,
    compute_fresh_until_epoch,
    parse_http_date,
)
from .cookies import CookieHeader, CookieJar
from .transport import TcpTarget, TlsPolicy, Transport
from .wire import HeaderFields, StatusLine, decode_chunked, parse_headers, parse_status_line


_RESERVED_REQUEST_HEADERS = frozenset(
    {
        "host",
        "user-agent",
        "accept",
        "accept-encoding",
        "connection",
        "cookie",
        "content-type",
        "content-length",
        "transfer-encoding",
        "if-none-match",
        "if-modified-since",
    }
)
_TOKEN_CHARS = frozenset(
    "!#$%&'*+-.^_`|~"
    "0123456789"
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
)
_POST_CONTENT_TYPE = "application/x-www-form-urlencoded"


class HttpRequest(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    method: Literal["GET", "POST"]
    url: str
    headers: HeaderFields
    body: bytes
    content_type: str | None


class HttpResponse(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    url: str
    status: int
    reason: str
    headers: HeaderFields
    body: bytes
    redirect_chain: tuple[str, ...]
    from_cache: bool
    revalidated: bool
    notices: tuple[str, ...]


class HttpClient(Protocol):
    def request(
        self,
        request: HttpRequest,
        navigation_deadline: float,
    ) -> HttpResponse: ...


def _header_values(headers: HeaderFields, name: str) -> tuple[str, ...]:
    return tuple(value for field_name, value in headers if field_name.lower() == name)


def _valid_request_header(name: str, value: str) -> bool:
    return (
        bool(name)
        and all(character in _TOKEN_CHARS for character in name)
        and all(
            character == "\t"
            or 0x20 <= ord(character) <= 0x7E
            or 0x80 <= ord(character) <= 0xFF
            for character in value
        )
    )


def _content_type_notice(headers: HeaderFields) -> str | None:
    values = _header_values(headers, "content-type")
    if not values:
        return "[notice] unsupported content type: <missing>"
    media_type = values[0].split(";", 1)[0].strip().lower()
    if media_type in {"text/html", "text/plain"}:
        return None
    if not media_type:
        media_type = "<malformed>"
    return f"[notice] unsupported content type: {media_type}"


def _build_request_headers(
    request: HttpRequest,
    parsed_url: ParsedUrl,
    cookie_header: CookieHeader,
    limits: Limits,
    conditional_headers: tuple[tuple[str, str], ...] = (),
) -> HeaderFields:
    if request.method == "GET" and (request.body or request.content_type is not None):
        raise ProtocolError("GET requests cannot carry a body or content type")
    if request.method == "POST":
        if request.content_type != _POST_CONTENT_TYPE:
            raise ProtocolError("POST content type is not supported")
        if len(request.body) > limits.max_form_bytes:
            raise BodyTooLargeError("request body exceeds max_form_bytes")
    custom_headers: list[tuple[str, str]] = []
    seen: set[str] = set()
    for name, value in request.headers:
        lowered = name.lower()
        if lowered in _RESERVED_REQUEST_HEADERS or lowered in seen:
            raise ProtocolError("reserved or duplicate request header")
        if not _valid_request_header(name, value):
            raise ProtocolError("invalid request header")
        seen.add(lowered)
        custom_headers.append((name, value))
    host = f"[{parsed_url.host}]" if ":" in parsed_url.host else parsed_url.host
    if parsed_url.port not in {80, 443}:
        host = f"{host}:{parsed_url.port}"
    headers: list[tuple[str, str]] = [
        ("Host", host),
        ("User-Agent", "terminal-browser/2"),
        ("Accept", "text/html, text/plain;q=0.9, */*;q=0.1"),
        ("Accept-Encoding", "gzip, deflate"),
        ("Connection", "close"),
    ]
    if cookie_header.value is not None:
        headers.append(("Cookie", cookie_header.value))
    headers.extend(conditional_headers)
    headers.extend(custom_headers)
    if request.method == "POST":
        headers.append(("Content-Type", _POST_CONTENT_TYPE))
        headers.append(("Content-Length", str(len(request.body))))
    return tuple(headers)


def _response_notices(status: int, headers: HeaderFields) -> tuple[str, ...]:
    notices: list[str] = []
    if status == 204:
        notices.append("[notice] no content")
    elif status == 205:
        notices.append("[notice] reset content")
    elif status == 304:
        notices.append("[notice] not modified without cached content")
    else:
        content_type_notice = _content_type_notice(headers)
        if content_type_notice is not None:
            notices.append(content_type_notice)
    return tuple(notices)


@dataclass(frozen=True, slots=True)
class _NetworkResponse:
    status: StatusLine
    headers: HeaderFields
    body: bytes
    received_at_epoch: float
    cookie_notice: str | None


def _has_cache_directive(headers: HeaderFields, directive_name: str) -> bool:
    for value in _header_values(headers, "cache-control"):
        for part in value.split(";"):
            name = part.partition("=")[0].strip().lower()
            if name == directive_name:
                return True
    return False


def _valid_nonnegative_integer(value: str | None) -> int | None:
    if value is None:
        return None
    text = value.strip()
    if not text.isascii() or not text.isdigit():
        return None
    return int(text)


def _merge_304_headers(
    stored_headers: HeaderFields,
    response_headers: HeaderFields,
) -> HeaderFields:
    usable_response_headers = tuple(
        (name, value)
        for name, value in response_headers
        if name.lower() != "date" or parse_http_date(value) is not None
    )
    supplied_names = {name.lower() for name, _value in usable_response_headers}
    return tuple(
        (name, value)
        for name, value in stored_headers
        if name.lower() not in supplied_names
    ) + usable_response_headers


def _conditional_headers(entry: CacheEntry | None) -> tuple[tuple[str, str], ...]:
    if entry is None:
        return ()
    headers: list[tuple[str, str]] = []
    if entry.etag is not None:
        headers.append(("If-None-Match", entry.etag))
    if entry.last_modified is not None:
        headers.append(("If-Modified-Since", entry.last_modified))
    return tuple(headers)


def _redirect_request(
    request: HttpRequest,
    next_url: str,
    status: int,
) -> HttpRequest:
    method: Literal["GET", "POST"] = request.method
    body = request.body
    content_type = request.content_type
    if status in {301, 302, 303} and method == "POST":
        method = "GET"
        body = b""
        content_type = None
    return HttpRequest(
        method=method,
        url=next_url,
        headers=request.headers,
        body=body,
        content_type=content_type,
    )


class HttpClientImpl:
    def __init__(
        self,
        limits: Limits,
        transport: Transport,
        clock: Clock,
        cache: Cache | None = None,
        cookie_jar: CookieJar | None = None,
        url_parser: UrlParser | None = None,
        tls_policy: TlsPolicy | None = None,
    ) -> None:
        self._limits = limits
        self._transport = transport
        self._clock = clock
        self._cache = cache
        self._cookie_jar = cookie_jar
        self._url_parser = url_parser or UrlParserImpl(limits)
        self._tls_policy = tls_policy or TlsPolicy(
            min_tls_version=ssl.TLSVersion.TLSv1_2
        )

    def _read_remaining(self, deadline: float) -> float:
        current = self._clock.now_monotonic()
        remaining = min(deadline, current + self._limits.read_timeout_sec) - current
        if remaining <= 0:
            raise ResponseTimeoutError("response deadline exhausted")
        return remaining

    def _navigation_remaining(self, deadline: float) -> float:
        remaining = deadline - self._clock.now_monotonic()
        if remaining <= 0:
            raise NavigationTimeoutError("navigation deadline exhausted")
        return remaining

    def _response_deadline(self, navigation_deadline: float) -> float:
        return min(
            navigation_deadline,
            self._clock.now_monotonic() + self._limits.total_response_timeout_sec,
        )

    def _recv(
        self,
        sock: socket.socket,
        max_bytes: int,
        deadline: float,
    ) -> bytes:
        if max_bytes <= 0:
            raise HeaderTooLargeError("response header exceeds max_header_size")
        read_deadline = min(
            deadline,
            self._clock.now_monotonic() + self._limits.read_timeout_sec,
        )
        remaining = read_deadline - self._clock.now_monotonic()
        if remaining <= 0:
            raise ResponseTimeoutError("read deadline exhausted")
        data = self._transport.recv_bounded(
            sock,
            max_bytes=max_bytes,
            remaining_sec=remaining,
            chunk_size=min(self._limits.chunk_read_size, max_bytes),
        )
        if self._clock.now_monotonic() >= read_deadline:
            raise ResponseTimeoutError("read deadline exhausted")
        return data

    def _read_one_head(
        self,
        sock: socket.socket,
        pending: bytearray,
        deadline: float,
    ) -> tuple[StatusLine, HeaderFields, bytearray]:
        while b"\r\n\r\n" not in pending:
            if len(pending) > self._limits.max_header_size:
                raise HeaderTooLargeError("response header exceeds max_header_size")
            data = self._recv(
                sock,
                self._limits.max_header_size + 4 - len(pending),
                deadline,
            )
            if not data:
                raise TruncatedBodyError("response headers ended before CRLF")
            pending.extend(data)
        head, body = bytes(pending).split(b"\r\n\r\n", 1)
        line_end = head.find(b"\r\n")
        if line_end < 0:
            raise ProtocolError("response status line is not terminated")
        status = parse_status_line(head[: line_end + 2], self._limits)
        headers = parse_headers(head[line_end + 2 :] + b"\r\n", self._limits)
        pending.clear()
        pending.extend(body)
        return status, headers, pending

    def _read_head(
        self,
        sock: socket.socket,
        pending: bytearray,
        deadline: float,
    ) -> tuple[StatusLine, HeaderFields, bytearray]:
        interim_count = 0
        while True:
            status, headers, pending = self._read_one_head(sock, pending, deadline)
            if not 100 <= status.status <= 199:
                return status, headers, pending
            if status.status == 101:
                raise UnsupportedSchemeError("HTTP switching protocols is unsupported")
            if 104 <= status.status <= 199:
                raise ProtocolError("unsupported interim response status")
            content_lengths = _header_values(headers, "content-length")
            transfer_encodings = _header_values(headers, "transfer-encoding")
            if content_lengths or transfer_encodings:
                raise ProtocolError("interim response has body framing")
            interim_count += 1
            if interim_count > self._limits.max_interim_responses:
                raise ProtocolError("too many interim responses")

    def _read_exact(
        self,
        sock: socket.socket,
        length: int,
        pending: bytearray,
        deadline: float,
    ) -> bytes:
        output = bytearray(pending[:length])
        del pending[:length]
        while len(output) < length:
            data = self._recv(sock, length - len(output), deadline)
            if not data:
                raise TruncatedBodyError("response body ended before Content-Length")
            output.extend(data)
        return bytes(output)

    def _read_until_eof(
        self,
        sock: socket.socket,
        pending: bytearray,
        deadline: float,
    ) -> bytes:
        output = bytearray(pending)
        pending.clear()
        while True:
            if len(output) > self._limits.max_body_bytes:
                raise BodyTooLargeError("response body exceeds max_body_bytes")
            data = self._recv(
                sock,
                self._limits.max_body_bytes - len(output) + 1,
                deadline,
            )
            if not data:
                return bytes(output)
            output.extend(data)

    def _body_chunks(
        self,
        sock: socket.socket,
        pending: bytearray,
        deadline: float,
    ) -> Iterator[bytes]:
        if pending:
            yield bytes(pending)
            pending.clear()
        while True:
            data = self._recv(sock, self._limits.chunk_read_size, deadline)
            if not data:
                return
            yield data

    def _decompress(self, body: bytes, content_encoding: str) -> bytes:
        if content_encoding in {"", "identity"}:
            return body
        if content_encoding == "gzip":
            return self._inflate(body, 16 + zlib.MAX_WBITS)
        if content_encoding == "deflate":
            try:
                return self._inflate(body, zlib.MAX_WBITS)
            except DecompressionError:
                return self._inflate(body, -zlib.MAX_WBITS)
        raise UnsupportedEncodingError("unsupported response content encoding")

    def _inflate(self, body: bytes, window_bits: int) -> bytes:
        decompressor = zlib.decompressobj(window_bits)
        output = bytearray()
        pending = body
        while pending:
            remaining = self._limits.max_decompressed_bytes - len(output)
            if remaining <= 0:
                raise DecompressionError("decompressed body exceeds max_decompressed_bytes")
            try:
                chunk = decompressor.decompress(pending, remaining + 1)
            except zlib.error as error:
                raise DecompressionError("response decompression failed") from error
            if len(chunk) > remaining:
                raise DecompressionError("decompressed body exceeds max_decompressed_bytes")
            output.extend(chunk)
            pending = decompressor.unconsumed_tail
        try:
            final = decompressor.flush(
                self._limits.max_decompressed_bytes - len(output) + 1
            )
        except zlib.error as error:
            raise DecompressionError("response decompression failed") from error
        if len(output) + len(final) > self._limits.max_decompressed_bytes:
            raise DecompressionError("decompressed body exceeds max_decompressed_bytes")
        output.extend(final)
        if not decompressor.eof:
            raise DecompressionError("response decompression ended before EOF")
        return bytes(output)

    def _cache_key(self, parsed_url: ParsedUrl) -> CacheKey:
        return CacheKey(
            method="GET",
            normalized_url=self._url_parser.normalize_for_cache(parsed_url),
        )

    def _read_body(
        self,
        sock: socket.socket,
        status: StatusLine,
        headers: HeaderFields,
        pending: bytearray,
        deadline: float,
    ) -> tuple[bytes, HeaderFields]:
        content_lengths = _header_values(headers, "content-length")
        transfer_encodings = _header_values(headers, "transfer-encoding")
        if len(content_lengths) > 1 or len(transfer_encodings) > 1:
            raise ProtocolError("duplicate framing header")
        if content_lengths and transfer_encodings:
            raise ProtocolError("ambiguous response framing")
        if status.version == "HTTP/1.0" and transfer_encodings:
            raise ProtocolError("Transfer-Encoding is invalid on HTTP/1.0")
        if status.status in {204, 205} and (content_lengths or transfer_encodings):
            raise ProtocolError("no-content response has body framing")
        if status.status == 304 and transfer_encodings:
            raise ProtocolError("Transfer-Encoding is invalid on 304")
        if status.status in {204, 205, 304}:
            return b"", headers
        if transfer_encodings:
            if transfer_encodings[0].strip().lower() != "chunked":
                raise ProtocolError("unsupported transfer coding")
            body, trailers = decode_chunked(
                self._body_chunks(sock, pending, deadline),
                self._limits,
            )
            return body, headers + trailers
        if content_lengths:
            value = content_lengths[0].strip()
            if not value.isascii() or not value.isdigit():
                raise ProtocolError("invalid Content-Length")
            content_length = int(value)
            if content_length > self._limits.max_body_bytes:
                raise BodyTooLargeError("response body exceeds max_body_bytes")
            return self._read_exact(sock, content_length, pending, deadline), headers
        return self._read_until_eof(sock, pending, deadline), headers

    def _fetch(
        self,
        request: HttpRequest,
        parsed_url: ParsedUrl,
        navigation_deadline: float,
        conditional_headers: tuple[tuple[str, str], ...],
    ) -> _NetworkResponse:
        cookie_header = CookieHeader(value=None, notice=None)
        if self._cookie_jar is not None:
            cookie_header = self._cookie_jar.header_for(parsed_url)
        request_headers = _build_request_headers(
            request,
            parsed_url,
            cookie_header,
            self._limits,
            conditional_headers,
        )
        origin = parsed_url.path or "/"
        if parsed_url.raw_query:
            origin = f"{origin}?{parsed_url.raw_query}"
        wire_lines = [f"{request.method} {origin} HTTP/1.1"]
        wire_lines.extend(f"{name}: {value}" for name, value in request_headers)
        wire = ("\r\n".join(wire_lines) + "\r\n\r\n").encode("latin-1")
        if request.body:
            wire += request.body
        target = TcpTarget(
            host=parsed_url.host,
            port=parsed_url.port,
            use_tls=parsed_url.scheme == "https",
        )
        response_deadline = self._response_deadline(navigation_deadline)
        sock = self._transport.connect(
            target,
            self._navigation_remaining(response_deadline),
        )
        pending = bytearray()
        try:
            if target.use_tls:
                sock = self._transport.upgrade_to_tls(
                    sock,
                    target,
                    self._tls_policy,
                    self._read_remaining(response_deadline),
                )
            self._transport.send_all(
                sock,
                wire,
                self._read_remaining(response_deadline),
            )
            if self._clock.now_monotonic() >= response_deadline:
                raise ResponseTimeoutError("response deadline exhausted")
            status, headers, pending = self._read_head(
                sock,
                pending,
                response_deadline,
            )
            if self._cookie_jar is not None:
                self._cookie_jar.store_from_headers(
                    parsed_url,
                    _header_values(headers, "set-cookie"),
                )
            body, headers = self._read_body(
                sock,
                status,
                headers,
                pending,
                response_deadline,
            )
            if len(body) > self._limits.max_body_bytes:
                raise BodyTooLargeError("response body exceeds max_body_bytes")
            if status.status not in {204, 205, 304}:
                content_encodings = _header_values(headers, "content-encoding")
                if len(content_encodings) > 1:
                    raise ProtocolError("duplicate Content-Encoding")
                body = self._decompress(
                    body,
                    content_encodings[0].strip().lower()
                    if content_encodings
                    else "",
                )
            return _NetworkResponse(
                status=status,
                headers=headers,
                body=body,
                received_at_epoch=self._clock.now_epoch(),
                cookie_notice=cookie_header.notice,
            )
        finally:
            self._transport.close(sock)

    def _redirect_target(
        self,
        current_url: ParsedUrl,
        headers: HeaderFields,
    ) -> ParsedUrl:
        locations = _header_values(headers, "location")
        if not locations or not locations[0].strip():
            raise RedirectError("redirect Location is missing or empty")
        location = locations[0]
        scheme = self._url_parser.scheme_of(location)
        if scheme not in {"", "http", "https"}:
            raise UnsupportedSchemeError("redirect uses an unsupported URL scheme")
        try:
            target = self._url_parser.resolve(current_url, location)
        except InvalidUrlError as error:
            raise RedirectError("redirect Location is malformed") from error
        if current_url.scheme == "https" and target.scheme == "http":
            raise RedirectError("HTTPS to HTTP redirect refused")
        return target

    def _direct_response(
        self,
        parsed_url: ParsedUrl,
        network: _NetworkResponse,
        redirect_chain: tuple[str, ...],
    ) -> HttpResponse:
        notices: list[str] = []
        if network.cookie_notice is not None:
            notices.append(network.cookie_notice)
        notices.extend(_response_notices(network.status.status, network.headers))
        return HttpResponse(
            url=parsed_url.normalized_url,
            status=network.status.status,
            reason=network.status.reason,
            headers=network.headers,
            body=network.body,
            redirect_chain=redirect_chain,
            from_cache=False,
            revalidated=False,
            notices=tuple(notices),
        )

    def _revalidated_response(
        self,
        parsed_url: ParsedUrl,
        entry: CacheEntry,
        network: _NetworkResponse,
        redirect_chain: tuple[str, ...],
    ) -> HttpResponse:
        if _has_cache_directive(network.headers, "no-store") or _header_values(
            network.headers, "vary"
        ):
            if self._cache is not None:
                self._cache.invalidate(entry.key.normalized_url)
            return self._direct_response(parsed_url, network, redirect_chain)
        merged_headers = _merge_304_headers(entry.headers, network.headers)
        receive_time = network.received_at_epoch
        prior_age = entry.age_at_stored_epoch + max(
            0.0,
            receive_time - entry.stored_at_epoch,
        )
        supplied_age = _valid_nonnegative_integer(
            next(iter(_header_values(network.headers, "age")), None)
        )
        effective_date = parse_http_date(
            next(iter(_header_values(network.headers, "date")), None)
        )
        if effective_date is None:
            effective_date = parse_http_date(
                next(iter(_header_values(entry.headers, "date")), None)
            )
        apparent_age = (
            max(0.0, receive_time - effective_date)
            if effective_date is not None
            else 0.0
        )
        new_entry = CacheEntry(
            key=entry.key,
            status=200,
            headers=merged_headers,
            body=entry.body,
            stored_at_epoch=receive_time,
            fresh_until_epoch=(
                compute_fresh_until_epoch(merged_headers, receive_time)
                if _header_values(network.headers, "cache-control")
                else entry.fresh_until_epoch
            ),
            etag=next(
                iter(_header_values(network.headers, "etag")),
                entry.etag,
            ),
            last_modified=next(
                iter(_header_values(network.headers, "last-modified")),
                entry.last_modified,
            ),
            body_len=len(entry.body),
            age_at_stored_epoch=max(
                prior_age,
                float(supplied_age) if supplied_age is not None else 0.0,
                apparent_age,
            ),
        )
        if self._cache is not None:
            self._cache.put(new_entry)
        notices: list[str] = []
        if network.cookie_notice is not None:
            notices.append(network.cookie_notice)
        notices.extend(_response_notices(200, merged_headers))
        return HttpResponse(
            url=parsed_url.normalized_url,
            status=200,
            reason="OK",
            headers=merged_headers,
            body=entry.body,
            redirect_chain=redirect_chain,
            from_cache=True,
            revalidated=True,
            notices=tuple(notices),
        )

    def _response_from_cache(
        self,
        entry: CacheEntry,
        parsed_url: ParsedUrl,
        redirect_chain: tuple[str, ...],
    ) -> HttpResponse:
        return HttpResponse(
            url=parsed_url.normalized_url,
            status=entry.status,
            reason="OK",
            headers=entry.headers,
            body=entry.body,
            redirect_chain=redirect_chain,
            from_cache=True,
            revalidated=False,
            notices=_response_notices(entry.status, entry.headers),
        )

    def request(
        self,
        request: HttpRequest,
        navigation_deadline: float,
    ) -> HttpResponse:
        self._navigation_remaining(navigation_deadline)
        current_request = request
        redirect_chain: list[str] = []
        redirect_count = 0
        while True:
            self._navigation_remaining(navigation_deadline)
            parsed_url = self._url_parser.parse(current_request.url)
            stale_entry: CacheEntry | None = None
            if current_request.method == "GET" and self._cache is not None:
                cached = self._cache.get(self._cache_key(parsed_url))
                if cached is not None:
                    now = self._clock.now_epoch()
                    if (
                        cached.fresh_until_epoch is not None
                        and cached.fresh_until_epoch > now
                    ):
                        return self._response_from_cache(
                            cached,
                            parsed_url,
                            tuple(redirect_chain),
                        )
                    stale_entry = cached
            network = self._fetch(
                current_request,
                parsed_url,
                navigation_deadline,
                _conditional_headers(stale_entry),
            )
            status = network.status.status
            if status in {301, 302, 303, 307, 308}:
                target = self._redirect_target(parsed_url, network.headers)
                if redirect_count >= self._limits.max_redirects:
                    raise TooManyRedirectsError("redirect chain exceeded max_redirects")
                redirect_count += 1
                redirect_chain.append(parsed_url.normalized_url)
                current_request = _redirect_request(
                    current_request,
                    target.normalized_url,
                    status,
                )
                continue
            if status == 304:
                if stale_entry is not None:
                    return self._revalidated_response(
                        parsed_url,
                        stale_entry,
                        network,
                        tuple(redirect_chain),
                    )
                return self._direct_response(
                    parsed_url,
                    network,
                    tuple(redirect_chain),
                )
            if self._cache is not None and current_request.method == "GET":
                cache_entry = build_entry(
                    self._cache_key(parsed_url),
                    status,
                    current_request.method,
                    network.headers,
                    network.body,
                    network.received_at_epoch,
                    self._limits,
                )
                if cache_entry is not None:
                    self._cache.put(cache_entry)
            return self._direct_response(
                parsed_url,
                network,
                tuple(redirect_chain),
            )
