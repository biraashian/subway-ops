# Workshop — Subway Ops Build Board

Updated only by the skills, never by hand.
Runway floor: 3 · WIP limit (built, awaiting audit): 3

## Needs you
| What | Ref | Since |
|---|---|---|
| **Decide B-0022** — the schema-drift gate blocks every migration task. T-0003 is built and green except for this; T-0004 cannot start either | B-0022 | 2026-08-13 |
| Push `main` to origin — blocked by the sandbox permission classifier, not by git | Part 0 | 2026-08-11 |
| Upload the cash drop reconciliation sheet — it is the domain source for `codex/09-MONEY-AND-RECONCILIATION/` | B-0002 | 2026-08-11 |
| Name the third-party delivery platforms, card merchant/processor, and payroll provider | B-0003 | 2026-08-11 |
| **Drain 7 bench items from the interview residue** — B-0009 (a contradiction) gates SPEC-BON; B-0011 gates all of Phase C; B-0012 gates 3 reconcilers; B-0013 gates comms | B-0007…B-0013 | 2026-08-11 |
| Upload the cash drop reconciliation sheet — the operating record for half of codex 09 | B-0002 | 2026-08-11 |

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
| SPEC-PPL-001 | Employee roster + wages | **tasked** — 7 queued | 2 (B-0020, B-0021 — both fenced) | T-0003…T-0009 |
| SPEC-TGT-001 | Targets and budgets | codex 04 authoritative — ready to spec | 1 (B-0007, additive) | Phase A |
| SPEC-KPI-* | The four grains | codex 03 authoritative — ready to spec | 1 (B-0008, scope) | Phase E |

## Merge queue — strict serial: pre-merge → approval → /close
(empty)

## Tasks
| Task | Title | Anchors | Status | Where |
|---|---|---|---|---|
| T-0000 | Install the Burst harness | — (bootstrap: installs the anchoring machinery) | merged | `main` |
| T-0001 | Codex chapters 00–02, 13, and the codex gate | codex/ (harvest) | built, awaiting audit | `burst/part-2-codex` |
| T-0002 | Codex chapters 03–11 | B-0006 (interview) | built, awaiting audit | `burst/part-2-codex-interview` |

## Backlog (written by /stubs)
(run /stubs once `codex/12-PROMPTS/` exists)

Statuses: queued → in progress → halted(B-####) → built, awaiting audit
→ audit failed(B-####) → awaiting your review → in merge queue → merged
