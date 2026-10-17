from pydantic import BaseModel, ConfigDict


class ErrorInfo(BaseModel):
    """Structured information for a browser error."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    code: str
    module: str
    detail: str
    url: str | None


class BrowserError(Exception):
    """Base class for all errors exposed by the browser."""


class NetworkError(BrowserError):
    """Base class for network and transport failures."""


class DnsError(NetworkError):
    """DNS resolution failed."""


class DnsTimeoutError(NetworkError):
    """DNS resolution exceeded its deadline."""


class ConnectTimeoutError(NetworkError):
    """The TCP connection exceeded its deadline."""


class ReadTimeoutError(NetworkError):
    """A socket read exceeded its per-read deadline."""


class ResponseTimeoutError(NetworkError):
    """One response exceeded its total response deadline."""


class NavigationTimeoutError(NetworkError):
    """A complete navigation exceeded its deadline."""


class ConnectionLostError(NetworkError):
    """The connection closed before a complete response."""


class TlsError(NetworkError):
    """TLS negotiation or certificate verification failed."""


class ProtocolError(BrowserError):
    """The wire message violates the HTTP protocol."""


class HeaderTooLargeError(ProtocolError):
    """The response header block exceeded its limits."""


class UnsupportedSchemeError(ProtocolError):
    """A URL uses a scheme the client cannot fetch."""


class TruncatedBodyError(ProtocolError):
    """The response ended before its declared body completed."""


class TokenLimitError(ProtocolError):
    """The tokenizer exceeded its hard token limit."""


class HttpError(BrowserError):
    """Base class for HTTP request and response failures."""


class TooManyRedirectsError(HttpError):
    """The redirect chain exceeded its limit."""


class RedirectError(HttpError):
    """A redirect cannot be followed."""


class BodyTooLargeError(HttpError):
    """A response body exceeded its byte limit."""


class DecodeError(BrowserError):
    """Base class for bounded content decoding failures."""


class UnsupportedEncodingError(DecodeError):
    """The response uses an unsupported content encoding."""


class DecompressionError(DecodeError):
    """Bounded decompression failed or exceeded its output limit."""


class ParseError(BrowserError):
    """The parser encountered an internal invariant failure."""


class FormError(BrowserError):
    """A form cannot be extracted or submitted."""


class RenderError(BrowserError):
    """The renderer cannot produce a valid page."""


class OutputError(BrowserError):
    """Terminal output failed."""


class InvalidUrlError(BrowserError):
    """A URL is malformed or cannot be normalized."""


class SessionError(BrowserError):
    """A session operation cannot be completed."""


class InvalidNavigationError(SessionError):
    """A requested history or link transition is invalid."""
