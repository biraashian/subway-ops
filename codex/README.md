# The Codex — design authority for Subway Ops

Read-only to builds. This is the top of the read-upward chain:

```
codex/ > specs/SPEC-*.md > design/PLAN-*.md > tasks/T-*.md > code
```

A spec may not license behavior the codex does not describe. Where a spec needs
something the codex is silent on, that is a **gap**: bench it (Rule 1), decide
it, write it here, then spec it. Code never becomes the authority by being
written first.

## Status convention

Every chapter carries frontmatter:

```
status: authoritative | draft
```

`authoritative` means specs may anchor to it. `draft` means it is being written
and nothing may anchor to it yet — the codex gate rejects placeholder markers in
an authoritative chapter, so a chapter cannot be quietly promoted while it still
has holes.

## Chapters

| # | Chapter | Status | Source |
|---|---|---|---|
| 00 | [INSTITUTION](00-INSTITUTION/README.md) — what this business is and who owns what | authoritative | harvested |
| 01 | [CALENDAR](01-CALENDAR/README.md) — business day and week | authoritative | harvested |
| 02 | [DATA-MODEL](02-DATA-MODEL/README.md) — table shapes, money, time, idempotency | authoritative | harvested |
| 03 | MEASUREMENT — what a KPI means at each grain | not written | founder interview |
| 04 | TARGETS-AND-BUDGETS — what a target is and who sets it | not written | founder interview |
| 05 | COMPENSATION — bonus plan anatomy | not written | founder interview |
| 06 | PEOPLE — roster lifecycle | not written | founder interview |
| 07 | SAFETY-HEALTH-AND-RECORDS — what must be recorded, and for how long | not written | founder interview |
| 08 | SCHEDULING-AND-HOURS — schedules, exceptions, the custody chain | not written | founder interview |
| 09 | MONEY-AND-RECONCILIATION — every money path and its tolerance | not written | founder interview + B-0002 |
| 10 | RECOGNITION — tasks, grading, the weekly awards | not written | founder interview |
| 11 | COMMS — Discord as the single channel | not written | founder interview |
| 12 | PROMPTS — the dependency-ordered source queue | not written | derived from 00–11 |
| 13 | BUILD — coding conventions | authoritative | harvested |

Chapters 00–02 and 13 are **harvested**: distilled from the pre-Burst
`CLAUDE.md`, `SUBWAY_OPS_BUILD_PLAYBOOK.md`, and the dated decision log now at
the bottom of `DECISIONS.md`. Those documents are retired to `legacy/` and are
no longer authoritative — if they disagree with a chapter here, the chapter
wins.

Chapters 03–11 do not exist yet, and that is the honest state: the domain they
describe has never been written down anywhere. It lives in the founder's head.
D-017 blocks new specs until they are authored.

## Gate

`./verify-codex.sh` from this directory. Four deterministic checks: internal
link integrity, chapter index consistency, unique chapter prefixes, and no
placeholder markers in an authoritative chapter. `scripts/verify.sh` runs it at
pre-merge and post-merge, and **fails** if this directory exists without the
gate — the upstream kit skipped silently there, which its own errata calls a
vacuous-pass hole.
