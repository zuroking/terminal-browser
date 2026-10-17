import ast
from pathlib import Path

import pytest

from terminal_browser.core.errors import InvalidUrlError, UnsupportedSchemeError
from terminal_browser.core.limits import Limits
from terminal_browser.url import ParsedUrl, UrlParserImpl


@pytest.fixture
def parser() -> UrlParserImpl:
    return UrlParserImpl(Limits.defaults())


def test_valid_http_url_parses_all_fields(parser: UrlParserImpl) -> None:
    parsed = parser.parse("http://Example.COM:8080/a?x=1")

    assert parsed.scheme == "http"
    assert parsed.host == "example.com"
    assert parsed.port == 8080
    assert parsed.path == "/a"
    assert parsed.raw_query == "x=1"
    assert parsed.normalized_url == "http://example.com:8080/a?x=1"


def test_valid_https_url_uses_default_port(parser: UrlParserImpl) -> None:
    parsed = parser.parse("https://example.com")

    assert parsed.scheme == "https"
    assert parsed.host == "example.com"
    assert parsed.port == 443
    assert parsed.path == "/"
    assert parsed.raw_query == ""
    assert parsed.normalized_url == "https://example.com/"


@pytest.mark.parametrize(
    "reference",
    ("ftp://example.com/file", "javascript:alert(1)", "data:text/plain,x", "mailto:a@b.test"),
)
def test_non_http_schemes_raise_unsupported_scheme(
    parser: UrlParserImpl,
    reference: str,
) -> None:
    with pytest.raises(UnsupportedSchemeError):
        parser.parse(reference)


def test_missing_or_malformed_url_raises_invalid_url(parser: UrlParserImpl) -> None:
    with pytest.raises(InvalidUrlError):
        parser.parse("not a url")


def test_userinfo_is_rejected(parser: UrlParserImpl) -> None:
    with pytest.raises(InvalidUrlError):
        parser.parse("http://user:pass@example.com/")


def test_max_url_length_is_checked_before_full_parse(parser: UrlParserImpl) -> None:
    reference = "http://example.com/" + ("a" * Limits.defaults().max_url_len)

    # The length check occurs before urlsplit and all other URL processing.
    with pytest.raises(InvalidUrlError):
        parser.parse(reference)


def test_ipv6_literal_parses_host_and_port(parser: UrlParserImpl) -> None:
    parsed = parser.parse("http://[::1]:8080/path")

    assert parsed.host == "::1"
    assert parsed.port == 8080
    assert parsed.normalized_url == "http://[::1]:8080/path"


def test_idna_host_is_punycoded(parser: UrlParserImpl) -> None:
    parsed = parser.parse("http://пример.рф/wiki")

    assert parsed.host == "xn--e1afmkfd.xn--p1ai"
    assert parsed.normalized_url.startswith("http://xn--e1afmkfd.xn--p1ai/")


def test_existing_path_encoding_is_not_double_encoded(parser: UrlParserImpl) -> None:
    parsed = parser.parse("http://example.com/a%2Fb%2fc")

    assert parsed.path == "/a%2Fb%2Fc"
    assert parsed.normalized_url == "http://example.com/a%2Fb%2Fc"


def test_literal_cyrillic_path_is_utf8_percent_encoded(parser: UrlParserImpl) -> None:
    parsed = parser.parse("http://example.com/wiki/Казахстан")

    assert parsed.path == "/wiki/%D0%9A%D0%B0%D0%B7%D0%B0%D1%85%D1%81%D1%82%D0%B0%D0%BD"


@pytest.mark.parametrize(
    ("reference", "expected"),
    (
        ("g", "http://a/b/c/g"),
        ("./g", "http://a/b/c/g"),
        ("g/", "http://a/b/c/g/"),
        ("/g", "http://a/g"),
        ("//g", "http://g/"),
        ("?y", "http://a/b/c/d;p?y"),
        ("g?y#s", "http://a/b/c/g?y"),
        (";x", "http://a/b/c/;x"),
        ("g;x", "http://a/b/c/g;x"),
        ("", "http://a/b/c/d;p?q"),
        ("..", "http://a/b/"),
        ("../", "http://a/b/"),
        ("../g", "http://a/b/g"),
        ("../..", "http://a/"),
        ("../../g", "http://a/g"),
    ),
)
def test_relative_resolution_matrix(
    parser: UrlParserImpl,
    reference: str,
    expected: str,
) -> None:
    base = parser.parse("http://a/b/c/d;p?q")

    resolved = parser.resolve(base, reference)

    assert resolved.normalized_url == expected


def test_fragment_only_resolution_preserves_base_url(parser: UrlParserImpl) -> None:
    base = parser.parse("http://a/b/c/d;p?q")

    resolved = parser.resolve(base, "#fragment")

    assert resolved.normalized_url == "http://a/b/c/d;p?q"


@pytest.mark.parametrize(
    ("reference", "expected"),
    (
        ("HTTP://example.com", "http"),
        ("https://example.com", "https"),
        ("ftp://example.com", "ftp"),
        ("//example.com/path", ""),
        ("not a url", ""),
        ("1bad://example.com", ""),
    ),
)
def test_scheme_of_is_best_effort(
    parser: UrlParserImpl,
    reference: str,
    expected: str,
) -> None:
    assert parser.scheme_of(reference) == expected


def test_normalize_for_cache_preserves_query_order_and_bytes(parser: UrlParserImpl) -> None:
    parsed = parser.parse(
        "http://example.com/?b=2&a=1&b=1&empty=%2f#fragment"
    )

    normalized = parser.normalize_for_cache(parsed)

    assert normalized == "http://example.com/?b=2&a=1&b=1&empty=%2f"
    assert normalized.index("b=2") < normalized.index("a=1") < normalized.index("b=1")


def test_normalize_for_cache_strips_default_ports(parser: UrlParserImpl) -> None:
    http_url = parser.parse("http://example.com:80/path")
    https_url = parser.parse("https://example.com:443/path")
    non_default_url = parser.parse("http://example.com:8080/path")

    assert parser.normalize_for_cache(http_url) == "http://example.com/path"
    assert parser.normalize_for_cache(https_url) == "https://example.com/path"
    assert parser.normalize_for_cache(non_default_url) == "http://example.com:8080/path"


def test_normalize_for_cache_changes_empty_path_to_slash(parser: UrlParserImpl) -> None:
    parsed = ParsedUrl(
        scheme="http",
        host="example.com",
        port=80,
        path="",
        raw_query="x=1",
        normalized_url="http://example.com:80?x=1",
    )

    assert parser.normalize_for_cache(parsed) == "http://example.com/?x=1"


def test_url_source_has_no_forbidden_imports() -> None:
    source_path = Path(__file__).parents[1] / "src" / "terminal_browser" / "url.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    forbidden_prefixes = (
        "net.",
        "html.",
        "render.",
        "term.",
        "session.",
    )

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith(forbidden_prefixes)
                assert alias.name not in {"net", "html", "render", "term", "session"}
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert not module.startswith(forbidden_prefixes)
            for alias in node.names:
                assert f"{module}.{alias.name}" not in forbidden_prefixes
