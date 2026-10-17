import pytest
from pydantic import ValidationError

from terminal_browser.core.limits import Limits


EXPECTED_DEFAULTS: dict[str, object] = {
    "connect_timeout_sec": 5.0,
    "dns_timeout_sec": 5.0,
    "read_timeout_sec": 10.0,
    "total_response_timeout_sec": 30.0,
    "navigation_timeout_sec": 60.0,
    "max_redirects": 5,
    "max_history": 100,
    "max_body_bytes": 2_000_000,
    "max_decompressed_bytes": 5_000_000,
    "cache_byte_budget": 10_000_000,
    "max_cache_entry_bytes": 2_500_000,
    "max_header_size": 65_536,
    "max_header_count": 100,
    "max_interim_responses": 5,
    "max_dom_depth": 64,
    "max_nodes": 25_000,
    "max_tokens": 100_000,
    "chunk_read_size": 16_384,
    "terminal_width_fallback": 80,
    "min_layout_width": 4,
    "max_render_lines": 5_000,
    "max_line_width": 120,
    "max_url_len": 8_192,
    "max_charset_prescan_bytes": 1_024,
    "max_cookies_per_host": 50,
    "max_cookies_total": 500,
    "max_cookie_store_bytes": 65_536,
    "max_set_cookie_bytes": 8_192,
    "max_form_fields": 256,
    "max_form_bytes": 16_384,
    "max_cookie_header_bytes": 8_192,
    "max_repl_line_bytes": 4_096,
    "max_repl_tokens": 64,
}


def limits_data(**overrides: object) -> dict[str, object]:
    data = dict(EXPECTED_DEFAULTS)
    data.update(overrides)
    return data


def test_limits_fields_match_architecture() -> None:
    assert tuple(Limits.model_fields) == tuple(EXPECTED_DEFAULTS)


def test_limits_defaults_snapshot() -> None:
    assert Limits.defaults().model_dump() == EXPECTED_DEFAULTS


@pytest.mark.parametrize("field", tuple(EXPECTED_DEFAULTS))
def test_every_limit_is_positive(field: str) -> None:
    with pytest.raises(ValidationError):
        Limits.model_validate(limits_data(**{field: 0}))


def test_default_limits_are_valid() -> None:
    assert isinstance(Limits.defaults(), Limits)


def test_dns_timeout_does_not_exceed_connect_timeout() -> None:
    with pytest.raises(ValidationError):
        Limits.model_validate(limits_data(dns_timeout_sec=5.1))
    assert isinstance(
        Limits.model_validate(limits_data(dns_timeout_sec=5.0)),
        Limits,
    )


def test_read_timeout_does_not_exceed_total_response_timeout() -> None:
    with pytest.raises(ValidationError):
        Limits.model_validate(limits_data(total_response_timeout_sec=9.9))
    assert isinstance(
        Limits.model_validate(limits_data(total_response_timeout_sec=10.0)),
        Limits,
    )


def test_total_response_timeout_does_not_exceed_navigation_timeout() -> None:
    with pytest.raises(ValidationError):
        Limits.model_validate(limits_data(navigation_timeout_sec=29.9))
    assert isinstance(
        Limits.model_validate(limits_data(navigation_timeout_sec=30.0)),
        Limits,
    )


def test_cache_entry_does_not_exceed_cache_budget() -> None:
    with pytest.raises(ValidationError):
        Limits.model_validate(limits_data(cache_byte_budget=2_499_999))
    assert isinstance(
        Limits.model_validate(limits_data(cache_byte_budget=2_500_001)),
        Limits,
    )


def test_body_does_not_exceed_cache_entry() -> None:
    with pytest.raises(ValidationError):
        Limits.model_validate(limits_data(max_body_bytes=2_500_001))
    assert isinstance(
        Limits.model_validate(limits_data(max_body_bytes=2_500_000)),
        Limits,
    )


def test_cache_entry_is_less_than_cache_budget() -> None:
    with pytest.raises(ValidationError):
        Limits.model_validate(
            limits_data(
                cache_byte_budget=2_500_000,
                max_cache_entry_bytes=2_500_000,
            )
        )
    assert isinstance(
        Limits.model_validate(
            limits_data(
                cache_byte_budget=2_500_001,
                max_cache_entry_bytes=2_500_000,
            )
        ),
        Limits,
    )


def test_set_cookie_size_does_not_exceed_cookie_store() -> None:
    with pytest.raises(ValidationError):
        Limits.model_validate(limits_data(max_set_cookie_bytes=65_537))
    assert isinstance(
        Limits.model_validate(limits_data(max_set_cookie_bytes=65_536)),
        Limits,
    )


def test_cookies_per_host_do_not_exceed_total_cookies() -> None:
    with pytest.raises(ValidationError):
        Limits.model_validate(limits_data(max_cookies_per_host=501))
    assert isinstance(
        Limits.model_validate(limits_data(max_cookies_per_host=500)),
        Limits,
    )


def test_minimum_layout_width_is_at_least_four() -> None:
    with pytest.raises(ValidationError):
        Limits.model_validate(limits_data(min_layout_width=3))
    assert isinstance(Limits.model_validate(limits_data(min_layout_width=4)), Limits)


def test_minimum_layout_width_does_not_exceed_fallback() -> None:
    with pytest.raises(ValidationError):
        Limits.model_validate(limits_data(terminal_width_fallback=3))
    assert isinstance(
        Limits.model_validate(limits_data(terminal_width_fallback=4)),
        Limits,
    )


def test_fallback_width_does_not_exceed_maximum_line_width() -> None:
    with pytest.raises(ValidationError):
        Limits.model_validate(limits_data(max_line_width=79))
    assert isinstance(
        Limits.model_validate(limits_data(max_line_width=80)),
        Limits,
    )


def test_dom_depth_is_less_than_node_limit() -> None:
    with pytest.raises(ValidationError):
        Limits.model_validate(limits_data(max_dom_depth=25_000))
    assert isinstance(
        Limits.model_validate(
            limits_data(max_dom_depth=64, max_nodes=65, max_form_fields=65)
        ),
        Limits,
    )


def test_node_limit_does_not_exceed_token_limit() -> None:
    with pytest.raises(ValidationError):
        Limits.model_validate(limits_data(max_tokens=24_999))
    assert isinstance(
        Limits.model_validate(limits_data(max_tokens=25_000)),
        Limits,
    )


def test_form_fields_do_not_exceed_node_limit() -> None:
    with pytest.raises(ValidationError):
        Limits.model_validate(limits_data(max_form_fields=25_001))
    assert isinstance(
        Limits.model_validate(limits_data(max_form_fields=25_000)),
        Limits,
    )


def test_charset_prescan_does_not_exceed_body_limit() -> None:
    with pytest.raises(ValidationError):
        Limits.model_validate(limits_data(max_charset_prescan_bytes=2_000_001))
    assert isinstance(
        Limits.model_validate(limits_data(max_charset_prescan_bytes=2_000_000)),
        Limits,
    )


def test_cookie_header_does_not_exceed_cookie_store() -> None:
    with pytest.raises(ValidationError):
        Limits.model_validate(limits_data(max_cookie_header_bytes=65_537))
    assert isinstance(
        Limits.model_validate(limits_data(max_cookie_header_bytes=65_536)),
        Limits,
    )


def test_repl_line_does_not_exceed_form_bytes() -> None:
    with pytest.raises(ValidationError):
        Limits.model_validate(limits_data(max_repl_line_bytes=16_385))
    assert isinstance(
        Limits.model_validate(limits_data(max_repl_line_bytes=16_384)),
        Limits,
    )


def test_repl_tokens_do_not_exceed_form_fields() -> None:
    with pytest.raises(ValidationError):
        Limits.model_validate(limits_data(max_repl_tokens=257))
    assert isinstance(
        Limits.model_validate(limits_data(max_repl_tokens=256)),
        Limits,
    )


def test_chunk_read_size_does_not_exceed_body_limit() -> None:
    with pytest.raises(ValidationError):
        Limits.model_validate(limits_data(chunk_read_size=2_000_001))
    assert isinstance(
        Limits.model_validate(limits_data(chunk_read_size=2_000_000)),
        Limits,
    )


def test_render_lines_have_required_minimum() -> None:
    with pytest.raises(ValidationError):
        Limits.model_validate(limits_data(max_render_lines=15))
    assert isinstance(
        Limits.model_validate(limits_data(max_render_lines=16)),
        Limits,
    )


def test_limits_instances_are_immutable() -> None:
    limits = Limits.defaults()

    with pytest.raises(ValidationError):
        limits.max_nodes = 1
