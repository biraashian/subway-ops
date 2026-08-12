# Chronicle — Thin Index

One line per event. `journal/T-####.md` is the system of record (D-003, D-023);
this file only points at it.

| Date | Ref | Event | Branch | Pointers (journal · verify-log) |
|---|---|---|---|---|
| 2026-08-11 | Part 0 | tree settled: store 10393 seed row + live timezone repaired; recon tests stopped destroying production data; 490 passed / 0 failed | `main` | — |
| 2026-08-11 | T-0000 | Burst harness installed: law, board, bench, gate, 7 invariants, schema drift. Calibration 8/8 — found and fixed a decorative track_job check | `burst/part-1-harness` | `journal/T-0000.md` · `test_logs/T-0000/` |
