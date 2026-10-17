# terminal-browser

**Languages:** English · [Русский](README_ru.md)

`terminal-browser` is a bounded, text-only HTTP/1.1 browser written in Python. It fetches `http://` and `https://` resources, parses a documented HTML subset, extracts basic forms, renders readable text, and routes terminal output through one sanitized egress point. (§1 G1–G8, §2.2)

> **Scope:** this is a text reader, not a complete browser. It does not execute JavaScript, implement CSS, download or rasterize images, speak HTTP/2, open WebSockets, browse `iframe` contexts, provide authentication or proxy support, decode Brotli/zstd, pool keep-alive connections, or widen cookie scope. (§1 N1–N10)

## Table of contents

- [Purpose](#purpose)
- [Non-goals](#non-goals)
- [Installation](#installation)
- [REPL usage](#repl-usage)
- [One-shot usage](#one-shot-usage)
- [Flags and exit codes](#flags-and-exit-codes)
- [Limits overview](#limits-overview)
- [Security](#security)
- [Development](#development)
- [License](#license)

## Purpose

The project is an educational implementation of a bounded browser pipeline: network transport, deterministic decoding, incremental HTML parsing, forms, layout, session history, and terminal output. (§1 G1–G9)

Every read, decode, parse, form, render, cache, cookie, and history operation is governed by a named numeric limit. (§1 G7, §6)

## Non-goals

The following boundaries are normative:

- **N1:** no JavaScript execution. (§1 N1, §12 DD-01)
- **N2:** no CSS selection, cascade, colors, or visual layout. (§1 N2, §12 DD-02)
- **N3:** no image fetching, decoding, or raster rendering; only `alt` text is used. (§1 N3, §12 DD-03)
- **N4:** no HTTP/2, ALPN, HPACK, multiplexing, or server push. (§1 N4, §12 DD-04)
- **N5:** no WebSockets or persistent bidirectional channels. (§1 N5, §12 DD-05)
- **N6:** no `iframe` browsing contexts. (§1 N6, §12 DD-06)
- **N7:** no authentication flows or proxy support. (§1 N7, §12 DD-07)
- **N8:** no Brotli, zstd, or content codings beyond `gzip` and `deflate`. (§1 N8, §12 DD-08)
- **N9:** no keep-alive connection pooling; every request sends `Connection: close`. (§1 N9, §12 DD-21)
- **N10:** no cookie `Domain=` widening; cookies remain host-only. (§1 N10, §12 DD-10)

## Installation

The source tree targets Python 3.12+ and Pydantic v2. (§1, §2.3 R7)

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# POSIX:   source .venv/bin/activate
python -m pip install "pydantic>=2" pytest mypy
```

The architecture defines the CLI grammar but does not prescribe a packaging entry-point name. The examples below show that grammar; the application composition root must provide the launcher. (§3.16, §10.2)

## REPL usage

With no `--url`, the application selects the interactive line-based REPL. (§10.1, §10.2)

```text
open https://example.test/
follow 1
back
forward
submit 1 name=value
quit
```

The input is bounded by `MAX_REPL_LINE_BYTES=4_096` and `MAX_REPL_TOKENS=64`; an over-limit line is discarded rather than parsed. (§6, §10.1)

## One-shot usage

With `--url URL`, the application performs one navigation and exits instead of entering the REPL. (§10.2)

```bash
python -m terminal_browser.cli --url https://example.test/
```

The one-shot result is `0` for a completed navigation and `1` for a handled navigation failure. (§10.2)

## Flags and exit codes

| Flag | Behavior |
|---|---|
| `--url URL` | Selects one-shot navigation. (§10.2) |
| `--width N` | Selects an explicit terminal width. (§10.2) |
| `--no-cache` | Bypasses cache reads, revalidation, and writes. (§10.2) |
| `--debug` | Adds a sanitized traceback to unexpected-error diagnostics. (§7.3, §10.2) |

| Exit code | Meaning |
|---:|---|
| `0` | Normal exit, successful one-shot navigation, or `quit`. (§10.2) |
| `1` | Handled one-shot navigation failure or top-level unexpected exception. (§7.3, §10.2) |
| `2` | Argument parsing or validation failure. (§10.2) |
| `130` | `KeyboardInterrupt`. (§7.3, §10.2) |

## Limits overview

The default values below are the proposed values from §6; the table cites the enforcing section for every value.

| Constant | Default |
|---|---:|
| `CONNECT_TIMEOUT_SEC` | `5.0` (§6) |
| `DNS_TIMEOUT_SEC` | `5.0` (§6) |
| `READ_TIMEOUT_SEC` | `10.0` (§6) |
| `TOTAL_RESPONSE_TIMEOUT_SEC` | `30.0` (§6) |
| `NAVIGATION_TIMEOUT_SEC` | `60.0` (§6) |
| `MAX_REDIRECTS` | `5` (§6) |
| `MAX_HISTORY` | `100` (§6) |
| `MAX_BODY_BYTES` | `2_000_000` (§6) |
| `MAX_DECOMPRESSED_BYTES` | `5_000_000` (§6) |
| `CACHE_BYTE_BUDGET` | `10_000_000` (§6) |
| `MAX_CACHE_ENTRY_BYTES` | `2_500_000` (§6) |
| `MAX_HEADER_SIZE` | `65_536` (§6) |
| `MAX_HEADER_COUNT` | `100` (§6) |
| `MAX_INTERIM_RESPONSES` | `5` (§6) |
| `MAX_DOM_DEPTH` | `64` (§6) |
| `MAX_NODES` | `25_000` (§6, §12 DD-12) |
| `MAX_TOKENS` | `100_000` (§6) |
| `CHUNK_READ_SIZE` | `16_384` (§6) |
| `TERMINAL_WIDTH_FALLBACK` | `80` (§6) |
| `MIN_LAYOUT_WIDTH` | `4` (§6) |
| `MAX_RENDER_LINES` | `5_000` (§6) |
| `MAX_LINE_WIDTH` | `120` (§6) |
| `MAX_URL_LEN` | `8_192` (§6) |
| `MAX_CHARSET_PRESCAN_BYTES` | `1_024` (§6) |
| `MAX_COOKIES_PER_HOST` | `50` (§6) |
| `MAX_COOKIES_TOTAL` | `500` (§6) |
| `MAX_COOKIE_STORE_BYTES` | `65_536` (§6) |
| `MAX_SET_COOKIE_BYTES` | `8_192` (§6) |
| `MAX_FORM_FIELDS` | `256` (§6) |
| `MAX_FORM_BYTES` | `16_384` (§6) |
| `MAX_COOKIE_HEADER_BYTES` | `8_192` (§6) |
| `MAX_REPL_LINE_BYTES` | `4_096` (§6) |
| `MAX_REPL_TOKENS` | `64` (§6) |

## Security

The browser sanitizes untrusted text at construction and again at terminal egress, and TLS certificate and hostname verification are unconditional. (§4, §5 I1–I2, §10.7)

Only `term/output.py` accesses stdout, stderr, or an output stream. (§2.3 R9, §10.7)

See [SECURITY.md](SECURITY.md) for the security boundary, reporting expectations, and residual DNS risk. For Russian, see [SECURITY_ru.md](SECURITY_ru.md).

## Development

The implementation order and required evidence are defined in [ARCHITECTURE.md](ARCHITECTURE.md) §11 and [PROTOCOL.md](PROTOCOL.md). Run the full test suite and strict type checker with raw terminal evidence after each module. (§11, process constraints in `CLAUDE.md`)

## License

[MIT](LICENSE) © 2026 Zuro
