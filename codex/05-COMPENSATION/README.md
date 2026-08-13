---
status: draft
source: founder interview 2026-08-11 (B-0006 §5)
blocked_by: B-0023
---

# 05 — Compensation

**Draft.** The *structure* is now fully settled — B-0009 resolved the crew
scorecard on 2026-08-13. What remains open is arithmetic: the scorecard's
weights and the payout cap are numbers nobody has set (**B-0023**). A bonus
spec cannot be written against "weighted" without the weights, so the chapter
stays draft on those two numbers alone.

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

### Crew — team-based weighted scorecard (5.2B, resolved by B-0009 → B)

A crew member's scorecard combines **their store's result** with **their own
throughput and training**:

| Component | Grain | Source |
|---|---|---|
| Store sales attainment | store | [04-TARGETS](../04-TARGETS-AND-BUDGETS/README.md) |
| Store food cost attainment | store | 04 |
| Store labor attainment | store | 04 |
| Own throughput | employee | [03-MEASUREMENT](../03-MEASUREMENT/README.md) §3.1 |
| Own training compliance | employee | [07-RECORDS](../07-SAFETY-HEALTH-AND-RECORDS/README.md) |

This is what resolves the contradiction between answers 5.2 and 3.1. The
interview named sales, food and labor as bonus components; 3.1 says those are
invalid *at employee grain* because an employee controls none of them. Both
stand, because the store metrics stay at **store** grain — the crew member
**shares in** the store's result rather than being **measured on** it. Only
throughput and training are attributed to the individual, and those are exactly
the two things 03 permits there.

The practical consequence is worth stating: a crew member's bonus moves when
their store's food cost moves, even in a week they worked one shift. That is
intended — it is a team incentive — but it must be explained that way when the
plan is communicated, or it reads as arbitrary.

**Still open (B-0023):** the weights across those five components, and the
payout cap. Both are numbers only the owner can set.

## Scale

**Sliding from a 90% floor** (5.3). Below 90% of target, nothing. From 90%
upward, linear to a cap.

The floor exists so near-misses are not paid as hits; the slide exists so that
99% is not treated the same as 60%. The cap prevents a single freak period from
paying out unboundedly — **its value is not yet set (B-0023)**.

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
