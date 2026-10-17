import pytest
from pydantic import ValidationError

from terminal_browser.core.errors import (
    BodyTooLargeError,
    BrowserError,
    ConnectTimeoutError,
    ConnectionLostError,
    DecodeError,
    DecompressionError,
    DnsError,
    DnsTimeoutError,
    ErrorInfo,
    FormError,
    HeaderTooLargeError,
    HttpError,
    InvalidNavigationError,
    InvalidUrlError,
    NavigationTimeoutError,
    NetworkError,
    OutputError,
    ParseError,
    ProtocolError,
    ReadTimeoutError,
    RedirectError,
    RenderError,
    ResponseTimeoutError,
    SessionError,
    TlsError,
    TokenLimitError,
    TooManyRedirectsError,
    TruncatedBodyError,
    UnsupportedEncodingError,
    UnsupportedSchemeError,
)

EXPECTED_HIERARCHY: dict[str, tuple[str, ...]] = {
    "BrowserError": (
        "NetworkError",
        "ProtocolError",
        "HttpError",
        "DecodeError",
        "ParseError",
        "FormError",
        "RenderError",
        "OutputError",
        "InvalidUrlError",
        "SessionError",
    ),
    "NetworkError": (
        "DnsError",
        "DnsTimeoutError",
        "ConnectTimeoutError",
        "ReadTimeoutError",
        "ResponseTimeoutError",
        "NavigationTimeoutError",
        "ConnectionLostError",
        "TlsError",
    ),
    "ProtocolError": (
        "HeaderTooLargeError",
        "UnsupportedSchemeError",
        "TruncatedBodyError",
        "TokenLimitError",
    ),
    "HttpError": (
        "TooManyRedirectsError",
        "RedirectError",
        "BodyTooLargeError",
    ),
    "DecodeError": (
        "UnsupportedEncodingError",
        "DecompressionError",
    ),
    "ParseError": (),
    "FormError": (),
    "RenderError": (),
    "OutputError": (),
    "InvalidUrlError": (),
    "SessionError": ("InvalidNavigationError",),
    "InvalidNavigationError": (),
}

LEAF_ERRORS: tuple[type[BrowserError], ...] = (
    DnsError,
    DnsTimeoutError,
    ConnectTimeoutError,
    ReadTimeoutError,
    ResponseTimeoutError,
    NavigationTimeoutError,
    ConnectionLostError,
    TlsError,
    HeaderTooLargeError,
    UnsupportedSchemeError,
    TruncatedBodyError,
    TokenLimitError,
    TooManyRedirectsError,
    RedirectError,
    BodyTooLargeError,
    UnsupportedEncodingError,
    DecompressionError,
    ParseError,
    FormError,
    RenderError,
    OutputError,
    InvalidUrlError,
    InvalidNavigationError,
)


def hierarchy(error_type: type[BrowserError]) -> dict[str, tuple[str, ...]]:
    children = tuple(child.__name__ for child in error_type.__subclasses__())
    result = {error_type.__name__: children}
    for child in error_type.__subclasses__():
        result.update(hierarchy(child))
    return result


def valid_error_data() -> dict[str, object]:
    return {
        "code": "network_error",
        "module": "net.transport",
        "detail": "connection failed",
        "url": "https://example.test/",
    }


def test_error_hierarchy_matches_architecture() -> None:
    actual_hierarchy = hierarchy(BrowserError)
    actual_branches = {
        name: children
        for name, children in actual_hierarchy.items()
        if children
    }
    expected_branches = {
        name: children
        for name, children in EXPECTED_HIERARCHY.items()
        if children
    }
    assert actual_branches == expected_branches


def test_every_leaf_error_subclasses_browser_error() -> None:
    actual_leaves = {
        name
        for name, children in hierarchy(BrowserError).items()
        if not children
    }
    expected_leaves = {error_type.__name__ for error_type in LEAF_ERRORS}

    assert all(issubclass(error_type, BrowserError) for error_type in LEAF_ERRORS)
    assert actual_leaves == expected_leaves


def test_error_info_is_frozen() -> None:
    error_info = ErrorInfo.model_validate(valid_error_data())

    with pytest.raises(ValidationError):
        error_info.code = "changed"


def test_error_info_rejects_extra_fields() -> None:
    data = valid_error_data()
    data["extra"] = "not allowed"

    with pytest.raises(ValidationError):
        ErrorInfo.model_validate(data)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("code", 1),
        ("module", False),
        ("detail", []),
        ("url", 1),
    ),
)
def test_error_info_rejects_wrong_types(field: str, value: object) -> None:
    data = valid_error_data()
    data[field] = value

    with pytest.raises(ValidationError):
        ErrorInfo.model_validate(data)
