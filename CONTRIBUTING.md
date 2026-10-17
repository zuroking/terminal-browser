# Contributing to `terminal-browser`

## What this project is

`terminal-browser` is a bounded, educational HTTP/1.1 text browser. Its purpose is to demonstrate explicit architecture, deterministic limits, and reviewable engineering rather than to provide a general-purpose browser. (§1, §2.3)

Read `ARCHITECTURE.md` before proposing work. The architecture is the source of truth, and deliberate scope boundaries are recorded in §12. (§2.3, §12)

## Before opening anything

Start with `ARCHITECTURE.md` and its locked decisions, non-goals, module graph, and Deliberate Deviations. A missing feature may be a deliberate boundary rather than an oversight. (§1, §2, §12)

## What is welcome

- Bug reports when behavior contradicts `ARCHITECTURE.md`, with a minimal reproduction and the violated section. (§1–§12)
- Documentation corrections, broken relative links, and EN/RU inconsistencies. (process constraint in `CLAUDE.md`)
- Regression tests for an architectural behavior that lacks required coverage. (§10.9)

## What is outside scope

- Features that expand the locked browser scope without an architecture update. (§1 N1–N10, §2.3, §12)
- JavaScript, CSS, image bytes, HTTP/2, WebSockets, `iframe`, authentication/proxy, Brotli/zstd, keep-alive pooling, and cookie-domain widening. (§1 N1–N10, §12 DD-01–DD-10, DD-21)
- Dependency additions outside the architecture's Pydantic v2 runtime boundary. (§2.3 R7, R8)

## One-module-at-a-time workflow

1. Select one module from the §11 build order.
2. Implement only that module and its directly required behavior.
3. Stop after the module; do not silently continue to the next module. (§11)
4. Add the module's required tests from the §10.9 matrix. (§10.9)
5. Add an AST import-boundary test that proves the module imports only the dependencies allowed by §2.2. (§2.2, §10.9)
6. Run `pytest -v` and `mypy --strict` after the module and preserve the complete raw terminal output. (§11, `CLAUDE.md`)

## Evidence rules

Raw evidence means the complete command output from `collecting ...` through the final test summary for `pytest -v`, and the complete output of the explicit `mypy --strict` command. A summary, paraphrase, screenshot, truncated paste, or selected subset is not evidence. (§11, `CLAUDE.md`)

Every acceptance claim must name the command, preserve the full output, and identify the module or requirement proven. (§11, `CLAUDE.md`)

## Test names prove requirements

A test name must state the behavior it proves. Prefer names such as `test_failed_navigation_preserves_state` over names such as `test_session_2`; the name is part of the reviewable evidence. (§10.9, process constraint in `CLAUDE.md`)

A test that only checks a type shape, an import, or a successful happy path does not prove an atomicity, timeout, security, or error-ownership requirement unless the assertion explicitly demonstrates that behavior. (§5, §7.3, §10.9)

## Network and test isolation

Tests must not contact the real network. Use local socket fixtures, scripted transports, fake clocks, and injected output buffers. (§1 G9, §10.3–§10.5, `CLAUDE.md`)

Do not add a public-network integration test to replace a deterministic fixture. (§1 G9, §10.3–§10.5)

## Deviations

Before changing a locked decision, record the proposed departure, its technical rationale, affected sections, and approval status in `ARCHITECTURE.md` §12. Do not implement the deviation first and document it later. (§2.3, §12)

DD-13 is the DNS-resolution deviation from locked decision #8; the architecture currently marks approval as required. (§12 DD-13)

## Review checklist

Before requesting review, confirm:

- the change is one module or one explicitly documented deviation; (§11, §12)
- required tests and AST boundary tests exist; (§10.9)
- `pytest -v` and `mypy --strict` raw output is attached; (§11)
- no real network was used; (§1 G9, §10.3–§10.5)
- EN and RU documentation remain section-for-section mirrors when documentation changes. (process constraint in `CLAUDE.md`)

## License

Contributions are distributed under the [MIT License](LICENSE).
