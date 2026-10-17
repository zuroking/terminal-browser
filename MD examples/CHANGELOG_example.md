# Changelog

All notable changes to {project_name} are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/), adapted for a
portfolio project with a fixed, protocol-driven development cycle rather than
continuous release cadence: each version corresponds to a completed pass through the
project's development protocol (`ARCHITECTURE.md` → grill-me → implementation →
code-review → tests → docs), not a calendar-based release.

Versioning here is descriptive, not semantic in the strict sense — this is a
completed educational artifact, not a library with a stable public API to protect.

## [Unreleased]

Changes staged but not yet part of a closed protocol cycle.

### Added
-

### Changed
-

### Fixed
-

## [1.0.0] — {YYYY-MM-DD}

Initial closed version, published after completing the full development protocol.

### Added
- Core functionality: {one-line summary of what the project does}.
- Full test suite ({N} tests passing, `pytest -v` output archived in the closing
  code-review round).
- `ARCHITECTURE.md` with all scope decisions and the Deliberate Deviations section.
- Bilingual documentation (`README.md` / `README_ru.md`, `ELI5.md` / `ELI5_ru.md`).

### Fixed
- {Any critical bugs found during the code-review pass and corrected before
  publication — list them here, even though they never reached a public release.
  This is not embarrassing; catching them here is the protocol working as intended.}

### Known limitations
- See `ARCHITECTURE.md`, Deliberate Deviations, for the full list of intentionally
  out-of-scope behavior. Do not duplicate that list here — link to it instead.

---

## How entries are added

An entry is added to `[Unreleased]` the moment a change is made to committed code —
not batched at the end. When a protocol cycle closes (architecture re-locked, tests
re-run, docs re-synced), `[Unreleased]` is renamed to the new version number and dated,
and a fresh empty `[Unreleased]` section is added above it.

Categories used: `Added`, `Changed`, `Fixed`, `Removed`, `Deprecated`. Omit empty
categories rather than leaving them as empty headers with no content.

Entries describe observable behavior, not implementation detail: "Fixed: mirrored
comparisons on the primary key produced an inverted range" is a changelog entry.
"Refactored `_extract_range` to use a lookup table" is a commit message, not a
changelog entry, unless the refactor itself changed observable behavior.
