---
name: next
description: The policy evaluator - computes what should happen next under the four decided policies (topo order, merge queue, WIP lane, runway floor) in 8 lines or fewer. Run at every session open. Invoke as /next.
disable-model-invocation: true
---

# /next — What should happen next, and why (v0.2 · D-006)

Read `workshop/WORKSHOP.md` (+ `bench/BENCH.md` for blockers). Evaluate in this
strict order and report the FIRST binding condition — ≤8 lines, no fluff:

1. **Queue frozen** — integration red or a revert pending → "Frozen on <ref>;
   resolve via /close's revert path / bench B-#### first."
2. **WIP lane full** — ≥3 in `built, awaiting audit` → "Lane full: audit and
   close <T-list> before building."
3. **Blocking bench items** on the next tasks in topo order → "B-#### gates
   <T-list>; run /bench."
4. **Runway below floor** — <3 tasks spec-scoped ahead → "Lead with /spec
   <next source in dependency order>."
5. **Otherwise** — the next 1–3 buildable tasks in topological order, `[P]`
   flagged, one line each.

Never start anything; recommend only. If the board is empty: "run /stubs."
