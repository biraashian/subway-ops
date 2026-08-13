# Chronicle — Thin Index

One line per event. `journal/T-####.md` is the system of record (D-003, D-023);
this file only points at it.

| Date | Ref | Event | Branch | Pointers (journal · verify-log) |
|---|---|---|---|---|
| 2026-08-11 | Part 0 | tree settled: store 10393 seed row + live timezone repaired; recon tests stopped destroying production data; 490 passed / 0 failed | `main` | — |
| 2026-08-11 | T-0000 | Burst harness installed: law, board, bench, gate, 7 invariants, schema drift. Calibration 8/8 — found and fixed a decorative track_job check | `burst/part-1-harness` | `journal/T-0000.md` · `test_logs/T-0000/` |
| 2026-08-11 | SPEC-PPL-001 | approved — 6 REQs, 31 ACs, 10 INVs; interview 6/6 decided | `main` | specs/SPEC-PPL-001.md |
| 2026-08-11 | PLAN-SPEC-PPL-001 | L1 design — 11 modules, 7 tasks forecast, constitution check clean | `main` | design/PLAN-SPEC-PPL-001.md |
| 2026-08-12 | SPEC-PPL-001 | tasked — 7 anchored tasks T-0003…T-0009, 31/31 AC coverage | `main` | tasks/T-0003.md … T-0009.md |
| 2026-08-13 | T-0003 | halted(B-0022) — code complete, 12 tests green, blocked by a gate defect | `forge/T-0003` | journal/T-0003.md · test_logs/T-0003/ |
| 2026-08-13 | /bench | 12 decided, 1 raised (B-0023); D-024…D-027; T-0010…T-0012 minted; T-0003 unhalted | `main` | bench/BENCH.md · DECISIONS.md |
| 2026-08-13 | repo | branch restructure — /bench cherry-picked to `main`; T-0003 and T-0010 rebased to one task each; board repaired | `main` | backup tags `backup/pre-restructure/*` |
| 2026-08-13 | /bench | B-0024 → A; D-028 amends D-024 with the predecessor rule; T-0010 → queued for rework | `main` | DECISIONS.md · bench/BENCH.md |
