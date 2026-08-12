---
name: tasks
description: Emit anchored T-#### task files from an approved spec and its plan, and queue them on the board in topological order. Invoke as /tasks SPEC-<AREA>-<nnn>.
disable-model-invocation: true
---

# /tasks — Spec + plan → the build sheet (v0.2)

1. Verify spec `planned` and its PLAN exists. Determine T-IDs: honor the source
   queue's declared mapping where the entry carries one; otherwise mint the next
   free number from the board (D-009).
2. Per forecast unit, write `tasks/T-####.md` in the format of
   `tasks/_TASK-FORMAT.md` with the ANCHORS block (spec / req / ac). Tags: `[P]`
   only if no shared DELIVERABLES and no dependency edge — nothing else (D-007).
3. **Copy the spec's EARS lines verbatim** into ACCEPTANCE_CRITERIA and add the
   concrete test names. The quality bar is one line: "`scripts/verify.sh T-####
   pre-merge` exits 0" — never restate numbers (D-014).
4. CONTEXT.read = the minimum set, not the comfortable set.
5. Coverage check both ways: every AC lands in ≥1 task; every task carries ≥1 AC.
   Fill the spec's §9 task column; spec lifecycle → `tasked`.
6. Board: queue the tasks in dependency order, grouped by story; print the
   summary — N tasks, order, `[P]` set, estimated total build time.
