# Workshop — Subway Ops Build Board

Updated only by the skills, never by hand.
Runway floor: 3 · WIP limit (built, awaiting audit): 3

## Needs you
| What | Ref | Since |
|---|---|---|
| Push `main` to origin — blocked by the sandbox permission classifier, not by git | Part 0 | 2026-08-11 |
| Upload the cash drop reconciliation sheet — it is the domain source for `codex/09-MONEY-AND-RECONCILIATION/` | B-0002 | 2026-08-11 |
| Name the third-party delivery platforms, card merchant/processor, and payroll provider | B-0003 | 2026-08-11 |
| **Answer the codex interview** — 40 questions at `bench/INTERVIEW-codex-03-11.md`. Gates every spec in Phases A–E | B-0006 | 2026-08-11 |

## Provisioning horizon (external, long-lead)
| Item | Feeds | Status |
|---|---|---|
| Discord server + roles mirroring territory→store | SPEC-COM-* | not started |
| Supabase Storage buckets (certificates, receipts, task-photos, invoices) | SPEC-CAP-001 | not started |
| Anthropic API key for receipt extraction | SPEC-CAP-001 | not started |
| Monarch export cadence + format sample | SPEC-RCN-001 | not started |
| Fly.io app for the new web surface | SPEC-APP-001 | not started |

## Runway — spec pipeline (floor: 3 tasks spec-scoped ahead)
| Spec | Component | Status | Open Qs | Tasks ready |
|---|---|---|---|---|
| — | blocked on the codex (D-017); chapters 00–02 and 13 are authoritative, 03–11 await B-0006 | — | 1 (B-0006) | — |

## Merge queue — strict serial: pre-merge → approval → /close
(empty)

## Tasks
| Task | Title | Anchors | Status | Where |
|---|---|---|---|---|
| T-0000 | Install the Burst harness | — (bootstrap: installs the anchoring machinery) | merged | `main` |
| T-0001 | Codex chapters 00–02, 13, and the codex gate | codex/ (harvest) | built, awaiting audit | `burst/part-2-codex` |
| T-0002 | Codex chapters 03–11 | codex/ (interview) | blocked on B-0006 | — |

## Backlog (written by /stubs)
(run /stubs once `codex/12-PROMPTS/` exists)

Statuses: queued → in progress → halted(B-####) → built, awaiting audit
→ audit failed(B-####) → awaiting your review → in merge queue → merged
