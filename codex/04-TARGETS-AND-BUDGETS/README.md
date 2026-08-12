---
status: authoritative
source: founder interview 2026-08-11 (B-0006 §4)
---

# 04 — Targets and Budgets

A target is the number a store is held to for a week. Per
[03-MEASUREMENT](../03-MEASUREMENT/README.md) it is the default comparison for
everything, which makes this chapter load-bearing for every surface in the
system.

## Who sets them

**The owner sets every target** (4.1). Field managers do not propose and the
system does not compute them from history. This is deliberately not the review
chain used elsewhere — targets are the owner's instrument.

## Cadence

**Set annually, revised quarterly** (4.2). The annual set is the plan; the
quarterly revision is the adjustment. Nothing is set weekly, even though the
grain is weekly — a year's worth of weekly rows is generated from the annual
set and then adjusted in quarterly passes.

## Shape

**Absolute dollars per store per week** (4.3). A real number in `ref_targets`,
not a percentage growth factor computed against last year, and not a portfolio
constant.

This is the direct repudiation of the pre-Burst design, where every store in the
franchise was measured against the same hardcoded `0.22` food cost forever. A
store that opened in September 2025 and a store that has run since 2018 do not
get the same number just because they sell the same sandwiches.

### Metrics carrying a target

Net sales · food cost % · labor hours · labor dollars · transactions · average
ticket.

**This list is assumed, not confirmed.** It was stated as the interview's
default for question 4.5 and not explicitly answered. It is recorded as
**B-0007** and should be confirmed before `ref_targets` ships. The risk is low
and additive — a metric added later is a nullable column and a backfill — but
the list is not a founder decision yet and is not presented as one.

Note that **labor dollars** depends on wages, which do not exist in Fresh
Connect at all. See [06-PEOPLE](../06-PEOPLE/README.md) — `ref_employee_wages`
is a prerequisite for this target being computable rather than decorative.

## Revision: effective-dated, never retroactive

**A target may be revised mid-period, and the revision is effective-dated so
history stays honest** (4.4).

This is the most consequential answer in the chapter, so the mechanics are
pinned here rather than left to a spec:

- `ref_targets` is keyed `(store_number, effective_week_start)`. A revision
  **inserts a new row** with a later `effective_week_start`. It never updates an
  existing one.
- Attainment for a past week always resolves against the row that was in force
  **for that week**, which is the latest row whose `effective_week_start` is on
  or before it.
- Consequently, raising a target in October cannot make September look worse,
  and lowering one in October cannot make September look better. Last quarter's
  attainment is a fact, not a view.
- A revision carries `set_by` and `set_at`. Who changed the goalposts and when
  is part of the record.

Immutable targets (option A) were rejected because reality moves — a store
changes hands, a road closes, a competitor opens. Retroactive revision (option
C) was rejected because it makes every historical attainment number
unfalsifiable, and attainment feeds bonuses.

## No silent fallback

A store-week with no `ref_targets` row in force has **no target**. Surfaces
render "no target set". Nothing falls back to a portfolio default, a sibling
store, or a constant.

The existing `TARGET_FOOD_COST_STORE` / `TARGET_LABOR_COST_PORTFOLIO` constants
are retired to exactly one use: seeding an initial annual set, where the owner
sees and edits them before they are written. They never act as a read-time
default again.

## Budgets are targets

There is no separate budget concept. A labor-hours budget is the labor-hours
target; a food budget is the food cost target. One table, one revision
discipline, one attainment calculation. The scheduling guard in
[08-SCHEDULING-AND-HOURS](../08-SCHEDULING-AND-HOURS/README.md) reads the same
rows the dashboards do, so a schedule cannot be checked against a different
number than the one the store is judged on.
