---
name: build
description: Implement exactly one task to pre-merge green - WIP-gated, journal-before-gate, halt-not-guess, R-503 wired. Invoke as /build T-####.
disable-model-invocation: true
---

# /build — One task, to the gate (v0.2)

## Preconditions (refuse to start otherwise)
1. The task's ANCHORS point at a spec with `status: approved`, zero open Qs —
   the Definition of Ready (Rule 2).
2. No OPEN bench item blocks its REQs.
3. **WIP check (D-005):** if 3 tasks already sit in "built, awaiting audit,"
   halt: "lane full — audit and close first," and stop.
4. If working a `[P]` task, use a worktree under `.claude/worktrees/T-####`.

## Steps
1. Scoped context only: task file, anchored spec sections, `CONTEXT.read`.
2. Micro-plan echo (≤8 lines): files, order, test approach. Anything outside
   DELIVERABLES → bench, don't proceed.
3. Implement code + tests. Inner loop: `bash scripts/verify.sh T-#### adhoc`.
4. **R-503:** three consecutive failures of the same check → halt, journal the
   cluster, bench item, stop. No grinding.
5. Ambiguity anywhere → HALT that thread: bench item (options + trade-offs +
   marked recommendation), commit WIP to `forge/T-####-wip`, board →
   `halted(B-####)`, stop. A correct guess is still a defect.
6. **Close the loop, in this order (D-003 — the gate asserts the journal):**
   a. Write `journal/T-####.md` — ≥40 lines, target 150: what, why these
      choices, what surprised you. Decision drafts for any decision touched.
      In-repo per D-023; the gate excludes `journal/` from its worktree-clean
      assertion so writing it here does not trip step (b).
   b. `bash scripts/verify.sh T-#### pre-merge` → must exit 0; fix or halt.
   c. Commit `forge/T-####` — message `T-####: <title> [pre-merge green]`.
   d. Chronicle thin line: `| date | T-#### | built | forge/T-#### | journal · log |`
   e. Board → `built, awaiting audit`.
   f. Founder note, ≤10 lines: what was built, the one or two spots worth
      human eyes, how to run it.
7. Recommend `/clear` before the next task — fresh context every time.

## Rules
- Task + spec are the only authorities; a conflict between them is a bench item.
- Every AC verified individually before claiming built — "tests pass" is
  evidence, not a verdict.
