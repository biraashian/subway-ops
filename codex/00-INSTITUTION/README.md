---
status: authoritative
source: harvested from the pre-Burst CLAUDE.md and SUBWAY_OPS_BUILD_PLAYBOOK.md
---

# 00 — The Institution

## What this system is

The brain of a very good small-shop manager, for a 15-store Subway franchise
across Washington and Oregon. It **reconciles**, it **remembers**, and it
**recognizes** — and everything it learns lands in one place.

That is the design thesis, and it is load-bearing rather than decorative. Every
capability in this system belongs to one of three verbs, and anything that
belongs to none of them is out of scope until the codex says otherwise:

- **Reconcile** — schedule against clock, cash drop against receipt against bank
  deposit, third-party payout against expected, merchant settlement against
  deposit, chargebacks, royalty against control sheet, invoice against delivery.
- **Remember** — certificates, food handler cards, training and orientation
  attestations, receipts, permits, and the expiry date on every one of them.
- **Recognize** — the weekly store task with photo proof and a grade, and the
  store / employee / manager of the week.

Cutting across all three is **the review chain**: office adjusts → the owner
approves → the result goes downstream. It appears in timecards, in disputes, and
in deposits, and its shape is always the same. A system that computes a number
nobody approved has not finished the job.

The output that matters most is not a report. It is **the list of things that
need a human today** — see `ops_worklist_items` in
[02-DATA-MODEL](../02-DATA-MODEL/README.md). Reports are what the previous
system produced, and the reason it was described as tacky.

## What it replaces

- A 6-tab, ~8,100-formula reconciliation workbook.
- Manual logins across LiveIQ, SubVentory, and email reports.
- A cash drop reconciliation sheet that holds the data but cannot say what to do
  about it.
- Eyeball-driven KPI tracking against franchise targets.

## What it is not

- **Not the POS.** LiveIQ / Fresh Connect remains the source of truth for sales,
  labor hours, and inventory. This system reads it; it never writes back.
- **Not payroll.** The custody chain ends at an approved, locked hours report
  that a person keys into payroll (D-022).
- **Not a forecaster.** It reports, reconciles, and flags. Where it predicts, it
  predicts something mechanical and near-term — who crosses 40 hours this week
  given the shifts already scheduled — never demand or revenue.

## The stores

15 stores, all in `America/Los_Angeles`. Store numbers are the natural key
everywhere and are carried as TEXT, never integers.

Fourteen carry ingested history back to 2025-05-14. Store 10393 (Belltown) is
valid reference data but has no ingested history yet.

## Territories

A **territory** is a field manager's cluster of stores. It is the only
intermediate grain between store and portfolio, and it is defined by
`seed/field_managers.csv` — not by geography. Two stores in the same city can
sit in different territories.

| Territory | Stores |
|---|---|
| Sokhavy | 4092, 17967, 26529, 39969 |
| Ekta | 36032, 38699, 51547, 54607, 58806 |
| Lauren | 10393, 24339, 26999 |
| Bir (Operations Manager) | 36248, 38203, 39194 |

Territory membership changes. Anything that reports by territory must resolve
membership **as of the period being reported**, not as of now, or last quarter's
numbers silently rewrite themselves when a store moves.

## The role ladder

| Role | Scope | Accountable for |
|---|---|---|
| `owner` | everything | Approving timecards, targets, and bonus payouts. The final link in every review chain. |
| `field_manager` | their territory | Their stores' targets, their store managers, territory-level attainment. |
| `office` | all stores, money and records | Reconciliation exceptions, disputes, deposit records, timecard adjustment before the owner sees them. |
| `store_manager` | one store | Their store's schedule, cash, tasks, and crew. |
| `crew` | themselves | Their own shifts, training, certificates, and tasks. |

`readonly` exists for a mentor or lender view and sees no personally identifying
employee data.

Two rules follow from this table and are not negotiable at spec level:

1. **A person sees their own data, their scope's data, and nothing above it.**
   A crew member sees their own KPI card; a store manager sees their store's
   crew; a field manager sees their territory. Enforcement is server-side, on
   every query, not in the template.
2. **Approval never skips a link.** Office adjusts before the owner approves.
   The owner cannot approve something office has not reviewed, because the whole
   point of the chain is that two people looked.

## Scope boundaries that keep coming up

- **The employee is the grain that was missing.** The pre-Burst system reported
  on stores. Stores do not do anything; people do. Any new capability should be
  able to answer "whose?" — and if it cannot, say so explicitly rather than
  quietly reporting at store level.
- **Nothing auto-posts money.** Extraction proposes, a human confirms (D-021).
- **Nothing is deleted.** Corrections are new rows with a reason, not edits.
  Records that an inspector or an auditor may ask for must survive the person
  who created them leaving the company.
