---
status: authoritative
source: founder interview 2026-08-11 (B-0006 §3)
---

# 03 — Measurement

What a number means at each grain, and — more importantly — which numbers are
**invalid** at which grain. A metric computed at a grain where it has no meaning
is worse than a missing metric, because it looks like information.

## The four grains

| Grain | Key | Floor period |
|---|---|---|
| Employee | person (see [06-PEOPLE](../06-PEOPLE/README.md)) | **week** |
| Manager | store manager, via their store | week |
| Store | `store_number` | **day** |
| Territory | field manager's cluster | week |

**The week is the floor for people; the day is the floor for stores** (3.4).
Per-shift employee reporting is out of scope: it multiplies row count and the
numbers get noisy enough that a slow Tuesday close reads as a performance
signal when it is a weather signal. Store-level daily stands because a store's
day is a large enough sample to mean something.

## Employee grain: throughput only

An employee card carries **throughput metrics and nothing else** (3.1):

- units per labor hour
- transactions per hour
- average ticket

That is the whole list. It is short on purpose.

**What is explicitly invalid at employee grain:**

- **Food cost.** An employee does not control purchasing, delivery, waste, or
  portioning across a week. Attributing food cost to a person is arithmetic
  without meaning.
- **Labor cost percentage.** They do not control their own scheduling.
- **Sales totals.** Whoever works the Saturday lunch rush rings more. Volume
  measures the shift, not the person; that is why the three metrics above are
  all rates or averages.
- **Void, refund and discount rates.** Excluded from the employee card by 3.1.
  See the note below — this one has an open question attached.

### Loss-prevention is not an employee KPI

`TransactionDetails` carries `clerk_id`, so void / refund / discount rates per
person are computable, and they are a standard loss-prevention signal. 3.1 keeps
them **off the employee card**.

That decision is respected here and the consequence is stated plainly: an
employee's own page, and their manager's view of them, show throughput only.

**B-0008 decided (2026-08-13): the same numbers DO exist as an
office-and-owner-only loss-prevention view.** Never surfaced to the employee,
never shown to their store manager, never an input to recognition or bonus.

The distinction is the point: what an employee is *judged* on and what the
owner can *see* are different questions. Void and refund rates are a
loss-prevention signal for the business, not a performance measure for a
person — a high void rate is a reason to look, not a reason to score someone
lower. Putting it on the employee card would make it a performance metric by
placement alone, whatever the intent.

## Store grain

Everything the warehouse already computes: net sales, transactions, average
ticket, food cost actual vs expected, labor hours, labor dollars, sales per
labor hour, cash over/short.

## Territory grain: sales-weighted

Store metrics roll up to territory as a **sales-weighted average** (3.2), which
is what `mart_field_manager_portfolio` already does. A $20k store moves the
territory number more than a $5k one, because it moves the business more.

The known cost of this choice, recorded so nobody rediscovers it as a bug: a
field manager running one large store and three small ones is judged mostly on
the large one. A simple average would be kinder to the small-store manager and
less true about the money. The weighting is the decision.

**Territory membership is resolved as of the period being reported**, never as
of now — see [00-INSTITUTION](../00-INSTITUTION/README.md). A store moving
between managers must not rewrite last quarter.

## The default comparison

Every number is shown against **its target for that store and that week** (3.3).
Not last year, not the trailing average, not a peer store.

This makes [04-TARGETS-AND-BUDGETS](../04-TARGETS-AND-BUDGETS/README.md) load-
bearing for the entire measurement layer: a store with no target row for a week
has no baseline, and the honest display is "no target set", never a silent
fallback to a portfolio constant. The hardcoded `TARGET_FOOD_COST_STORE = 0.22`
that every store was measured against is precisely the failure this rule ends.

Other comparisons — last year, trailing four weeks, territory peers — may be
offered as secondary context on a detail view. They are never the primary
framing.

## Aggregation rules

- **Rates never average.** Units per labor hour for a territory is total units
  over total labor hours, not the mean of each store's rate. Averaging rates
  weights a slow store equally with a busy one and produces a number that
  matches nothing.
- **Percentages are stored as fractions** — see
  [02-DATA-MODEL](../02-DATA-MODEL/README.md).
- **A missing input is missing, not zero.** A week with no control sheet has no
  food cost; it does not have 0% food cost. Marts carry NULL and surfaces render
  "—".
