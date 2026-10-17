# Architecture Decision Records — {project_name}

This file is a granular, chronological log of individual architectural decisions,
in standard ADR (Architecture Decision Record) format. It complements
`ARCHITECTURE.md` rather than replacing it:

- **`ARCHITECTURE.md`** describes the *current, locked* state of the architecture —
  what the system does and why, organized by subsystem.
- **`DECISIONS.md`** describes *how the architecture got there* — each individual
  decision point, in the order it was made, including decisions that were later
  revisited or reversed.

If a decision recorded here was later changed, the original entry is not deleted or
rewritten — a new entry is added referencing and superseding it. The history of
changing your mind on a documented basis is itself useful information, both for
future maintainers and for anyone evaluating the project's engineering process.

---

## ADR format

Each entry follows this structure:

```
## ADR-{NNN}: {short title}

**Status:** Proposed / Accepted / Superseded by ADR-{NNN}
**Date:** {YYYY-MM-DD}

### Context
What problem or question prompted this decision. What constraints were in play.

### Decision
The specific choice made, stated plainly — not the alternatives, the actual choice.

### Alternatives considered
What else was on the table, and in one line each, why it wasn't chosen.

### Consequences
What this decision makes easier, what it makes harder or forecloses, and what it
depends on remaining true. Include both positive and negative consequences — an
ADR that only lists upsides is incomplete.
```

---

## ADR-001: {example title, e.g. "Storage layer: clustered index vs. heap + secondary index"}

**Status:** Accepted
**Date:** {YYYY-MM-DD}

### Context
{What prompted the decision — e.g. the project needs on-disk persistence for table
data, and there are two standard architectural patterns to choose between.}

### Decision
{The specific choice, stated as a fact: "The table is stored as a clustered B+-tree
keyed on rowid; there is no separate heap file."}

### Alternatives considered
- {Alternative A} — not chosen because {one-line reason}.
- {Alternative B} — not chosen because {one-line reason}.

### Consequences
- {Positive consequence — what this simplifies.}
- {Negative consequence / what this forecloses — e.g. "secondary indexes are not
  possible without revisiting this decision."}
- {Dependency — what other, later decisions assume this one holds.}

---

## ADR-002: {next decision title}

**Status:** Accepted
**Date:** {YYYY-MM-DD}

### Context


### Decision


### Alternatives considered


### Consequences


---

## Superseding an entry

When a later decision changes an earlier one, do not edit the earlier entry's
Decision or Consequences sections. Instead:

1. Change the earlier entry's **Status** to `Superseded by ADR-{NNN}`.
2. Add the new entry as usual, with its Context section explicitly stating what
   earlier ADR it revisits and what new information or constraint changed.

This keeps the log honest — it shows the actual sequence of reasoning, including
the parts that turned out to be wrong the first time.
