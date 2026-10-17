# Changelog

All notable changes to `terminal-browser` are documented here. The entries follow the locked build order in `ARCHITECTURE.md` §11; they describe completed implementation work, not a future roadmap. (§11)

## [2.0.0] — 2026-09-24

The completed v2 implementation contains all 21 modules in the architecture's build order. (§11)

### Added

- `core/errors.py`: sole `BrowserError` exception root and frozen strict `ErrorInfo`. (§3.1, §7)
- `core/limits.py`: frozen strict resource limits and cross-cap validation. (§3.2, §6)
- `core/clock.py`: monotonic/epoch clock seam with `SystemClock` and deterministic `FakeClock`. (§3.3, §10.4)
- `core/encoding.py`: bounded charset detection and replacement decoding. (§3.4, §8.2)
- `core/sanitize.py`: construction-time text and attribute sanitization. (§3.5, §4)
- `core/text.py`: shared display-width policy for terminal cells. (§3.6, §8.6)
- `url.py`: HTTP(S) parsing, IDNA/IPv6 handling, relative resolution, and narrow cache normalization. (§3.9, §8.1)
- `net/transport.py`: bounded socket, TLS, DNS, connect, and read transport. (§3.6, §3.10, §10.3)
- `net/wire.py`: pure HTTP/1.1 status, header, chunk, and trailer parsing. (§3.7, §9.4, §10.5)
- `net/cookies.py`: clock-backed host-only cookie jar with bounded eviction and send ordering. (§3.8, §9.6)
- `net/cache.py`: bounded LRU and disk cache with validators and HTTP cache directives. (§3.9, §9.5, §10.6)
- `net/http.py`: request framing, redirects, deadlines, cookies, cache, decoding, and response dispatch. (§3.10, §9.1–§9.5)
- `html/entities.py`: HTML4-style entities plus `apos`, numeric references, and context rules. (§3.11, §8.4)
- `html/tokenizer.py`: incremental lazy tokenizer with lexical modes and hard token caps. (§3.12, §8.4)
- `html/tree.py`: bounded DOM builder, recovery, base/link resolution, sanitization, and visible truncation. (§3.12, §8.3–§8.4)
- `forms.py`: form extraction, successful controls, labels, GET/POST serialization, and limits. (§3.14, §8.5)
- `render/layout.py`: deterministic width-aware text layout, links, forms, tables, and truncation notices. (§3.13, §8.6–§8.9)
- `term/output.py`: sole stdout/stderr owner with construction/egress defense in depth. (§3.13, §4, §10.7)
- `session/session.py`: navigation pipeline, atomic history, forms, BrowserError views, and POST replay. (§3.15, §7.3, §9.7–§9.8)
- `ui/repl.py`: bounded line REPL, command dispatch, width resolution, and exit handling. (§3.16, §10.1)
- `cli.py`: argument parsing, dependency composition, one-shot/interactive modes, exit codes, and top-level catch-all. (§3.16, §7.3, §10.2)
- Normative AST egress coverage: `tests/test_egress.py` scans production Python files and excludes only `term/output.py`. (§10.7)

### Changed

- The v1 cache-key correction preserves query bytes byte-for-byte, including order, duplicates, percent-escape spelling, and case. (§8.1)
- The v1 cacheability correction makes any response with `Vary` non-cacheable. (§9.5)
- The complete local suite is green: `390` tests passed; strict mypy is clean. (§10.9, §11; repository verification)

### Fixed

- The terminal egress test now rejects `print`, direct standard-stream access and aliases, `os.write`, and imported or opened output streams outside `term/output.py`. (§10.7)
- The final CLI boundary preserves `KeyboardInterrupt` as exit code `130`, re-raises `SystemExit`, and sanitizes debug tracebacks. (§7.3, §10.2)

### Deliberate deviation record

- DD-13 is recorded in this process history as approved in-session for implementation to proceed. `ARCHITECTURE.md` still labels DD-13 `[APPROVAL REQUIRED]`, so architectural reconciliation remains required before the record can be treated as fully synchronized. (§12 DD-13)

### Verification

- Full test evidence: `390 passed`. (§10.9, §11)
- Type evidence: `mypy --strict` passed for the final implementation and tests. (§11)
