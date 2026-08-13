# Workshop — Subway Ops Build Board

Updated only by the skills, never by hand.
Runway floor: 3 · WIP limit (built, awaiting audit): 3

## Needs you
| What | Ref | Since |
|---|---|---|
| Push `main` to origin — blocked by the sandbox permission classifier, not by git | Part 0 | 2026-08-11 |
| Upload the cash drop reconciliation sheet — it is the domain source for `codex/09-MONEY-AND-RECONCILIATION/` | B-0002 | 2026-08-11 |
| **B-0011** — the timecard exception taxonomy. Gates all of Phase C | B-0011 | 2026-08-11 |
| **B-0012** — deposit ageing, royalty basis, invoice variance. Gates 3 reconcilers | B-0012 | 2026-08-11 |
| **B-0013** — real-time vs cadence routing. Gates SPEC-COM | B-0013 | 2026-08-11 |
| **B-0023** — crew scorecard weights and the payout cap. Gates SPEC-BON | B-0023 | 2026-08-13 |
| **T-0011 is founder-paired** — infrastructure type, not built autonomously | D-025 | 2026-08-13 |
| Upload the cash drop reconciliation sheet — the operating record for half of codex 09 | B-0002 | 2026-08-11 |

## Provisioning horizon (external, long-lead)
| Item | Feeds | Status |
|---|---|---|
| Discord server + roles mirroring territory→store | SPEC-COM-* | not started |
| Supabase Storage buckets (certificates, receipts, task-photos, invoices) | SPEC-CAP-001 | not started |
| Anthropic API key for receipt extraction | SPEC-CAP-001 | not started |
| Monarch export cadence + format sample | SPEC-RCN-001 | not started |
| Fly.io app for the new web surface | SPEC-APP-001 | not started |
| `stg_timeclock` → TIMESTAMPTZ (B-0019) — must land before SPEC-SCH-003 | Phase C | decided, unminted (no anchor yet) |

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
| T-0001 | Codex chapters 00–02, 13, and the codex gate | codex/ (harvest) | merged | `main` |
| T-0002 | Codex chapters 03–11 | B-0006 (interview) | merged | `main` |
| T-0003 | ops_worklist_items + worklist helper | SPEC-PPL-001 AC-018, AC-020 | queued — code done; needs its drift declaration + gate re-run | `forge/T-0003` |
| T-0004 | People schema — persons, assignments, wages, identity log | AC-011, AC-014, AC-022, AC-031 | queued (needs T-0003) | — |
| T-0005 `[P]` | Pure helpers — names, roles | AC-026, AC-027, AC-029, AC-030 | queued | — |
| T-0006 | Roster derivation and person resolution | AC-001…AC-006, AC-024, AC-028 | queued (needs T-0003/4/5) | — |
| T-0007 | Wages, permission guard, weekly cost with overtime | AC-011…AC-017 | queued (needs T-0004/5) | — |
| T-0008 | Identity repair — merge, split, wage-overlap refusal | AC-007…AC-010, AC-023, AC-025 | queued (needs T-0006/7) | — |
| T-0009 | Completeness sweep, CLI, daily_pull wiring | AC-018…AC-021 | queued (needs T-0003/6/7) | — |
| T-0010 | Schema drift becomes declared, not merely detected | D-024 | **built, awaiting audit** | `forge/T-0010` |
| T-0011 | DB tests on containerised Postgres | D-025 | queued (founder-paired) | — |
| T-0012 | Format the repo once, re-enable the gate line | D-027 | queued (run when nothing else is in flight) | — |

## Backlog (written by /stubs)
(run /stubs once `codex/12-PROMPTS/` exists)

Statuses: queued → in progress → halted(B-####) → built, awaiting audit
→ audit failed(B-####) → awaiting your review → in merge queue → merged
