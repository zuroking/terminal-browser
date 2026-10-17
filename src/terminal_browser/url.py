from ipaddress import IPv6Address
from typing import Literal, Protocol, cast
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict

from .core.errors import InvalidUrlError, UnsupportedSchemeError
from .core.limits import Limits


class ParsedUrl(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    scheme: Literal["http", "https"]
    host: str
    port: int
    path: str
    raw_query: str
    normalized_url: str


class UrlParser(Protocol):
    def parse(self, reference: str) -> ParsedUrl: ...

    def resolve(self, base: ParsedUrl, reference: str) -> ParsedUrl: ...

    def scheme_of(self, reference: str) -> str: ...

    def normalize_for_cache(self, url: ParsedUrl) -> str: ...


_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")
_PATH_SAFE = ":@!$&'()*+,;=-._~/"


def _is_percent_triplet(value: str, index: int) -> bool:
    return (
        index + 2 < len(value)
        and value[index] == "%"
        and value[index + 1] in _HEX_DIGITS
        and value[index + 2] in _HEX_DIGITS
    )


def _normalize_path(path: str) -> str:
    output: list[str] = []
    literal: list[str] = []
    index = 0
    while index < len(path):
        if _is_percent_triplet(path, index):
            if literal:
                output.append(quote("".join(literal), safe=_PATH_SAFE))
                literal.clear()
            output.append("%" + path[index + 1 : index + 3].upper())
            index += 3
            continue
        if path[index] == "%":
            literal.append("%")
        else:
            literal.append(path[index])
        index += 1
    if literal:
        output.append(quote("".join(literal), safe=_PATH_SAFE))
    return "".join(output) or "/"


def _normalize_query(query: str) -> str:
    output: list[str] = []
    for character in query:
        codepoint = ord(character)
        if codepoint <= 0x7F:
            output.append(character)
        else:
            output.extend(f"%{byte:02X}" for byte in character.encode("utf-8"))
    return "".join(output)


def _canonical_host(host: str) -> str:
    if any(
        character.isspace() or ord(character) < 0x20 or character in "%[]@"
        for character in host
    ):
        raise InvalidUrlError("invalid host")
    if ":" in host:
        try:
            return IPv6Address(host).compressed.lower()
        except ValueError as error:
            raise InvalidUrlError("invalid IPv6 host") from error
    try:
        return host.encode("idna").decode("ascii").lower()
    except UnicodeError as error:
        raise InvalidUrlError("invalid IDNA host") from error


def _netloc(host: str, port: int | None) -> str:
    rendered_host = f"[{host}]" if ":" in host else host
    if port is None:
        return rendered_host
    return f"{rendered_host}:{port}"


def _render_url(
    scheme: str,
    host: str,
    port: int,
    path: str,
    raw_query: str,
) -> str:
    normalized_port = None
    if not (
        (scheme == "http" and port == 80)
        or (scheme == "https" and port == 443)
    ):
        normalized_port = port
    return urlunsplit(
        (scheme, _netloc(host, normalized_port), path or "/", raw_query, "")
    )


class UrlParserImpl:
    def __init__(self, limits: Limits) -> None:
        self._limits = limits

    def parse(self, reference: str) -> ParsedUrl:
        if len(reference) > self._limits.max_url_len:
            raise InvalidUrlError("URL exceeds max_url_len")
        try:
            encoded_length = len(reference.encode("utf-8"))
        except UnicodeEncodeError as error:
            raise InvalidUrlError("URL contains invalid Unicode") from error
        if encoded_length > self._limits.max_url_len:
            raise InvalidUrlError("URL exceeds max_url_len")
        try:
            parts = urlsplit(reference)
            scheme_value = parts.scheme.lower()
            if not scheme_value:
                raise InvalidUrlError("URL scheme is required")
            if scheme_value not in {"http", "https"}:
                raise UnsupportedSchemeError("only HTTP and HTTPS URLs are supported")
            scheme = cast(Literal["http", "https"], scheme_value)
            if parts.username is not None or parts.password is not None or "@" in parts.netloc:
                raise InvalidUrlError("URL userinfo is not supported")
            raw_host = parts.hostname
            if raw_host is None:
                raise InvalidUrlError("URL host is required")
            host = _canonical_host(raw_host)
            port = parts.port
            if port is None:
                port = 80 if scheme == "http" else 443
            if not 1 <= port <= 65535:
                raise InvalidUrlError("URL port is invalid")
            path = _normalize_path(parts.path)
            raw_query = _normalize_query(parts.query)
        except (UnicodeError, ValueError) as error:
            if isinstance(error, (InvalidUrlError, UnsupportedSchemeError)):
                raise
            raise InvalidUrlError("malformed URL") from error

        normalized_url = _render_url(scheme, host, port, path, raw_query)
        return ParsedUrl(
            scheme=scheme,
            host=host,
            port=port,
            path=path,
            raw_query=raw_query,
            normalized_url=normalized_url,
        )

    def resolve(self, base: ParsedUrl, reference: str) -> ParsedUrl:
        try:
            joined = urljoin(base.normalized_url, reference)
        except (UnicodeError, ValueError) as error:
            raise InvalidUrlError("malformed relative URL") from error
        return self.parse(joined)

    def scheme_of(self, reference: str) -> str:
        separator = reference.find(":")
        if separator <= 0:
            return ""
        scheme = reference[:separator]
        if not scheme[0].isascii() or not scheme[0].isalpha():
            return ""
        if not all(
            character.isascii()
            and (character.isalnum() or character in "+.-")
            for character in scheme
        ):
            return ""
        return scheme.lower()

    def normalize_for_cache(self, url: ParsedUrl) -> str:
        return _render_url(
            url.scheme.lower(),
            url.host.lower(),
            url.port,
            url.path,
            url.raw_query,
        )
