# PROTOCOL.md

## Purpose

This document defines the reviewable workflow for `terminal-browser`. It is a process contract, not a replacement for `ARCHITECTURE.md`; architecture remains the source of truth. (§2.3, §11)

## Roles

- **Owner:** sets scope, makes final architectural decisions, approves deviations, and accepts the module evidence. (§12)
- **Implementer:** implements one module at a time in the §11 build order, writes tests, and produces raw evidence. (§11, process constraint in `CLAUDE.md`)
- **Architectural reviewer:** checks consistency with the locked architecture, challenges implicit assumptions, and rejects unsupported or incomplete evidence. (§1, §12, process constraint in `CLAUDE.md`)

The roles are not interchangeable: the implementer proposes and builds, the reviewer checks, and the owner decides. (process constraint in `CLAUDE.md`)

## Evidence rules

Only raw, complete terminal output is evidence:

- `pytest -v` must include the complete run from `collecting ...` through the final `N passed` summary.
- `mypy --strict` must include the exact command and its complete output.
- A summary, paraphrase, screenshot, selected test subset, or truncated paste is rejected. (§11, process constraint in `CLAUDE.md`)

Every claim must identify the command, the complete output, and the module or requirement it proves. (§11, process constraint in `CLAUDE.md`)

## Test names prove requirements

A test name must describe the behavior under test. A name such as `test_failed_navigation_preserves_state` is stronger evidence than a generic or implementation-only name. (§10.9, process constraint in `CLAUDE.md`)

The test must assert the named requirement. A happy-path test does not prove timeout enforcement, atomic history, security sanitization, or exception propagation unless those conditions are explicitly asserted. (§5, §7.3, §10.9)

## Batching rule

Work is batched by leaf modules only. A module is implemented after its listed dependencies, then implementation stops until its tests, boundary test, and raw evidence are reviewed. (§11)

Dependency order is the §11 build order; convenience does not override it. (§2.3, §11)

## AST import-boundary rule

Each production module receives an AST-based test that proves its direct imports match the dependency graph. The test scans source syntax rather than relying on text grep. (§2.2, §10.9)

The egress test additionally scans every production `.py` file and excludes only `term/output.py`. (§10.7)

## Calibration incidents

### Incident #1 — `net/wire.py`

A pasted `pytest -v` result was incomplete: it omitted the beginning and/or end of the run. It was rejected outright because an incomplete paste cannot prove that the full required suite ran. (§10.5, §11, process constraint in `CLAUDE.md`)

Required response: rerun the command and preserve the complete raw output from `collecting ...` through the final summary. (§11, process constraint in `CLAUDE.md`)

### Incident #2 — `net/cookies.py`

A tie-break test was rejected because its name and assertion did not pin the required sequence-before-name rule. A passing test that does not prove the requirement is not evidence. (§9.6, §10.9, process constraint in `CLAUDE.md`)

Required response: rename and strengthen the test so the deterministic ordering rule is explicit in the name and assertion. (§9.6, §10.9)

## Review loop

1. Read the applicable locked decision and architecture section.
2. Implement one module in dependency order.
3. Add required tests and an AST boundary test.
4. Run the full `pytest -v` and explicit `mypy --strict` commands.
5. Attach complete raw output.
6. Stop for architectural review.
7. Record any approved deviation in §12 before changing the implementation. (§11, §12)

## Documentation review

EN and RU documents are mirrors: same sections, same order, same facts, and same citations. Templates supply style only; `ARCHITECTURE.md` supplies facts. (task constraint; process constraint in `CLAUDE.md`)
