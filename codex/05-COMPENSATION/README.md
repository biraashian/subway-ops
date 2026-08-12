---
status: draft
source: founder interview 2026-08-11 (B-0006 §5)
blocked_by: B-0009
---

# 05 — Compensation

**Draft.** The manager structure is settled; the crew scorecard is not, because
answer 5.2 and answer 3.1 disagree with each other. See the conflict below. No
spec may anchor to this chapter until B-0009 resolves.

## Eligibility

**Everyone, including crew** (5.1). Three populations, two structures.

## Structure

### Managers — gate plus multiplier (5.2C)

A store or field manager must **pass a labor-cost gate** before earning anything
on their other metrics. Miss the gate, earn zero, regardless of sales.

The gate is deliberate and worth stating plainly: labor is the cost a manager
most directly controls week to week, and a sales bonus without a labor gate pays
for revenue bought with overtime.

The gate threshold is the store's labor target for the period, per
[04-TARGETS-AND-BUDGETS](../04-TARGETS-AND-BUDGETS/README.md).

### Crew — weighted scorecard (5.2B) — **components open**

A weighted scorecard across several metrics rather than a single number.

**Which metrics is unresolved (B-0009).** The interview's option text listed
"sales / food / labor / training", but
[03-MEASUREMENT](../03-MEASUREMENT/README.md) §3.1 says food cost, labor cost
and sales totals are *invalid at employee grain* — an employee controls none of
them. Both answers came from the same sitting and they cannot both stand.

The three ways out, none of them assumed:

- **A)** Crew scorecard uses only what 03 permits at employee grain — throughput
  (units/labor hour, transactions/hour, average ticket) plus training
  compliance. Internally consistent; narrow.
- **B)** Crew scorecard is **team-based**: their store's sales / food / labor
  attainment, plus their own throughput and training. Common in restaurants, and
  consistent with 03 because the store metrics stay at store grain — the crew
  member shares in the store's result rather than being measured on it
  individually.
- **C)** Revise 3.1 to admit these metrics at employee grain. Not recommended;
  3.1's reasoning holds.

Burst recommends **B**. It is the only option that pays crew on the things the
interview named without attributing store economics to individuals.

## Scale

**Sliding from a 90% floor** (5.3). Below 90% of target, nothing. From 90%
upward, linear to a cap.

The floor exists so near-misses are not paid as hits; the slide exists so that
99% is not treated the same as 60%. The cap prevents a single freak week from
paying out unboundedly — its value is not yet set and belongs with B-0009.

## Period

**Quarterly payout, monthly standings** (5.4).

The standings are the point. A bonus you learn about after the period closes
changes no behaviour, so attainment is published monthly to the person and their
manager — mid-period, while the quarter can still be influenced. Payout happens
once, at quarter end.

Standings are pushed per [11-COMMS](../11-COMMS/README.md), which constrains
what can be said in a channel: **individual bonus amounts never go to Discord**.
Standings are attainment percentages and rank, not dollars.

## Leavers forfeit

**An employee who leaves mid-period keeps nothing** (5.5). No pro-rating. The
bonus is earned at period close and being employed at close is part of earning
it.

The record still stands: their attainment for the weeks they worked stays in
`mart_bonus_attainment` with the payout marked forfeited. It is not deleted, and
the reason is legible. Per [06-PEOPLE](../06-PEOPLE/README.md) nothing is erased
on termination.

## Attainment is computed, payout is approved

Attainment is arithmetic against targets. The **payout is not automatic** — it
runs the review chain from [00-INSTITUTION](../00-INSTITUTION/README.md): the
system computes, office reviews, the owner approves. Money leaving the business
on a computed number nobody looked at is exactly the failure mode this system
exists to prevent.
