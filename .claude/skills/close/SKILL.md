---
name: close
description: Founder-commanded integration of one approved task - rebase if the queue moved, merge, post-merge, baseline rotation, revert-first on red. Invoke as /close T-#### only after explicit founder approval.
disable-model-invocation: true
---

# /close — The merge critical section (v0.2 · D-002, D-004, D-014)

**Precondition:** the task shows `awaiting your review` with a GREEN audit, and
the founder has explicitly approved in this session. No approval → refuse.
Strictly one task at a time — never batch closes.

## Steps
1. **Rebase check.** If the integration branch advanced since this task's
   pre-merge: rebase `forge/T-####` onto it and re-run
   `bash scripts/verify.sh T-#### pre-merge` — must exit 0 (the merge-queue
   discipline; a stale gate is no gate).
2. Merge: `git checkout <integration> && git merge --no-ff forge/T-####`.
3. `bash scripts/verify.sh T-#### post-merge` — confirms the merge clean and
   **rotates the baseline** for the next task's gate.
4. **Green:** chronicle `| date | T-#### | merged | <integration> | audit green |`,
   board → `merged`, fill the spec's §9 final column. Report in ≤5 lines.
5. **Red (D-004 — revert-first, no debate):**
   a. `git revert -m 1 <merge-commit>` immediately — integration returns green.
   b. Re-run post-merge on the revert to confirm clean and re-rotate.
   c. Bench item carrying the evidence: the post-merge log path, the failing
      check, observed vs. expected.
   d. Board → `audit failed(B-####)`; the fix re-enters via spec → build →
      audit. Never patch the integration branch directly.
   e. Same task reverting twice → flag it loudly: spec defect (D-004 reopen).
