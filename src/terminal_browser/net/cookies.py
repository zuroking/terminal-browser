from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from ..core.clock import Clock
from ..core.limits import Limits
from ..url import ParsedUrl


class Cookie(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    name: str
    value: str
    host: str
    path: str
    secure_only: bool
    http_only: bool
    session_only: bool
    created_at_epoch: float
    expires_at_epoch: float | None


class CookieHeader(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    value: str | None
    notice: str | None


class CookieJar(Protocol):
    def store_from_headers(
        self,
        url: ParsedUrl,
        set_cookie_values: tuple[str, ...],
    ) -> None: ...

    def header_for(self, url: ParsedUrl) -> CookieHeader: ...

    def snapshot(self) -> tuple[Cookie, ...]: ...

    def clear_expired(self) -> int: ...

    def total_bytes(self) -> int: ...


@dataclass(slots=True)
class _CookieRecord:
    cookie: Cookie
    use_sequence: int


_TOKEN_CHARS = frozenset(
    "!#$%&'*+-.^_`|~"
    "0123456789"
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
)
_FORBIDDEN_VALUE_CHARS = frozenset('" ,;\\')


def _utf8_size(value: str) -> int | None:
    try:
        return len(value.encode("utf-8"))
    except UnicodeEncodeError:
        return None


def _default_path(path: str) -> str:
    if not path or path == "/":
        return "/"
    separator = path.rfind("/")
    if separator <= 0:
        return "/"
    return path[:separator]


def _parse_http_date(value: str | None) -> float | None:
    if value is None:
        return None
    normalized = value.strip()
    formats = (
        "%a, %d %b %Y %H:%M:%S GMT",
        "%A, %d-%b-%y %H:%M:%S GMT",
        "%a %b %d %H:%M:%S %Y",
        "%a, %d-%b-%Y %H:%M:%S GMT",
    )
    for date_format in formats:
        try:
            parsed = datetime.strptime(normalized, date_format)
        except ValueError:
            continue
        return parsed.replace(tzinfo=timezone.utc).timestamp()
    return None


def _parse_attributes(parts: tuple[str, ...]) -> dict[str, str | None]:
    attributes: dict[str, str | None] = {}
    for part in parts:
        name, separator, value = part.partition("=")
        normalized_name = name.strip().lower()
        if not normalized_name:
            continue
        normalized_value = value.strip() if separator else None
        attributes.setdefault(normalized_name, normalized_value)
    return attributes


def _cookie_size(cookie: Cookie) -> int:
    values = (
        cookie.name,
        cookie.value,
        cookie.host,
        cookie.path,
    )
    return sum(_utf8_size(value) or 0 for value in values) + 64


def _record_order(record: _CookieRecord) -> tuple[float, int, str, str, str]:
    return (
        record.cookie.created_at_epoch,
        record.use_sequence,
        record.cookie.name,
        record.cookie.host,
        record.cookie.path,
    )


class CookieJarImpl:
    def __init__(self, clock: Clock, limits: Limits) -> None:
        self._clock = clock
        self._limits = limits
        self._cookies: dict[tuple[str, str, str], _CookieRecord] = {}
        self._use_sequence = 0

    def store_from_headers(
        self,
        url: ParsedUrl,
        set_cookie_values: tuple[str, ...],
    ) -> None:
        self.clear_expired()
        now = self._clock.now_epoch()
        for raw_value in set_cookie_values:
            encoded_size = _utf8_size(raw_value)
            if encoded_size is None or encoded_size > self._limits.max_set_cookie_bytes:
                continue
            parts = tuple(raw_value.split(";"))
            name_value = parts[0]
            name, separator, value = name_value.partition("=")
            if not separator:
                continue
            name = name.strip()
            value = value.strip()
            if (
                not name
                or any(character not in _TOKEN_CHARS for character in name)
                or any(
                    character in _FORBIDDEN_VALUE_CHARS
                    or character.isspace()
                    or ord(character) < 0x20
                    or ord(character) == 0x7F
                    for character in value
                )
            ):
                continue
            attributes = _parse_attributes(parts[1:])
            secure_only = "secure" in attributes
            if secure_only and url.scheme != "https":
                continue
            path_attribute = attributes.get("path")
            path = (
                path_attribute
                if path_attribute is not None and path_attribute.startswith("/")
                else _default_path(url.path)
            )
            key = (name, url.host, path)
            max_age_value = attributes.get("max-age")
            max_age: int | None = None
            if max_age_value is not None:
                try:
                    max_age = int(max_age_value)
                except ValueError:
                    max_age = None
            if max_age is not None and max_age <= 0:
                self._cookies.pop(key, None)
                continue
            expires_at = (
                now + max_age
                if max_age is not None
                else _parse_http_date(attributes.get("expires"))
            )
            if expires_at is not None and expires_at <= now:
                self._cookies.pop(key, None)
                continue
            existing = self._cookies.get(key)
            created_at = existing.cookie.created_at_epoch if existing is not None else now
            cookie = Cookie(
                name=name,
                value=value,
                host=url.host,
                path=path,
                secure_only=secure_only,
                http_only="httponly" in attributes,
                session_only=expires_at is None,
                created_at_epoch=created_at,
                expires_at_epoch=expires_at,
            )
            self._cookies[key] = _CookieRecord(cookie=cookie, use_sequence=0)
            self._enforce_caps()
        self.clear_expired()

    def _enforce_caps(self) -> None:
        hosts = {key[1] for key in self._cookies}
        for host in hosts:
            while True:
                host_keys = [key for key in self._cookies if key[1] == host]
                if len(host_keys) <= self._limits.max_cookies_per_host:
                    break
                oldest_key = min(host_keys, key=lambda key: _record_order(self._cookies[key]))
                del self._cookies[oldest_key]
        while (
            len(self._cookies) > self._limits.max_cookies_total
            or self.total_bytes() > self._limits.max_cookie_store_bytes
        ):
            if not self._cookies:
                break
            oldest_key = min(
                self._cookies,
                key=lambda key: _record_order(self._cookies[key]),
            )
            del self._cookies[oldest_key]

    def clear_expired(self) -> int:
        now = self._clock.now_epoch()
        expired = [
            key
            for key, record in self._cookies.items()
            if record.cookie.expires_at_epoch is not None
            and record.cookie.expires_at_epoch <= now
        ]
        for key in expired:
            del self._cookies[key]
        return len(expired)

    def _matches_path(self, cookie_path: str, request_path: str) -> bool:
        return (
            cookie_path == request_path
            or (cookie_path.endswith("/") and request_path.startswith(cookie_path))
            or request_path.startswith(cookie_path + "/")
        )

    def header_for(self, url: ParsedUrl) -> CookieHeader:
        self.clear_expired()
        eligible = [
            record
            for record in self._cookies.values()
            if record.cookie.host == url.host
            and self._matches_path(record.cookie.path, url.path)
            and (not record.cookie.secure_only or url.scheme == "https")
        ]
        eligible.sort(
            key=lambda record: (
                -len(record.cookie.path),
                record.cookie.created_at_epoch,
                record.cookie.name,
            )
        )
        if not eligible:
            return CookieHeader(value=None, notice=None)
        selected: list[_CookieRecord] = []
        selected_parts: list[str] = []
        omitted = False
        for record in eligible:
            pair = f"{record.cookie.name}={record.cookie.value}"
            candidate = "; ".join((*selected_parts, pair))
            candidate_size = _utf8_size(candidate)
            if (
                candidate_size is None
                or candidate_size > self._limits.max_cookie_header_bytes
            ):
                omitted = True
                break
            selected.append(record)
            selected_parts.append(pair)
        if not selected:
            return CookieHeader(
                value=None,
                notice="eligible cookies did not fit within max_cookie_header_bytes",
            )
        for record in selected:
            record.use_sequence = self._use_sequence
            self._use_sequence += 1
        return CookieHeader(
            value="; ".join(selected_parts),
            notice=(
                "one or more eligible cookies were dropped for max_cookie_header_bytes"
                if omitted
                else None
            ),
        )

    def snapshot(self) -> tuple[Cookie, ...]:
        records = sorted(
            self._cookies.values(),
            key=lambda record: (
                record.cookie.host,
                record.cookie.path,
                record.cookie.name,
            ),
        )
        return tuple(record.cookie for record in records)

    def total_bytes(self) -> int:
        return sum(_cookie_size(record.cookie) for record in self._cookies.values())
