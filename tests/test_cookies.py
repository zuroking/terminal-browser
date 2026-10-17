import ast
from pathlib import Path

import pytest

from terminal_browser.core.clock import FakeClock
from terminal_browser.core.limits import Limits
from terminal_browser.net.cookies import CookieHeader, CookieJarImpl
from terminal_browser.url import ParsedUrl


LIMITS = Limits.defaults()


def make_url(scheme: str, host: str, path: str = "/") -> ParsedUrl:
    port = 80 if scheme == "http" else 443
    return ParsedUrl(
        scheme=scheme,
        host=host,
        port=port,
        path=path,
        raw_query="",
        normalized_url=f"{scheme}://{host}{path}",
    )


def make_jar(clock: FakeClock, **overrides: int) -> CookieJarImpl:
    limits = Limits.model_validate({**LIMITS.model_dump(), **overrides})
    return CookieJarImpl(clock, limits)


def test_basic_store_and_retrieve_round_trip() -> None:
    clock = FakeClock(monotonic_start=0.0, epoch_start=100.0)
    jar = make_jar(clock)
    url = make_url("https", "example.com")

    jar.store_from_headers(url, ("session=abc; Path=/; Secure; HttpOnly",))

    result = jar.header_for(url)

    assert result.value == "session=abc"
    assert result.notice is None
    assert jar.snapshot()[0].http_only is True


def test_oversized_set_cookie_field_is_rejected_before_parsing() -> None:
    clock = FakeClock(monotonic_start=0.0, epoch_start=100.0)
    jar = make_jar(clock, max_set_cookie_bytes=8)
    url = make_url("https", "example.com")

    jar.store_from_headers(url, ("name=oversized-value",))

    assert jar.snapshot() == ()
    assert jar.header_for(url) == CookieHeader(value=None, notice=None)


def test_max_age_takes_precedence_over_expires() -> None:
    clock = FakeClock(monotonic_start=0.0, epoch_start=100.0)
    jar = make_jar(clock)
    url = make_url("https", "example.com")

    jar.store_from_headers(
        url,
        ("token=abc; Max-Age=3600; Expires=Wed, 21 Oct 2015 07:28:00 GMT",),
    )

    cookie = jar.snapshot()[0]
    assert cookie.expires_at_epoch == 3700.0
    assert cookie.session_only is False


@pytest.mark.parametrize("max_age", ("0", "-1"))
def test_nonpositive_max_age_deletes_existing_cookie(max_age: str) -> None:
    clock = FakeClock(monotonic_start=0.0, epoch_start=100.0)
    jar = make_jar(clock)
    url = make_url("https", "example.com")
    jar.store_from_headers(url, ("token=abc; Max-Age=3600",))

    jar.store_from_headers(url, (f"token=deleted; Max-Age={max_age}",))

    assert jar.snapshot() == ()


def test_invalid_expires_stores_session_cookie() -> None:
    clock = FakeClock(monotonic_start=0.0, epoch_start=100.0)
    jar = make_jar(clock)
    url = make_url("https", "example.com")

    jar.store_from_headers(url, ("token=abc; Expires=not-a-date",))

    cookie = jar.snapshot()[0]
    assert cookie.session_only is True
    assert cookie.expires_at_epoch is None


def test_secure_cookie_over_http_is_rejected() -> None:
    clock = FakeClock(monotonic_start=0.0, epoch_start=100.0)
    jar = make_jar(clock)

    jar.store_from_headers(make_url("http", "example.com"), ("token=abc; Secure",))

    assert jar.snapshot() == ()


def test_secure_cookie_is_sent_only_over_https() -> None:
    clock = FakeClock(monotonic_start=0.0, epoch_start=100.0)
    jar = make_jar(clock)
    jar.store_from_headers(
        make_url("https", "example.com"),
        ("token=abc; Secure",),
    )

    assert jar.header_for(make_url("http", "example.com")).value is None
    assert jar.header_for(make_url("https", "example.com")).value == "token=abc"


def test_domain_attribute_does_not_widen_host_scope() -> None:
    clock = FakeClock(monotonic_start=0.0, epoch_start=100.0)
    jar = make_jar(clock)
    jar.store_from_headers(
        make_url("https", "one.example"),
        ("token=abc; Domain=two.example",),
    )

    assert jar.header_for(make_url("https", "two.example")).value is None
    assert jar.header_for(make_url("https", "one.example")).value == "token=abc"


@pytest.mark.parametrize(
    ("cookie_path", "request_path", "expected"),
    (
        ("/foo", "/foo", "token=abc"),
        ("/foo/", "/foo/bar", "token=abc"),
        ("/foo", "/foobar", None),
    ),
)
def test_path_matching_rules(
    cookie_path: str,
    request_path: str,
    expected: str | None,
) -> None:
    clock = FakeClock(monotonic_start=0.0, epoch_start=100.0)
    jar = make_jar(clock)
    jar.store_from_headers(
        make_url("https", "example.com"),
        (f"token=abc; Path={cookie_path}",),
    )

    assert jar.header_for(make_url("https", "example.com", request_path)).value == expected


def test_replacing_cookie_preserves_created_at_epoch() -> None:
    clock = FakeClock(monotonic_start=0.0, epoch_start=100.0)
    jar = make_jar(clock)
    url = make_url("https", "example.com")
    jar.store_from_headers(url, ("token=first; Path=/",))
    original_created = jar.snapshot()[0].created_at_epoch

    clock.advance(50.0)
    jar.store_from_headers(url, ("token=second; Path=/",))

    assert jar.snapshot()[0].created_at_epoch == original_created


def test_expired_cookie_is_implicitly_cleared_before_send() -> None:
    clock = FakeClock(monotonic_start=0.0, epoch_start=100.0)
    jar = make_jar(clock)
    url = make_url("https", "example.com")
    jar.store_from_headers(url, ("token=abc; Max-Age=1",))

    clock.advance(2.0)

    assert jar.header_for(url).value is None
    assert jar.snapshot() == ()


def test_per_host_cap_evicts_earliest_cookie() -> None:
    clock = FakeClock(monotonic_start=0.0, epoch_start=100.0)
    jar = make_jar(clock, max_cookies_per_host=2, max_cookies_total=10)
    url = make_url("https", "example.com")
    jar.store_from_headers(url, ("a=1; Path=/",))
    clock.advance(1.0)
    jar.store_from_headers(url, ("b=2; Path=/",))
    clock.advance(1.0)
    jar.store_from_headers(url, ("c=3; Path=/",))

    assert {cookie.name for cookie in jar.snapshot()} == {"b", "c"}


def test_global_cap_evicts_globally_earliest_cookie() -> None:
    clock = FakeClock(monotonic_start=0.0, epoch_start=100.0)
    jar = make_jar(clock, max_cookies_per_host=2, max_cookies_total=2)
    jar.store_from_headers(make_url("https", "a.example"), ("a=1; Path=/",))
    clock.advance(1.0)
    jar.store_from_headers(make_url("https", "b.example"), ("b=2; Path=/",))
    clock.advance(1.0)
    jar.store_from_headers(make_url("https", "a.example"), ("c=3; Path=/",))

    assert {(cookie.host, cookie.name) for cookie in jar.snapshot()} == {
        ("a.example", "c"),
        ("b.example", "b"),
    }


def test_global_cap_created_time_tie_breaks_deterministically_by_name() -> None:
    results: list[tuple[str, ...]] = []
    for _ in range(2):
        clock = FakeClock(monotonic_start=0.0, epoch_start=100.0)
        jar = make_jar(clock, max_cookies_per_host=2, max_cookies_total=2)
        jar.store_from_headers(make_url("https", "z.example"), ("z=1; Path=/",))
        jar.store_from_headers(make_url("https", "a.example"), ("a=2; Path=/",))
        jar.store_from_headers(make_url("https", "m.example"), ("m=3; Path=/",))
        results.append(tuple(cookie.name for cookie in jar.snapshot()))

    assert results[0] == results[1]
    assert "a" not in results[0]


def test_global_cap_created_time_tie_uses_sequence_before_name() -> None:
    clock = FakeClock(monotonic_start=0.0, epoch_start=100.0)
    jar = make_jar(clock, max_cookies_per_host=3, max_cookies_total=3)
    seed_url = make_url("https", "seed.example")
    host_url = make_url("https", "example.com")
    jar.store_from_headers(seed_url, ("seed=0; Path=/",))
    assert jar.header_for(seed_url).value == "seed=0"
    jar.store_from_headers(seed_url, ("seed=deleted; Max-Age=0",))
    jar.store_from_headers(host_url, ("a=1; Path=/a", "z=2; Path=/z"))
    assert jar.header_for(make_url("https", "example.com", "/a")).value == "a=1"
    clock.advance(1.0)
    jar.store_from_headers(host_url, ("new1=3; Path=/new1", "new2=4; Path=/new2"))

    assert {cookie.name for cookie in jar.snapshot()} == {"a", "new1", "new2"}


def test_cookie_store_byte_cap_evicts_oldest_cookie() -> None:
    clock = FakeClock(monotonic_start=0.0, epoch_start=100.0)
    jar = make_jar(
        clock,
        max_cookie_store_bytes=80,
        max_set_cookie_bytes=80,
        max_cookie_header_bytes=80,
    )
    url = make_url("https", "example.com")
    jar.store_from_headers(url, ("a=1; Path=/",))
    clock.advance(1.0)
    jar.store_from_headers(url, ("b=2; Path=/",))

    assert {cookie.name for cookie in jar.snapshot()} == {"b"}


def test_header_byte_cap_returns_complete_pairs_and_notice() -> None:
    clock = FakeClock(monotonic_start=0.0, epoch_start=100.0)
    jar = make_jar(clock, max_cookie_header_bytes=10)
    url = make_url("https", "example.com")
    jar.store_from_headers(url, ("a=1; Path=/", "b=12345678901234567890; Path=/",))

    result = jar.header_for(url)

    assert result.value == "a=1"
    assert result.notice is not None
    assert result.value is not None and result.value.endswith("a=1")


def test_header_byte_cap_reports_when_nothing_fits() -> None:
    clock = FakeClock(monotonic_start=0.0, epoch_start=100.0)
    jar = make_jar(clock, max_cookie_header_bytes=2)
    url = make_url("https", "example.com")
    jar.store_from_headers(url, ("a=123; Path=/",))

    result = jar.header_for(url)

    assert result.value is None
    assert result.notice is not None


def test_normal_header_has_no_notice() -> None:
    clock = FakeClock(monotonic_start=0.0, epoch_start=100.0)
    jar = make_jar(clock)
    url = make_url("https", "example.com")
    jar.store_from_headers(url, ("a=1; Path=/",))

    result = jar.header_for(url)

    assert result == CookieHeader(value="a=1", notice=None)


def test_send_order_is_longest_path_then_creation_then_name() -> None:
    clock = FakeClock(monotonic_start=0.0, epoch_start=100.0)
    jar = make_jar(clock)
    jar.store_from_headers(
        make_url("https", "example.com"),
        ("root=1; Path=/", "long=2; Path=/long", "z=3; Path=/same", "a=4; Path=/same"),
    )

    result = jar.header_for(make_url("https", "example.com", "/same"))

    assert result.value == "a=4; z=3; root=1"


def test_malformed_cookie_name_rejects_field() -> None:
    clock = FakeClock(monotonic_start=0.0, epoch_start=100.0)
    jar = make_jar(clock)

    jar.store_from_headers(make_url("https", "example.com"), ("bad name=1",))

    assert jar.snapshot() == ()


@pytest.mark.parametrize(
    "raw_value",
    (
        "a=bad\x00value",
        "a=bad value",
        'a="bad"',
        "a=bad,value",
        'a="bad;value"',
        "a=bad\\value",
    ),
)
def test_malformed_cookie_value_rejects_field(raw_value: str) -> None:
    clock = FakeClock(monotonic_start=0.0, epoch_start=100.0)
    jar = make_jar(clock)

    jar.store_from_headers(make_url("https", "example.com"), (raw_value,))

    assert jar.snapshot() == ()


def test_cookies_source_has_only_locked_import_dependencies() -> None:
    source_path = (
        Path(__file__).parents[1]
        / "src"
        / "terminal_browser"
        / "net"
        / "cookies.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    allowed_modules = {
        "dataclasses",
        "datetime",
        "typing",
        "pydantic",
        "core.clock",
        "core.errors",
        "core.limits",
        "url",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name in allowed_modules
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert module in allowed_modules
