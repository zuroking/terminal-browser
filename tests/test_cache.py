import ast
from datetime import datetime, timezone
from pathlib import Path

import pytest

from terminal_browser.core.clock import FakeClock
from terminal_browser.core.limits import Limits
from terminal_browser.net.cache import (
    CacheEntry,
    CacheKey,
    DiskCache,
    build_entry,
    compute_age_at_stored_epoch,
    is_cacheable,
    parse_http_date,
)
from terminal_browser.net.wire import HeaderFields
from terminal_browser.url import UrlParserImpl


LIMITS = Limits.defaults()


def limits(**overrides: int) -> Limits:
    return Limits.model_validate({**LIMITS.model_dump(), **overrides})


def make_entry(
    url: str,
    body: bytes = b"body",
    headers: HeaderFields = (),
    received_at_epoch: float = 100.0,
    limit_values: Limits = LIMITS,
) -> CacheEntry:
    result = build_entry(
        CacheKey(method="GET", normalized_url=url),
        200,
        "GET",
        headers,
        body,
        received_at_epoch,
        limit_values,
    )
    assert result is not None
    return result


def test_cacheability_for_valid_get_response() -> None:
    assert is_cacheable(200, "GET", (), 4, LIMITS)


@pytest.mark.parametrize(
    ("status", "method", "headers", "body_len"),
    (
        (404, "GET", (), 1),
        (200, "POST", (), 1),
        (200, "GET", (("cache-control", "no-store"),), 1),
        (200, "GET", (("vary", "Accept"),), 1),
        (200, "GET", (("vary", "*"),), 1),
        (200, "GET", (), 2_500_001),
    ),
)
def test_cacheability_rejects_ineligible_responses(
    status: int,
    method: str,
    headers: HeaderFields,
    body_len: int,
) -> None:
    assert not is_cacheable(status, method, headers, body_len, LIMITS)


def test_transfer_truncation_is_not_cacheable() -> None:
    assert not is_cacheable(200, "GET", (), 1, LIMITS, transfer_truncated=True)


def test_max_age_sets_freshness_deadline() -> None:
    result = make_entry("https://example.com/a", headers=(("cache-control", "max-age=60"),))

    assert result.fresh_until_epoch == 160.0


def test_expires_sets_freshness_deadline() -> None:
    expires = "Sun, 06 Nov 1994 09:49:37 GMT"
    received = parse_http_date("Sun, 06 Nov 1994 08:49:37 GMT")
    assert received is not None
    result = make_entry(
        "https://example.com/a",
        headers=(("expires", expires),),
        received_at_epoch=received,
    )

    assert result.fresh_until_epoch == parse_http_date(expires)


def test_max_age_wins_over_expires_and_keeps_expires_metadata() -> None:
    expires = "Sun, 06 Nov 1994 09:49:37 GMT"
    result = make_entry(
        "https://example.com/a",
        headers=(("cache-control", "max-age=60"), ("expires", expires)),
        received_at_epoch=100.0,
    )

    assert result.fresh_until_epoch == 160.0
    assert ("expires", expires) in result.headers


def test_last_modified_heuristic_caps_at_24_hours() -> None:
    last_modified = datetime(1994, 11, 6, 8, 49, 37, tzinfo=timezone.utc).timestamp()
    received = last_modified + 10 * 86_400
    result = make_entry(
        "https://example.com/a",
        headers=(("last-modified", "Sun, 06 Nov 1994 08:49:37 GMT"),),
        received_at_epoch=received,
    )

    assert result.fresh_until_epoch == received + 86_400


def test_last_modified_heuristic_uses_tenth_when_under_cap() -> None:
    last_modified = datetime(1994, 11, 6, 8, 49, 37, tzinfo=timezone.utc).timestamp()
    received = last_modified + 100
    result = make_entry(
        "https://example.com/a",
        headers=(("last-modified", "Sun, 06 Nov 1994 08:49:37 GMT"),),
        received_at_epoch=received,
    )

    assert result.fresh_until_epoch == received + 10


def test_no_explicit_freshness_is_immediately_stale() -> None:
    result = make_entry("https://example.com/a", received_at_epoch=100.0)

    assert result.fresh_until_epoch == 100.0


def test_age_uses_age_and_apparent_date() -> None:
    date_value = "Sun, 06 Nov 1994 08:49:37 GMT"
    date_epoch = parse_http_date(date_value)
    assert date_epoch is not None
    headers: HeaderFields = (("age", "30"), ("date", date_value))

    assert compute_age_at_stored_epoch(headers, date_epoch + 10.0) == 30.0


def test_age_with_invalid_date_uses_age_only() -> None:
    headers: HeaderFields = (("age", "7"), ("date", "invalid"))

    assert compute_age_at_stored_epoch(headers, 100.0) == 7.0


def test_http_date_formats_and_leap_second() -> None:
    expected = datetime(1994, 11, 6, 8, 49, 37, tzinfo=timezone.utc).timestamp()
    assert parse_http_date("Sun, 06 Nov 1994 08:49:37 GMT") == expected
    assert parse_http_date("Sunday, 06-Nov-94 08:49:37 GMT") == expected
    assert parse_http_date("Sunday, 06-Nov-'94 08:49:37 GMT") == expected
    assert parse_http_date("Sun Nov  6 08:49:37 1994") == expected
    assert parse_http_date("Sun, 06 Nov 1994 08:49:60 GMT") == expected + 22
    assert parse_http_date("not a date") is None


def test_quoted_max_age_matches_unquoted() -> None:
    quoted = make_entry("https://example.com/a", headers=(("cache-control", 'max-age="60"'),))
    plain = make_entry("https://example.com/b", headers=(("cache-control", "max-age=60"),))

    assert quoted.fresh_until_epoch == plain.fresh_until_epoch == 160.0


def test_conflicting_duplicate_max_age_is_not_cacheable() -> None:
    headers: HeaderFields = (
        ("cache-control", "max-age=60"),
        ("cache-control", "max-age=61"),
    )

    assert not is_cacheable(200, "GET", headers, 1, LIMITS)


def test_duplicate_no_store_is_harmless_but_non_cacheable() -> None:
    headers: HeaderFields = (
        ("cache-control", "no-store"),
        ("cache-control", "no-store"),
    )

    assert not is_cacheable(200, "GET", headers, 1, LIMITS)


def test_put_rejects_oversized_entry_without_mutating_cache(tmp_path: Path) -> None:
    small_limits = limits(
        cache_byte_budget=10,
        max_cache_entry_bytes=4,
        max_body_bytes=4,
        max_charset_prescan_bytes=4,
        chunk_read_size=4,
    )
    cache = DiskCache(tmp_path, small_limits, FakeClock(0.0, 100.0))
    oversized = CacheEntry(
        key=CacheKey(method="GET", normalized_url="https://example.com/large"),
        status=200,
        headers=(),
        body=b"12345",
        stored_at_epoch=100.0,
        fresh_until_epoch=100.0,
        etag=None,
        last_modified=None,
        body_len=5,
        age_at_stored_epoch=0.0,
    )

    assert cache.put(oversized) is False
    assert cache.byte_size() == 0


def test_disk_round_trip_uses_fresh_cache_instance(tmp_path: Path) -> None:
    clock = FakeClock(0.0, 100.0)
    first = DiskCache(tmp_path, LIMITS, clock)
    stored = make_entry("https://example.com/a", body=b"persisted")
    assert first.put(stored)

    second = DiskCache(tmp_path, LIMITS, clock)

    loaded = second.get(stored.key)
    assert loaded is not None
    assert loaded.body == b"persisted"
    assert loaded.headers == stored.headers


def test_corrupted_record_is_skipped_without_losing_other_entries(tmp_path: Path) -> None:
    clock = FakeClock(0.0, 100.0)
    first = DiskCache(tmp_path, LIMITS, clock)
    first_entry = make_entry("https://example.com/first")
    second_entry = make_entry("https://example.com/second")
    assert first.put(first_entry)
    assert first.put(second_entry)
    paths = sorted(tmp_path.glob("*.cache"))
    paths[0].write_bytes(b"corrupt")

    loaded_cache = DiskCache(tmp_path, LIMITS, clock)

    assert sum(
        loaded_cache.get(key.key) is not None
        for key in (first_entry, second_entry)
    ) == 1


def test_unsupported_record_version_is_skipped(tmp_path: Path) -> None:
    clock = FakeClock(0.0, 100.0)
    first = DiskCache(tmp_path, LIMITS, clock)
    stored = make_entry("https://example.com/a")
    assert first.put(stored)
    record_path = next(tmp_path.glob("*.cache"))
    record_path.write_bytes(b"BAD1\xff")

    loaded_cache = DiskCache(tmp_path, LIMITS, clock)

    assert loaded_cache.get(stored.key) is None


def test_atomic_write_leaves_no_temporary_files(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path, LIMITS, FakeClock(0.0, 100.0))
    stored = make_entry("https://example.com/a")

    assert cache.put(stored)
    assert not any(path.name.endswith(".tmp") for path in tmp_path.iterdir())


def test_lru_evicts_oldest_accessed_entry_and_respects_budget(tmp_path: Path) -> None:
    small_limits = limits(
        cache_byte_budget=500,
        max_cache_entry_bytes=250,
        max_body_bytes=250,
        max_charset_prescan_bytes=250,
        chunk_read_size=250,
    )
    cache = DiskCache(tmp_path, small_limits, FakeClock(0.0, 100.0))
    first = make_entry("https://example.com/1", body=b"a" * 50, limit_values=small_limits)
    second = make_entry("https://example.com/2", body=b"b" * 50, limit_values=small_limits)
    third = make_entry("https://example.com/3", body=b"c" * 50, limit_values=small_limits)
    fourth = make_entry("https://example.com/4", body=b"d" * 50, limit_values=small_limits)
    assert cache.put(first)
    assert cache.byte_size() <= small_limits.cache_byte_budget
    assert cache.put(second)
    assert cache.byte_size() <= small_limits.cache_byte_budget
    assert cache.put(third)
    assert cache.byte_size() <= small_limits.cache_byte_budget
    assert cache.get(first.key) is not None
    assert cache.put(fourth)
    assert cache.byte_size() <= small_limits.cache_byte_budget

    assert cache.get(first.key) is not None
    assert cache.get(fourth.key) is not None
    assert cache.byte_size() <= small_limits.cache_byte_budget


def test_invalidate_returns_zero_or_one_and_removes_entry(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path, LIMITS, FakeClock(0.0, 100.0))
    stored = make_entry("https://example.com/a")
    assert cache.put(stored)

    assert cache.invalidate(stored.key.normalized_url) == 1
    assert cache.invalidate(stored.key.normalized_url) == 0
    assert cache.get(stored.key) is None


def test_cache_key_preserves_normalized_query_bytes(tmp_path: Path) -> None:
    parser = UrlParserImpl(LIMITS)
    parsed = parser.parse("http://example.com/?b=2&a=1&b=1")
    key = CacheKey(
        method="GET",
        normalized_url=parser.normalize_for_cache(parsed),
    )
    cache = DiskCache(tmp_path, LIMITS, FakeClock(0.0, 100.0))
    stored = make_entry(key.normalized_url)

    assert cache.put(stored)
    assert cache.get(key) is not None
    assert key.normalized_url.endswith("?b=2&a=1&b=1")


def test_cache_source_has_only_locked_import_dependencies() -> None:
    source_path = (
        Path(__file__).parents[1]
        / "src"
        / "terminal_browser"
        / "net"
        / "cache.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    allowed_modules = {
        "dataclasses",
        "datetime",
        "hashlib",
        "pathlib",
        "struct",
        "typing",
        "pydantic",
        "core.clock",
        "core.errors",
        "core.limits",
        "wire",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name in allowed_modules
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert module in allowed_modules
