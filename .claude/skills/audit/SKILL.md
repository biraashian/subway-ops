---
name: audit
description: Independent validation gate in a forked clean context - verifies each acceptance criterion empirically against the diff and the pre-merge log, GREEN or RED, never repairs. Invoke as /audit T-####.
disable-model-invocation: true
context: fork
---

# /audit — Gate 2, validation (v0.2 · D-014)

This runs forked on purpose: the builder's assumptions must not leak in.
Verification (did the rules pass) already happened — verify.sh. This gate asks
the other question: is it the RIGHT thing — oracle = the spec's EARS lines.

1. Read only: the task file, its anchored spec sections (REQs, ACs, INVs, §6,
   §7), the diff of `forge/T-####` vs the integration branch, and the pre-merge
   log under `test_logs/T-####/`.
2. Verify **empirically**: run the named tests; exercise each AC's trigger and
   observe; probe each §6 edge; confirm each INV across exercised paths.
3. Fences: nothing outside DELIVERABLES changed; no FORBIDDEN_ACTION; no NG-###
   crossed — gold-plating past the spec is RED even when the extra code is good.
4. Verdict table (Check | Item | Method | Result), then:
   - **GREEN** → chronicle line, board → `awaiting your review`, 5-line founder
     summary naming the single riskiest spot.
   - **RED** → bench item with observed-vs-specified, board → `audit failed(B-####)`.
     Never repair — builder and auditor stay separate.
5. If the SPEC proves ambiguous during audit: that's a spec defect → bench item
   against the spec; result is RED-blocked, not a judgment call.
