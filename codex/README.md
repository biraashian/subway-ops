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
| 03 | [MEASUREMENT](03-MEASUREMENT/README.md) — what a KPI means at each grain | authoritative | interview |
| 04 | [TARGETS-AND-BUDGETS](04-TARGETS-AND-BUDGETS/README.md) — what a target is and who sets it | authoritative | interview |
| 05 | [COMPENSATION](05-COMPENSATION/README.md) — bonus plan anatomy | draft (B-0009) | interview |
| 06 | [PEOPLE](06-PEOPLE/README.md) — roster lifecycle | authoritative | interview |
| 07 | [SAFETY-HEALTH-AND-RECORDS](07-SAFETY-HEALTH-AND-RECORDS/README.md) — what must be recorded, and for how long | authoritative | interview |
| 08 | [SCHEDULING-AND-HOURS](08-SCHEDULING-AND-HOURS/README.md) — schedules, exceptions, the custody chain | draft (B-0011) | interview |
| 09 | [MONEY-AND-RECONCILIATION](09-MONEY-AND-RECONCILIATION/README.md) — every money path and its tolerance | draft (B-0002, B-0012) | interview |
| 10 | [RECOGNITION](10-RECOGNITION/README.md) — tasks, grading, the weekly awards | authoritative | interview |
| 11 | [COMMS](11-COMMS/README.md) — Discord as the single channel | draft (B-0013) | interview |
| 12 | PROMPTS — the dependency-ordered source queue | not written | derived from 00–11 |
| 13 | BUILD — coding conventions | authoritative | harvested |

Chapters 00–02 and 13 are **harvested**: distilled from the pre-Burst
`CLAUDE.md`, `SUBWAY_OPS_BUILD_PLAYBOOK.md`, and the dated decision log now at
the bottom of `DECISIONS.md`. Those documents are retired to `legacy/` and are
no longer authoritative — if they disagree with a chapter here, the chapter
wins.

Chapters 03–11 come from the founder interview of 2026-08-11 (B-0006). Six are
authoritative. Four are draft, each blocked on a specific unanswered question
rather than on general incompleteness — a chapter is authoritative only when
**every** spec that would anchor to it can be written, and a draft names the one
thing standing in the way. Nothing was filled in by inference (Rule 1).

## Gate

`./verify-codex.sh` from this directory. Four deterministic checks: internal
link integrity, chapter index consistency, unique chapter prefixes, and no
placeholder markers in an authoritative chapter. `scripts/verify.sh` runs it at
pre-merge and post-merge, and **fails** if this directory exists without the
gate — the upstream kit skipped silently there, which its own errata calls a
vacuous-pass hole.
