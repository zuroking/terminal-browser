from typing import Protocol, Self

from pydantic import BaseModel, ConfigDict, model_validator


class Limits(BaseModel):
    """Bounded numeric limits used across the browser."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    connect_timeout_sec: float
    dns_timeout_sec: float
    read_timeout_sec: float
    total_response_timeout_sec: float
    navigation_timeout_sec: float
    max_redirects: int
    max_history: int
    max_body_bytes: int
    max_decompressed_bytes: int
    cache_byte_budget: int
    max_cache_entry_bytes: int
    max_header_size: int
    max_header_count: int
    max_interim_responses: int
    max_dom_depth: int
    max_nodes: int
    max_tokens: int
    chunk_read_size: int
    terminal_width_fallback: int
    min_layout_width: int
    max_render_lines: int
    max_line_width: int
    max_url_len: int
    max_charset_prescan_bytes: int
    max_cookies_per_host: int
    max_cookies_total: int
    max_cookie_store_bytes: int
    max_set_cookie_bytes: int
    max_form_fields: int
    max_form_bytes: int
    max_cookie_header_bytes: int
    max_repl_line_bytes: int
    max_repl_tokens: int

    @classmethod
    def defaults(cls) -> "Limits":
        """Return the documented default limits through model validation."""
        return cls(
            connect_timeout_sec=5.0,
            dns_timeout_sec=5.0,
            read_timeout_sec=10.0,
            total_response_timeout_sec=30.0,
            navigation_timeout_sec=60.0,
            max_redirects=5,
            max_history=100,
            max_body_bytes=2_000_000,
            max_decompressed_bytes=5_000_000,
            cache_byte_budget=10_000_000,
            max_cache_entry_bytes=2_500_000,
            max_header_size=65_536,
            max_header_count=100,
            max_interim_responses=5,
            max_dom_depth=64,
            max_nodes=25_000,
            max_tokens=100_000,
            chunk_read_size=16_384,
            terminal_width_fallback=80,
            min_layout_width=4,
            max_render_lines=5_000,
            max_line_width=120,
            max_url_len=8_192,
            max_charset_prescan_bytes=1_024,
            max_cookies_per_host=50,
            max_cookies_total=500,
            max_cookie_store_bytes=65_536,
            max_set_cookie_bytes=8_192,
            max_form_fields=256,
            max_form_bytes=16_384,
            max_cookie_header_bytes=8_192,
            max_repl_line_bytes=4_096,
            max_repl_tokens=64,
        )

    @model_validator(mode="after")
    def validate_constraints(self) -> Self:
        """Validate positivity and all documented cross-field constraints."""
        positive_values = (
            self.connect_timeout_sec,
            self.dns_timeout_sec,
            self.read_timeout_sec,
            self.total_response_timeout_sec,
            self.navigation_timeout_sec,
            self.max_redirects,
            self.max_history,
            self.max_body_bytes,
            self.max_decompressed_bytes,
            self.cache_byte_budget,
            self.max_cache_entry_bytes,
            self.max_header_size,
            self.max_header_count,
            self.max_interim_responses,
            self.max_dom_depth,
            self.max_nodes,
            self.max_tokens,
            self.chunk_read_size,
            self.terminal_width_fallback,
            self.min_layout_width,
            self.max_render_lines,
            self.max_line_width,
            self.max_url_len,
            self.max_charset_prescan_bytes,
            self.max_cookies_per_host,
            self.max_cookies_total,
            self.max_cookie_store_bytes,
            self.max_set_cookie_bytes,
            self.max_form_fields,
            self.max_form_bytes,
            self.max_cookie_header_bytes,
            self.max_repl_line_bytes,
            self.max_repl_tokens,
        )
        if any(value <= 0 for value in positive_values):
            raise ValueError("all limits must be positive")
        if self.dns_timeout_sec > self.connect_timeout_sec:
            raise ValueError("dns_timeout_sec must not exceed connect_timeout_sec")
        if self.read_timeout_sec > self.total_response_timeout_sec:
            raise ValueError(
                "read_timeout_sec must not exceed total_response_timeout_sec"
            )
        if self.total_response_timeout_sec > self.navigation_timeout_sec:
            raise ValueError(
                "total_response_timeout_sec must not exceed navigation_timeout_sec"
            )
        if self.max_cache_entry_bytes > self.cache_byte_budget:
            raise ValueError(
                "max_cache_entry_bytes must not exceed cache_byte_budget"
            )
        if self.max_body_bytes > self.max_cache_entry_bytes:
            raise ValueError(
                "max_body_bytes must not exceed max_cache_entry_bytes"
            )
        if self.max_cache_entry_bytes >= self.cache_byte_budget:
            raise ValueError(
                "max_cache_entry_bytes must be less than cache_byte_budget"
            )
        if self.max_set_cookie_bytes > self.max_cookie_store_bytes:
            raise ValueError(
                "max_set_cookie_bytes must not exceed max_cookie_store_bytes"
            )
        if self.max_cookies_per_host > self.max_cookies_total:
            raise ValueError(
                "max_cookies_per_host must not exceed max_cookies_total"
            )
        if self.min_layout_width < 4:
            raise ValueError("min_layout_width must be at least 4")
        if self.min_layout_width > self.terminal_width_fallback:
            raise ValueError(
                "min_layout_width must not exceed terminal_width_fallback"
            )
        if self.terminal_width_fallback > self.max_line_width:
            raise ValueError(
                "terminal_width_fallback must not exceed max_line_width"
            )
        if self.max_dom_depth >= self.max_nodes:
            raise ValueError("max_dom_depth must be less than max_nodes")
        if self.max_nodes > self.max_tokens:
            raise ValueError("max_nodes must not exceed max_tokens")
        if self.max_form_fields > self.max_nodes:
            raise ValueError("max_form_fields must not exceed max_nodes")
        if self.max_charset_prescan_bytes > self.max_body_bytes:
            raise ValueError(
                "max_charset_prescan_bytes must not exceed max_body_bytes"
            )
        if self.max_cookie_header_bytes > self.max_cookie_store_bytes:
            raise ValueError(
                "max_cookie_header_bytes must not exceed max_cookie_store_bytes"
            )
        if self.max_repl_line_bytes > self.max_form_bytes:
            raise ValueError("max_repl_line_bytes must not exceed max_form_bytes")
        if self.max_repl_tokens > self.max_form_fields:
            raise ValueError("max_repl_tokens must not exceed max_form_fields")
        if self.chunk_read_size > self.max_body_bytes:
            raise ValueError("chunk_read_size must not exceed max_body_bytes")
        if self.max_render_lines < 16:
            raise ValueError("max_render_lines must be at least 16")
        return self


class LimitProvider(Protocol):
    def get_limits(self) -> Limits:
        """Return the limits used by a bounded operation."""
        raise NotImplementedError


class LimitsFactory(Protocol):
    def defaults(self) -> Limits:
        """Return the default limits."""
        raise NotImplementedError
