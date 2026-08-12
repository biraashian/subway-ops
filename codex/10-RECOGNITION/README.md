---
status: authoritative
source: founder interview 2026-08-11 (B-0006 §10)
---

# 10 — Recognition

The third verb. Morale is an operating input, not a soft extra — the same people
who feel recognised are the ones who close correctly and show up on time.

## Task of the week

**The owner sets one task, and it applies to all stores** (10.1). Not per
territory, not auto-assigned from a rotating library. One task, one week, fifteen
stores — which makes the comparison between stores meaningful, because they all
did the same thing.

A task is: a description, a week, and a required photo on completion.

Completion is **a photo uploaded by the store**, stored per
[02-DATA-MODEL](../02-DATA-MODEL/README.md) and captured through the same
pipeline as receipts (D-021), minus the extraction step — a deep-clean photo has
no number to read.

## Grading

**The field manager grades their own territory, 1–5** (10.2).

The FM grades because they know what that store looked like last month. A
central grader comparing photographs across fifteen stores is comparing lighting
and camera angles.

An ungraded task past the week's end raises a worklist item against the field
manager. This is the mechanism that stops recognition quietly dying: the grading
step is the one that gets skipped, so it is the one that is tracked.

## The three weekly awards

| Award | Decided by |
|---|---|
| **Store of the week** | Computed from target attainment (10.3) |
| **Manager of the week** | Computed — their store's attainment |
| **Employee of the week** | Store manager nominates from a KPI-ranked shortlist (10.4C) |

Store and manager of the week are **computed and not overridable**. Attainment
against [04-TARGETS-AND-BUDGETS](../04-TARGETS-AND-BUDGETS/README.md) decides
it. An award the owner can override is an award everyone reads as political.

Employee of the week is **half computed, half human**. The system produces a
shortlist ranked on employee-grain throughput per
[03-MEASUREMENT](../03-MEASUREMENT/README.md); the store manager picks from it.

That split is the whole point of 10.4C. Pure computation cannot see that someone
covered a shift at four hours' notice or trained the new hire. Pure nomination
drifts into favouritism. The shortlist bounds the discretion without removing it.

The nomination records **who nominated and why**. A one-line reason is required,
and it is what gets posted — "picked by the system" is not recognition.

## Rewards: three things at once

**A recognition post, points toward something, and a Subway gift card** (10.5).

This is an architectural fork and it lands on the more expensive side: points
that accumulate toward something require a **ledger with balances**, not a list
of winners.

- `ops_recognition_points` — an append-only ledger. One row per award or
  adjustment, carrying employee, points, reason, source, and timestamp. A
  balance is the sum of the ledger, never a stored mutable integer.
- Redemption is a **negative row** with the gift card reference. The ledger is
  the audit trail for something that converts to money, so it follows the same
  rule as every other money path: append, never update.
- A gift card issued is a payout. It runs the review chain from
  [00-INSTITUTION](../00-INSTITUTION/README.md) — computed, office reviews,
  owner approves — for the same reason bonus payouts do.
- Points survive a store transfer, because they belong to the person
  (see [06-PEOPLE](../06-PEOPLE/README.md)).

Open, and deliberately not assumed: how many points each award carries, and the
points-to-gift-card conversion rate. Those are numbers the owner sets and the
system reads; they belong in configuration rather than this chapter, but they
must exist before redemption ships.

## Where recognition appears

The recognition post goes to the store channel; the personal notification goes
by DM — per [11-COMMS](../11-COMMS/README.md).

**Points balances and gift card values are personal.** They appear on the
employee's own page and in their DM. They do not go in a channel, for the same
reason bonus amounts do not.

Recognition posts name winners and say why. That is the part meant to be public,
and it is the only part.
