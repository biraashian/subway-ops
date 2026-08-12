---
status: draft
source: founder interview 2026-08-11 (B-0006 §9)
blocked_by: B-0002, B-0012
---

# 09 — Money and Reconciliation

**Draft.** Three parameters are open (B-0012) and the cash drop reconciliation
sheet has not been provided (B-0002). The sheet is the real specification for
half this chapter; what follows is the frame it will slot into.

## The shape of a reconciliation

Every money path in this business is the same shape:

```
expected  ←→  recorded  ←→  settled
```

**Expected** is what the POS says should exist. **Recorded** is what a human
says happened — a drop counted, a receipt photographed. **Settled** is what the
bank says arrived, from Monarch (D-020).

A path is *reconciled* when all three agree within tolerance. Any disagreement
is a worklist item, never a silent adjustment. That uniformity is the point: one
matching engine, one exception type, one screen — not seven bespoke
reconciliations.

## Cash

**Tolerance: ≤ $5 clean, ≤ $50 flagged, above escalated** (9.1A) — the existing
`mart_recon_weekly` thresholds, kept.

**Custody** (9.2A): the **store manager** counts the drop and uploads the
receipt. **Office** matches it against the bank. Two people, which is the whole
control — the person who counts the money is not the person who confirms it
arrived.

**Deposit cadence: weekly, on Wednesday** (9.3). This aligns with the business
week closing Tuesday night, so a deposit covers exactly one closed week. It also
means cash sits in the store for up to seven days, which is a risk the owner has
accepted and which makes the drop-level record the only trace of what was in the
safe on any given night.

**Open — B-0012:** how many days a deposit may sit with no bank receipt before
it escalates, and to whom. Without it the worklist has no due date for the one
item most worth chasing.

## Card and third-party

**Providers** (9.8): FreedomPay (card processing) · Amex (settled separately) ·
ezCater (catering) · DoorDash · GrubHub · UberEats.

Six settlement sources, each with its own file format, cadence and fee
structure. Each is its own ingest, and none of them should be assumed to
resemble another.

Expected comes from what the POS already records —
`stg_third_party_daily`, `stg_3p_daily_provider` and the card lines in the
control sheet's `cash_control` section are all ingested today. Settled comes
from the provider statement and from Monarch. The gap between them is fees,
adjustments, and errors, and separating those three is the work.

**Chargebacks** (9.5A): **office disputes**. A chargeback notification opens a
worklist item whose due date is the processor's own deadline — a dispute window
that closes unnoticed is money given away, so the deadline is the due date, not
a reminder.

## Royalty

**12.5%** (9.6).

**Open — B-0012:** the basis and the tolerance. 12.5% is the familiar Subway
figure (8% royalty plus 4.5% advertising) and it is almost certainly of **net
sales** — but "almost certainly" is not a specification, and this reconciliation
runs weekly against fifteen stores forever. Confirm the basis, and state what
size discrepancy is material.

Expected is computed from `stg_controlsheet_weekly.net_sales`; settled is the
actual draw. The control sheet is already ingested, so this is the cheapest
reconciliation in the chapter once the two numbers are pinned.

## Invoices

**Suppliers: Harbor and US Foods. Arriving both paper and digital** (9.7).

Both channels are needed: digital invoices parse directly; paper goes through
the photo-and-extract pipeline (D-021). Same destination table either way, with
the source recorded — a disputed line needs to know whether the number came
from a file or a photograph.

Three-way match: **invoice ↔ delivery ↔ control sheet**. Food cost percentage
says a leak exists; this says where. The two failure modes it catches are price
creep — a case that quietly went from $42 to $47 — and short delivery, billed
for twelve and received ten.

**Open — B-0012:** what price variance is material. Every supplier price moves;
without a threshold this generates an exception per line item per invoice and
becomes noise, which is the same failure as an over-tight schedule exception.

## Monarch is bank truth

Per D-020, deposits and settlements reconcile against Monarch. It has no
official public API, so this is a **scheduled export import**, not a live feed —
`raw_monarch` → `stg_bank_transactions`, following the layer discipline in
[02-DATA-MODEL](../02-DATA-MODEL/README.md).

An import is a snapshot with a date. The matching engine must tolerate a
transaction arriving days after the event it settles, which means matching runs
continuously over an open window rather than once per period.

## Capture

Photo → extraction → **human confirms** → posts (D-021). Never auto-posts. The
source image and the raw model output are both retained, so a number can always
be traced to the pixels it came from.

This is the answer to why the existing spreadsheet is unusable. It holds the
data; it cannot tell anyone what to do about it, and every figure in it was
typed by hand.

## What B-0002 will settle

The cash drop sheet is the operating record for how cash actually moves through
these stores. Reading it should settle: the fields a drop record needs, what the
store manager writes down today and when, how a discrepancy is currently
resolved and by whom, and which parts of the current process are load-bearing
versus accidents of the spreadsheet.

The parts of it that are hardest to use are the parts most worth designing away
— but they have to be seen before they can be replaced, and replacing a control
without understanding why it exists is how controls get lost.
