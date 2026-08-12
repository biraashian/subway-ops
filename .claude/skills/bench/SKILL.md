---
name: bench
description: Drain all OPEN bench items in one founder sitting - compressed multiple-choice with marked recommendations - then apply decisions back into specs, tasks, the board, and DECISIONS.md. Invoke as /bench.
disable-model-invocation: true
---

# /bench — One sitting, all decisions (v0.2)

1. Read `bench/BENCH.md`. Nothing OPEN → say so in one line, stop.
2. Present ALL open items in one message: ID, one-line question, lettered
   options with one-line trade-offs, era-1 label where harvested, marked
   recommendation. Order by how many tasks each unblocks (state the count).
   Accept compressed answers ("B-0007 A, B-0008 B, B-0009: 500ms").
3. Per decision: fold into the governing spec (REQ/AC updated, §10 recorded,
   version bumped) · mark the item `DECIDED: <answer> (<date>)` · append a
   D-entry to `DECISIONS.md` when the decision is policy-shaped rather than
   spec-local · flip blocked tasks back to `queued` · chronicle line.
4. Close with the unblock report: what's now buildable, in what order.

Rule: recommendations are marked as recommendations; the founder's answer is
the decision even when it differs. Decided items are never re-argued — "reopen
if" conditions live in the record, not in pushback.
