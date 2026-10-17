from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import struct
from typing import Literal, Protocol, cast

from pydantic import BaseModel, ConfigDict

from ..core.clock import Clock
from ..core.limits import Limits
from .wire import HeaderFields


_MAGIC = b"TBC1"
_VERSION = 1
_INDEX_NAME = "index.txt"
_METADATA_COUNT_LIMIT = 10_000


class CacheKey(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    method: Literal["GET"]
    normalized_url: str


class CacheEntry(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    key: CacheKey
    status: Literal[200]
    headers: HeaderFields
    body: bytes
    stored_at_epoch: float
    fresh_until_epoch: float | None
    etag: str | None
    last_modified: str | None
    body_len: int
    age_at_stored_epoch: float


class Cache(Protocol):
    def get(self, key: CacheKey) -> CacheEntry | None: ...

    def put(self, entry: CacheEntry) -> bool: ...

    def invalidate(self, normalized_url: str) -> int: ...

    def byte_size(self) -> int: ...

    def close(self) -> None: ...


@dataclass(slots=True)
class _CacheRecord:
    entry: CacheEntry
    size: int
    access_sequence: int


def _unquote(value: str) -> str:
    normalized = value.strip()
    if len(normalized) >= 2 and normalized[0] == normalized[-1] and normalized[0] in "\"'":
        return normalized[1:-1]
    return normalized


def _header_values(headers: HeaderFields, name: str) -> tuple[str, ...]:
    return tuple(value for field_name, value in headers if field_name.lower() == name.lower())


def _cache_control(headers: HeaderFields) -> tuple[dict[str, str | None], bool]:
    directives: dict[str, str | None] = {}
    conflicting_max_age = False
    for field_value in _header_values(headers, "cache-control"):
        for part in field_value.split(";"):
            name, separator, value = part.partition("=")
            directive = name.strip().lower()
            if not directive:
                continue
            normalized_value = _unquote(value) if separator else None
            if directive == "max-age" and directive in directives:
                if directives[directive] != normalized_value:
                    conflicting_max_age = True
            else:
                directives.setdefault(directive, normalized_value)
    return directives, conflicting_max_age


def _integer(value: str | None, minimum: int | None = None) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value.strip())
    except ValueError:
        return None
    if minimum is not None and parsed < minimum:
        return None
    return parsed


def _clock_value(value: str) -> tuple[int, int, int] | None:
    pieces = value.split(":")
    if len(pieces) != 3:
        return None
    try:
        hour, minute, second = (int(piece) for piece in pieces)
    except ValueError:
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 60):
        return None
    return hour, minute, min(second, 59)


def parse_http_date(value: str | None) -> float | None:
    if value is None:
        return None
    text = " ".join(value.split())
    if text.upper().endswith("GMT"):
        text = text[:-3].strip()
    text = text.replace("'", "").replace(",", " ")
    tokens = text.split()
    month_names = {
        "Jan": 1,
        "Feb": 2,
        "Mar": 3,
        "Apr": 4,
        "May": 5,
        "Jun": 6,
        "Jul": 7,
        "Aug": 8,
        "Sep": 9,
        "Oct": 10,
        "Nov": 11,
        "Dec": 12,
    }
    day: int
    month: int
    year: int
    clock: tuple[int, int, int] | None
    if len(tokens) == 5 and tokens[1].isdigit() and tokens[2] in month_names:
        day = int(tokens[1])
        month = month_names[tokens[2]]
        year = int(tokens[3])
        clock = _clock_value(tokens[4])
    elif len(tokens) == 3 and "-" in tokens[1]:
        date_parts = tokens[1].split("-")
        if len(date_parts) != 3 or not date_parts[0].isdigit() or date_parts[1] not in month_names or not date_parts[2].isdigit():
            return None
        day = int(date_parts[0])
        month = month_names[date_parts[1]]
        year_text = date_parts[2]
        year = int(year_text)
        if len(year_text) == 2:
            year = 1900 + year if year >= 70 else 2000 + year
        clock = _clock_value(tokens[2])
    elif len(tokens) == 5 and tokens[1] in month_names and tokens[2].isdigit():
        month = month_names[tokens[1]]
        day = int(tokens[2])
        clock = _clock_value(tokens[3])
        year = int(tokens[4])
    else:
        return None
    if clock is None:
        return None
    try:
        parsed = datetime(year, month, day, *clock, tzinfo=timezone.utc)
    except ValueError:
        return None
    return parsed.timestamp()


def compute_age_at_stored_epoch(headers: HeaderFields, received_at_epoch: float) -> float:
    valid_ages = [
        age
        for value in _header_values(headers, "age")
        if (age := _integer(value, minimum=0)) is not None
    ]
    age_value = max(valid_ages, default=0)
    date_value = next(iter(_header_values(headers, "date")), None)
    date_epoch = parse_http_date(date_value)
    apparent_age = max(0.0, received_at_epoch - date_epoch) if date_epoch is not None else 0.0
    return max(0.0, float(age_value), apparent_age)


def compute_fresh_until_epoch(headers: HeaderFields, received_at_epoch: float) -> float:
    directives, conflicting_max_age = _cache_control(headers)
    if "no-cache" in directives or conflicting_max_age:
        return received_at_epoch
    max_age = _integer(directives.get("max-age"))
    if max_age is not None:
        return received_at_epoch + max(0, max_age)
    expires_value = next(iter(_header_values(headers, "expires")), None)
    expires_epoch = parse_http_date(expires_value)
    if expires_epoch is not None:
        return expires_epoch
    last_modified_value = next(iter(_header_values(headers, "last-modified")), None)
    last_modified_epoch = parse_http_date(last_modified_value)
    if last_modified_epoch is None:
        return received_at_epoch
    lifetime = min(86_400.0, max(0.0, received_at_epoch - last_modified_epoch) / 10.0)
    return received_at_epoch + lifetime


def is_cacheable(
    status: int,
    method: str,
    headers: HeaderFields,
    body_len: int,
    limits: Limits,
    transfer_truncated: bool = False,
) -> bool:
    directives, conflicting_max_age = _cache_control(headers)
    return (
        status == 200
        and method == "GET"
        and not transfer_truncated
        and "no-store" not in directives
        and not conflicting_max_age
        and not _header_values(headers, "vary")
        and body_len <= limits.max_cache_entry_bytes
        and body_len <= limits.cache_byte_budget
    )


def build_entry(
    key: CacheKey,
    status: int,
    method: str,
    headers: HeaderFields,
    body: bytes,
    received_at_epoch: float,
    limits: Limits,
    transfer_truncated: bool = False,
) -> CacheEntry | None:
    if not is_cacheable(
        status,
        method,
        headers,
        len(body),
        limits,
        transfer_truncated,
    ):
        return None
    return CacheEntry(
        key=key,
        status=200,
        headers=headers,
        body=body,
        stored_at_epoch=received_at_epoch,
        fresh_until_epoch=compute_fresh_until_epoch(headers, received_at_epoch),
        etag=next(iter(_header_values(headers, "etag")), None),
        last_modified=next(iter(_header_values(headers, "last-modified")), None),
        body_len=len(body),
        age_at_stored_epoch=compute_age_at_stored_epoch(headers, received_at_epoch),
    )


def _key_digest(key: CacheKey) -> str:
    canonical = f"{key.method}\n{key.normalized_url}".encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _pack_text(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return struct.pack(">I", len(encoded)) + encoded


def _unpack_text(data: bytes, offset: int, maximum: int) -> tuple[str, int]:
    if offset + 4 > len(data):
        raise ValueError("truncated cache metadata length")
    length = struct.unpack_from(">I", data, offset)[0]
    offset += 4
    if length > maximum or offset + length > len(data):
        raise ValueError("invalid cache metadata length")
    try:
        value = data[offset : offset + length].decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("invalid cache metadata encoding") from error
    return value, offset + length


def _encode_entry(entry: CacheEntry) -> bytes:
    values: list[str] = [
        entry.key.method,
        entry.key.normalized_url,
        str(entry.status),
        repr(entry.stored_at_epoch),
        "" if entry.fresh_until_epoch is None else repr(entry.fresh_until_epoch),
        entry.etag or "",
        entry.last_modified or "",
        str(entry.body_len),
        repr(entry.age_at_stored_epoch),
        str(len(entry.headers)),
    ]
    for name, value in entry.headers:
        values.extend((name, value))
    encoded = bytearray(_MAGIC)
    encoded.append(_VERSION)
    encoded.extend(struct.pack(">I", len(values)))
    for value in values:
        encoded.extend(_pack_text(value))
    encoded.extend(struct.pack(">Q", len(entry.body)))
    encoded.extend(entry.body)
    return bytes(encoded)


def _decode_entry(data: bytes, limits: Limits) -> CacheEntry:
    if len(data) < len(_MAGIC) + 1 or data[: len(_MAGIC)] != _MAGIC or data[len(_MAGIC)] != _VERSION:
        raise ValueError("unsupported cache record")
    offset = len(_MAGIC) + 1
    if offset + 4 > len(data):
        raise ValueError("truncated cache metadata count")
    value_count = struct.unpack_from(">I", data, offset)[0]
    offset += 4
    if value_count > _METADATA_COUNT_LIMIT:
        raise ValueError("too many cache metadata values")
    maximum_text = max(limits.max_url_len, limits.max_header_size)
    values: list[str] = []
    for _ in range(value_count):
        value, offset = _unpack_text(data, offset, maximum_text)
        values.append(value)
    if len(values) < 10 or offset + 8 > len(data):
        raise ValueError("incomplete cache metadata")
    header_count = int(values[9])
    if header_count > limits.max_header_count or len(values) != 10 + header_count * 2:
        raise ValueError("invalid cache header metadata")
    headers = tuple(
        (values[10 + index * 2], values[11 + index * 2])
        for index in range(header_count)
    )
    body_length = struct.unpack_from(">Q", data, offset)[0]
    offset += 8
    if body_length > limits.max_cache_entry_bytes or offset + body_length != len(data):
        raise ValueError("invalid cache body length")
    fresh_until = None if values[4] == "" else float(values[4])
    if values[0] != "GET" or int(values[2]) != 200:
        raise ValueError("invalid cache key or status")
    method = cast(Literal["GET"], values[0])
    status = cast(Literal[200], int(values[2]))
    entry = CacheEntry(
        key=CacheKey(method=method, normalized_url=values[1]),
        status=status,
        headers=headers,
        body=data[offset:],
        stored_at_epoch=float(values[3]),
        fresh_until_epoch=fresh_until,
        etag=values[5] or None,
        last_modified=values[6] or None,
        body_len=int(values[7]),
        age_at_stored_epoch=float(values[8]),
    )
    if entry.body_len != len(entry.body):
        raise ValueError("cache body length mismatch")
    return entry


class DiskCache:
    def __init__(self, cache_dir: Path | str, limits: Limits, clock: Clock) -> None:
        self._cache_dir = Path(cache_dir)
        self._limits = limits
        self._clock = clock
        self._records: dict[CacheKey, _CacheRecord] = {}
        self._access_sequence = 0
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._load()

    def _record_path(self, key: CacheKey) -> Path:
        return self._cache_dir / f"{_key_digest(key)}.cache"

    def _load_index(self) -> dict[str, int]:
        path = self._cache_dir / _INDEX_NAME
        if not path.exists():
            return {}
        result: dict[str, int] = {}
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            return {}
        for line in lines:
            digest, separator, sequence_text = line.partition("\t")
            if len(digest) != 64 or not separator:
                continue
            try:
                sequence = int(sequence_text)
            except ValueError:
                continue
            if sequence >= 0:
                result[digest] = sequence
        return result

    def _persist_index(self) -> None:
        index_path = self._cache_dir / _INDEX_NAME
        temporary_path = self._cache_dir / f".{_INDEX_NAME}.tmp"
        lines = [
            f"{_key_digest(record.entry.key)}\t{record.access_sequence}\n"
            for record in self._records.values()
        ]
        temporary_path.write_text("".join(lines), encoding="utf-8")
        temporary_path.replace(index_path)

    def _load(self) -> None:
        index = self._load_index()
        for path in sorted(self._cache_dir.glob("*.cache")):
            try:
                data = path.read_bytes()
                entry = _decode_entry(data, self._limits)
            except (OSError, ValueError, UnicodeError, struct.error):
                path.unlink(missing_ok=True)
                continue
            if entry.key in self._records:
                path.unlink(missing_ok=True)
                continue
            access = index.get(path.stem, 0)
            self._records[entry.key] = _CacheRecord(
                entry=entry,
                size=len(data),
                access_sequence=access,
            )
            self._access_sequence = max(self._access_sequence, access + 1)
        self._enforce_lru()

    def _remove(self, key: CacheKey) -> None:
        self._records.pop(key, None)
        self._record_path(key).unlink(missing_ok=True)

    def _enforce_lru(self) -> None:
        while self.byte_size() > self._limits.cache_byte_budget:
            if not self._records:
                break
            oldest_key = min(
                self._records,
                key=lambda key: self._records[key].access_sequence,
            )
            self._remove(oldest_key)

    def get(self, key: CacheKey) -> CacheEntry | None:
        record = self._records.get(key)
        if record is None:
            return None
        record.access_sequence = self._access_sequence
        self._access_sequence += 1
        self._persist_index()
        return record.entry

    def put(self, entry: CacheEntry) -> bool:
        if entry.body_len != len(entry.body):
            return False
        if not is_cacheable(
            entry.status,
            entry.key.method,
            entry.headers,
            entry.body_len,
            self._limits,
        ):
            return False
        try:
            encoded = _encode_entry(entry)
        except (UnicodeError, struct.error):
            return False
        if len(encoded) > self._limits.max_cache_entry_bytes or len(encoded) > self._limits.cache_byte_budget:
            return False
        path = self._record_path(entry.key)
        temporary_path = self._cache_dir / f".{path.name}.tmp"
        try:
            temporary_path.write_bytes(encoded)
            temporary_path.replace(path)
        except OSError:
            temporary_path.unlink(missing_ok=True)
            return False
        old_record = self._records.get(entry.key)
        if old_record is not None:
            del self._records[entry.key]
        self._records[entry.key] = _CacheRecord(
            entry=entry,
            size=len(encoded),
            access_sequence=self._access_sequence,
        )
        self._access_sequence += 1
        self._enforce_lru()
        self._persist_index()
        return entry.key in self._records

    def invalidate(self, normalized_url: str) -> int:
        key = CacheKey(method="GET", normalized_url=normalized_url)
        if key not in self._records:
            return 0
        self._remove(key)
        self._persist_index()
        return 1

    def byte_size(self) -> int:
        return sum(record.size for record in self._records.values())

    def close(self) -> None:
        self._persist_index()
