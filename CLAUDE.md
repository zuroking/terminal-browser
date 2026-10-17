# CLAUDE.md

Guidance for Claude Code working in this repository.

## Project

`terminal-browser` is a bounded Python 3.12+ text browser. `ARCHITECTURE.md` is the source of truth for scope, module order, limits, behavior, and deviations. Read it before changing code. (§1, §2, §11)

## Non-negotiable implementation rules

- Python 3.12+, `mypy --strict`, Pydantic v2. No stubs: no `pass`, no `TODO`, no unhandled exceptions. (§2.3, §11)
- No high-level wrappers (`requests`/`httpx`/`BeautifulSoup`/`html.parser`/`Rich` in the render path). Stdlib `ssl`, `socket`, and `zlib` only. (§2.3 R7–R8)
- `ARCHITECTURE.md` is the source of truth. Do not implement anything outside it. Any deviation goes into the Deliberate Deviations section of `ARCHITECTURE.md` with a technical rationale. (§2.3, §12)
- Implement one module at a time, in dependency order. Stop after each module. (§11)
- After each module, run `pytest -v` and `mypy --strict` and print the raw terminal output. Never summarize or paraphrase test results. (§11)
- Tests must not touch the real network. Use a local socket server fixture. (§1 G9, §10.3–§10.5)

## Evidence protocol

- Complete output only: preserve the full `pytest -v` run from `collecting ...` through the final `N passed` summary. (§11)
- Preserve the exact `mypy --strict` command and its complete output. (§11)
- Reject summaries, paraphrases, screenshots, selected subsets, and truncated pastes. (§11, process rule in `PROTOCOL.md`)
- Every acceptance claim must identify the command, complete output, and requirement it proves. (§11, `PROTOCOL.md`)

## Test and boundary protocol

- Add the required tests for the module from the §10.9 matrix. (§10.9)
- Add an AST import-boundary test for every production module; the allowed direct-import graph is §2.2. (§2.2, §10.9)
- A test name must state the requirement it proves; generic names are insufficient. (§10.9, `PROTOCOL.md`)
- Use local socket fixtures, scripted transports, fake clocks, and injected output buffers. Never contact public hosts. (§1 G9, §10.3–§10.5)

## Deviation procedure

- Do not implement a deviation before recording it in `ARCHITECTURE.md` §12 with technical rationale and approval status. (§12)
- DD-13 is the DNS-resolution deviation from locked decision #8; its approval status must remain explicit and synchronized. (§12 DD-13)
- No new feature, promise, roadmap item, or limit may be added without an architecture update first. (§1, §2.3, §11)

## Documentation protocol

- EN and RU documentation is a complete mirror: same sections, order, facts, identifiers, limits, citations, and code fences. (task constraint)
- Templates contribute structure and tone only; `ARCHITECTURE.md` contributes facts. (task constraint)
- Do not modify `src/`, `tests/`, or `ARCHITECTURE.md` during a documentation-only task. (task constraint)

## Environment

- Development is on Windows PowerShell 5.1, while code remains cross-platform. (§2.3, process environment)
- Preserve UTF-8 when editing Russian Markdown; do not use PowerShell text pipelines that can mangle Cyrillic. (process rule in `CLAUDE.md`)

## Final checklist

- Architecture remains synchronized. (§2.3, §11)
- Raw full-suite and strict-mypy evidence is attached. (§11)
- No real network was used. (§1 G9, §10.3–§10.5)
- No commits are created until the architectural reviewer accepts the result. (task constraint)
