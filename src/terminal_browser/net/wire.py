"""Pure HTTP/1.1 wire parsing; stored header names are lowercased."""

from collections.abc import Iterator
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ..core.errors import (
    BodyTooLargeError,
    HeaderTooLargeError,
    ProtocolError,
    TruncatedBodyError,
)
from ..core.limits import Limits


HeaderFields = tuple[tuple[str, str], ...]
_SINGLETON_FIELDS = frozenset(
    {
        "location",
        "content-type",
        "content-encoding",
        "etag",
        "last-modified",
        "age",
        "date",
        "expires",
    }
)
_TOKEN_BYTES = frozenset(
    b"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!#$%&'*+-.^_`|~"
)
_REASON_BYTES = frozenset(range(0x20, 0x7F)) | {0x09} | set(range(0x80, 0x100))


class StatusLine(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    version: Literal["HTTP/1.0", "HTTP/1.1"]
    status: int
    reason: str


def _check_crlf(raw: bytes) -> None:
    for index, value in enumerate(raw):
        if value == 0x0A and (index == 0 or raw[index - 1] != 0x0D):
            raise ProtocolError("bare LF in wire data")
        if value == 0x0D and (index + 1 == len(raw) or raw[index + 1] != 0x0A):
            raise ProtocolError("bare CR in wire data")


def parse_status_line(raw: bytes, limits: Limits) -> StatusLine:
    if len(raw) > limits.max_header_size:
        raise HeaderTooLargeError("status line exceeds max_header_size")
    _check_crlf(raw)
    line = raw
    if line.endswith(b"\r\n"):
        line = line[:-2]
    if len(line) > limits.max_header_size:
        raise HeaderTooLargeError("status line exceeds max_header_size")
    parts = line.split(b" ", 2)
    if len(parts) < 2 or parts[0] not in {b"HTTP/1.0", b"HTTP/1.1"}:
        raise ProtocolError("malformed HTTP status line")
    status_bytes = parts[1]
    if len(status_bytes) != 3 or any(value < 0x30 or value > 0x39 for value in status_bytes):
        raise ProtocolError("HTTP status must be three decimal digits")
    reason_bytes = parts[2] if len(parts) == 3 else b""
    if len(reason_bytes) > limits.max_header_size:
        raise HeaderTooLargeError("HTTP reason phrase exceeds max_header_size")
    if any(value not in _REASON_BYTES for value in reason_bytes):
        raise ProtocolError("invalid HTTP reason phrase")
    return StatusLine(
        version="HTTP/1.0" if parts[0] == b"HTTP/1.0" else "HTTP/1.1",
        status=int(status_bytes),
        reason=reason_bytes.decode("latin-1"),
    )


def parse_headers(raw: bytes, limits: Limits) -> HeaderFields:
    _check_crlf(raw)
    lines = raw.split(b"\r\n")
    if lines and lines[-1] == b"":
        lines.pop()
    fields: list[tuple[str, str]] = []
    seen_singletons: set[str] = set()
    consumed = 0
    for index, line in enumerate(lines):
        if line == b"":
            if any(remaining for remaining in lines[index + 1 :]):
                raise ProtocolError("data follows empty header line")
            break
        consumed += len(line) + 2
        if consumed > limits.max_header_size:
            raise HeaderTooLargeError("header block exceeds max_header_size")
        if len(fields) >= limits.max_header_count:
            raise HeaderTooLargeError("header count exceeds max_header_count")
        if line[0:1] in {b" ", b"\t"}:
            raise ProtocolError("obsolete header line folding")
        separator = line.find(b":")
        if separator <= 0:
            raise ProtocolError("header field lacks a name")
        name_bytes = line[:separator]
        if any(value not in _TOKEN_BYTES for value in name_bytes):
            raise ProtocolError("invalid header field name")
        value_bytes = line[separator + 1 :].strip(b" \t")
        if any(
            value != 0x09
            and not (0x20 <= value <= 0x7E)
            and not (0x80 <= value <= 0xFF)
            for value in value_bytes
        ):
            raise ProtocolError("invalid header field value")
        name = name_bytes.decode("ascii").lower()
        if name in _SINGLETON_FIELDS:
            if name in seen_singletons:
                raise ProtocolError("duplicate singleton header")
            seen_singletons.add(name)
        fields.append((name, value_bytes.decode("latin-1")))
    return tuple(fields)


class _ChunkReader:
    def __init__(self, chunks: Iterator[bytes], limits: Limits) -> None:
        self._chunks = chunks
        self._limits = limits
        self._buffer = bytearray()

    def _next_fragment(self) -> bool:
        try:
            fragment = next(self._chunks)
        except StopIteration:
            return False
        if fragment:
            self._buffer.extend(fragment)
            return True
        return True

    def read_line(self, eof_error: type[ProtocolError]) -> bytes:
        while True:
            separator = self._buffer.find(b"\r\n")
            if separator >= 0:
                line = bytes(self._buffer[:separator])
                del self._buffer[: separator + 2]
                if len(line) > self._limits.max_header_size:
                    raise ProtocolError("chunk line exceeds max_header_size")
                return line
            if len(self._buffer) > self._limits.max_header_size:
                raise ProtocolError("chunk line exceeds max_header_size")
            if not self._next_fragment():
                raise eof_error("wire data ended before CRLF")

    def read_exact(self, length: int, eof_error: type[ProtocolError]) -> bytes:
        output = bytearray()
        while len(output) < length:
            if not self._buffer and not self._next_fragment():
                raise eof_error("wire data ended inside chunk")
            if self._buffer:
                take = min(length - len(output), len(self._buffer))
                output.extend(self._buffer[:take])
                del self._buffer[:take]
        return bytes(output)


def decode_chunked(
    chunks: Iterator[bytes],
    limits: Limits,
) -> tuple[bytes, HeaderFields]:
    reader = _ChunkReader(chunks, limits)
    body = bytearray()
    while True:
        size_line = reader.read_line(TruncatedBodyError)
        size_text = size_line.split(b";", 1)[0].strip(b" \t")
        if not size_text or any(
            not (
                0x30 <= value <= 0x39
                or 0x41 <= value <= 0x46
                or 0x61 <= value <= 0x66
            )
            for value in size_text
        ):
            raise ProtocolError("invalid chunk size")
        chunk_size = int(size_text, 16)
        if chunk_size == 0:
            break
        if chunk_size > limits.max_body_bytes - len(body):
            raise BodyTooLargeError("decoded chunk body exceeds max_body_bytes")
        body.extend(reader.read_exact(chunk_size, TruncatedBodyError))
        terminator = reader.read_line(ProtocolError)
        if terminator != b"":
            raise ProtocolError("missing CRLF after chunk data")

    trailer_lines: list[bytes] = []
    trailer_size = 0
    while True:
        line = reader.read_line(TruncatedBodyError)
        if line == b"":
            break
        trailer_size += len(line) + 2
        if trailer_size > limits.max_header_size:
            raise HeaderTooLargeError("trailer block exceeds max_header_size")
        trailer_lines.append(line)
    trailer_raw = b"".join(line + b"\r\n" for line in trailer_lines)
    trailers = parse_headers(trailer_raw, limits)
    for name, _value in trailers:
        if name in {"content-length", "transfer-encoding"}:
            raise ProtocolError("trailer contains framing metadata")
    return bytes(body), trailers
