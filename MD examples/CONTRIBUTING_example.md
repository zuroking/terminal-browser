# Contributing to {project_name}

## What this project is

{project_name} is an educational, from-scratch implementation built as part of a
personal portfolio. Its primary purpose is to demonstrate architecture, decision-making,
and implementation quality for learning and hiring purposes — not to become a
general-purpose, community-maintained library.

This shapes how contributions are handled. Please read this before opening an issue or PR.

## Before you open anything

Start with `ARCHITECTURE.md`, specifically the **Deliberate Deviations** section. Most
"missing" features (additional SQL clauses, transaction support, concurrency, etc.,
depending on the project) are not oversights — they are documented, deliberate scope
boundaries with stated reasoning. If your issue is "why doesn't this support X",
check there first.

## What's welcome

- **Bug reports.** If behavior contradicts what `ARCHITECTURE.md` or `README.md`
  claims — that's a real bug, not a scope boundary. Please include a minimal
  reproduction and the specific section of the docs that the behavior violates.
- **Documentation corrections.** Typos, unclear explanations, broken links,
  inconsistencies between the English and Russian versions.
- **Test coverage gaps.** If you find an untested edge case that the architecture
  claims to handle, a report (or a PR adding the test) is valuable.

## What's generally out of scope

- **New features that expand the project's scope.** This is a portfolio piece with
  intentionally fixed boundaries (see `ARCHITECTURE.md` §14 or equivalent). Feature
  requests that would require re-opening closed architectural decisions are unlikely
  to be accepted, even if well-implemented — the point of the project is the specific,
  bounded thing it already does.
- **Style-only refactors** without a functional or clarity justification.
- **Dependency additions.** Most projects in this portfolio are deliberately
  zero-dependency or minimal-dependency as an educational constraint.

## If you want to submit a PR anyway

1. Open an issue first describing what you want to change and why. This avoids
   wasted effort on both sides if the change conflicts with a documented
   architectural decision.
2. Keep the change scoped to one concern. Mixed refactor+feature+fix PRs are
   hard to review and harder to justify against the existing test suite.
3. Include real, passing test output (`pytest -v` or the project's equivalent) —
   not just a claim that tests pass.
4. If the change touches an architectural decision, explain why the original
   reasoning in `ARCHITECTURE.md` no longer holds, not just that you prefer a
   different approach.

## Code style

Follow the conventions already present in the codebase (typing strictness, docstring
style, module structure). Consistency with the existing code matters more than
personal preference.

## Questions

For anything not covered here, open an issue with the `question` label rather than
guessing.
