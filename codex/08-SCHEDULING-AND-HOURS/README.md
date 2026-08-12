---
status: draft
source: founder interview 2026-08-11 (B-0006 §8)
blocked_by: B-0011
---

# 08 — Scheduling and Hours

**Draft.** Question 8.3 — what counts as an exception needing office review —
was not answered, and it is the centre of the chapter. The custody chain below
cannot be specced without knowing what enters it. No spec anchors here until
B-0011 resolves.

Everything else in this chapter is settled and recorded.

## Who builds the schedule

**The store manager, within the labor budget** (8.1). Not the field manager, not
a central planner. The person who knows who is reliable on a Friday night builds
the Friday night.

The budget they work within is the store's labor-hours and labor-dollars target
from [04-TARGETS-AND-BUDGETS](../04-TARGETS-AND-BUDGETS/README.md) — the same
rows the dashboards read, so a schedule can never be checked against a different
number than the one the store is judged on.

## Publication

**Published Saturday, for the business week starting the following Wednesday**
(8.2, modified).

That is four days of notice. It also means the schedule is built before the
current week has closed, so the manager is planning against a week whose
attainment is not yet final — worth knowing when designing the guard, because
the budget check is against target, not against how the current week is going.

**After publication, changes need manager approval and are logged.** A published
schedule is a commitment to the people on it. Every post-publication change
carries who changed it, when, and what it was before.

## The budget guard

The schedule is checked against the labor budget **before the week runs** —
scheduled hours summed, multiplied by each person's wage from
[06-PEOPLE](../06-PEOPLE/README.md), compared to the labor-dollar target.

This is the highest-value mechanic in the chapter. A dashboard reports that last
week went over. A guard at publication says Saturday is over budget while it is
still Saturday-next-week and a shift can be moved.

An employee with no wage on file cannot be costed. Per 06 they are excluded from
labor dollars and the guard reports the schedule as **partially costed** rather
than passing it — a guard that silently ignores the uncosted is worse than no
guard.

## Overtime

**40 hours per week; warn only when exceeded** (8.6B).

Recording the consequence plainly, because it reverses something proposed
earlier and someone will otherwise reopen it: this is **detection, not
prediction**. The system reports overtime that has already happened. It does not
warn mid-week that a person is on track to cross 40.

That was offered as option A and not taken. The cost is that overtime is a
reporting line rather than a preventable event; the benefit is that no one gets
a stream of speculative warnings about hours they may never work. If the
trade-off ever feels wrong, this is a one-line reopen — the scheduled hours and
the worked hours are both already in the system, so prediction is arithmetic
that is simply not switched on.

Hours sum **across store assignments**, per 06. Someone at 25 hours in two
stores is at 50 hours and in overtime, and no single store's view would show it.

## Breaks

**Tracked, and violations flagged** (8.4A). Washington requires a 30-minute meal
period for shifts over five hours and a paid 10-minute rest per four hours;
Oregon is similar but not identical, and the difference matters for the Hermiston
store.

This is compliance exposure, not a nicety, which is why it is tracked rather
than left to the POS. The per-state rule detail belongs in the spec, sourced
from the actual statutes rather than from this paragraph.

## Shift swaps

**Allowed, with store manager approval, and logged** (8.5A). A swap rewrites the
schedule, so it follows the same post-publication discipline: who, when, and
what it replaced.

## The custody chain

The settled shape, from D-022 and [00-INSTITUTION](../00-INSTITUTION/README.md):

```
schedule (planned)  ─┐
                     ├─► exceptions ─► office adjusts ─► owner approves ─► locked report ─► keyed into payroll
actual clock (real) ─┘        ▲
                              └── B-0011: what enters here is undecided
```

Properties that hold regardless of how B-0011 resolves:

- **The clock is evidence, not truth.** Someone stays late through a rush; the
  clock records it and that is correct. Whether it is *payable as recorded* is a
  human decision, which is why the chain exists.
- **Adjustments are new rows,** carrying who adjusted, the original value, the
  new value, and a reason. The raw clock record is never edited.
- **Approval locks.** After the owner approves, the period is immutable. A later
  correction is a new adjustment against a new approval, never a rewrite of an
  approved one.
- **The output is a report, not an integration** (D-022). Office keys it into
  payroll.
- **Approval never skips a link.** The owner cannot approve hours office has not
  reviewed.

## What B-0011 needs to settle

The exception taxonomy and its thresholds. The candidate set offered in the
interview, none of it adopted:

- clocked in more than *N* minutes before scheduled start
- clocked out more than *N* minutes after scheduled end
- no-show against a scheduled shift
- worked a shift that was not scheduled
- missed or short meal break
- shift over-running store close

Each needs a threshold and a decision about whether it merely flags or blocks
approval. Getting this wrong in either direction has a real cost: too tight and
office reviews three hundred items a week and stops looking at any of them; too
loose and the review chain is ceremony over a rubber stamp.
