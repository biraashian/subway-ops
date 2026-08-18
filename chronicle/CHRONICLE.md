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
| 2026-08-13 | T-0010 | built (rework) — B-0024 folded; predecessor rule implemented and tested | `forge/T-0010` | journal/T-0010.md · test_logs/T-0010/ |
| 2026-08-13 | /audit T-0010 | GREEN — 17/17 tests, 9 ACs re-exercised by hand, 5 fences clean, pre-merge re-run 0 at `a1b892b` | `forge/T-0010` | journal/T-0010.md · test_logs/T-0010/ |
| 2026-08-13 | T-0010 | **merged** — audit green; post-merge clean; baseline rotated | `main` | test_logs/T-0010/T-0010-post-merge.md |
| 2026-08-13 | /audit T-0003 | RED — both ACs hold and every fence is clean; two Rule 1 fills found: `dismissed` inert (B-0025) and two columns past the licensed shape (B-0026) | `forge/T-0003` | bench/BENCH.md |
| 2026-08-13 | /bench | B-0025 → A, B-0026 → C, B-0013 → A; D-029…D-031; codex 02 and 11 amended; SPEC-PPL-001 → v1.2.0; residue B-0027, B-0028 | `main` | DECISIONS.md · bench/BENCH.md |
| 2026-08-13 | /bench | B-0027 → A; D-032 — append-only binds at merge, not at application; T-0013 minted for the `--update` hole it exposed; T-0003 unblocked for rework | `main` | DECISIONS.md · tasks/T-0013.md |
| 2026-08-13 | T-0003 | built (rework) — B-0025/B-0026 folded; `dismissed` suppresses, `resolved_by` dropped, `020` edited in place per D-032; 14 tests, drift declared, pre-merge 0 | `forge/T-0003` | journal/T-0003.md · test_logs/T-0003/ |
| 2026-08-13 | /audit T-0003 | GREEN — 14/14 tests, AC-018/AC-020 and D-029/D-030/D-032 re-exercised by hand against the live schema, 4 fences clean, pre-merge re-run 0 at `7c3fc8e` | `forge/T-0003` | journal/T-0003.md · test_logs/T-0003/ |
| 2026-08-13 | T-0003 | **merged** — audit green; post-merge clean; baseline rotated; T-0003 and T-0010 declarations retired (D-028 §3) | `main` | test_logs/T-0003/T-0003-post-merge.md |
| 2026-08-13 | T-0004 | built — people schema: 4 tables + widened ref_users.role; 21 tests; drift declared (4 tables); B-0029 raised — the gate cannot see a constraint change | `forge/T-0004` | journal/T-0004.md · test_logs/T-0004/ |
| 2026-08-13 | /audit T-0004 | GREEN — 21/21 tests, AC-011/AC-014/AC-022/AC-031 and 6 §6 edges re-exercised by hand against the live schema; 5 fences clean; `log_id` is the one addition past §5 and it is disclosed; pre-merge re-run 0 at `1682692` | `forge/T-0004` | journal/T-0004.md · test_logs/T-0004/ |
| 2026-08-13 | T-0004 | **merged** — audit green; post-merge clean; baseline rotated; declaration retired (D-028 §3); board's stale T-0003 row repaired | `main` | test_logs/T-0004/T-0004-post-merge.md |
| 2026-08-17 | /audit T-0005 | RED — B-0031: a committed worktree symlink would replace main's fixtures with a dangling link on merge; code itself clean | `forge/T-0005` | bench/BENCH.md |
| 2026-08-17 | /bench | B-0031 → B+A, B-0030 → C, B-0029 → A; D-033…D-035; T-0014, T-0015 minted; T-0005 → rework | `main` | DECISIONS.md · bench/BENCH.md |
| 2026-08-17 | /audit T-0005 (rework) | GREEN — D-033 both halves verified: symlink untracked (mode 120000 gone), ignore rule widened; merge into a throwaway clone of `main` lands no symlink and leaves `tests/fixtures/` intact; 26/26 tests, AC-026/027/029/030 re-probed by hand; 4 fences clean; pre-merge Run 6 exit 0 at `2c81f7a` | `forge/T-0005` | journal/T-0005.md · test_logs/T-0005/ |
| 2026-08-17 | T-0005 | **merged** — audit green (rework); branch rebuilt on main after an empty-commit rebase loop, content proven byte-identical to `audit/T-0005-verified` | `main` | journal/T-0005.md · test_logs/T-0005/ |
| 2026-08-17 | T-0005 | **merged** — audit green (rework); post-merge clean; baseline rotated. Branch rebuilt after an empty-commit rebase loop, content proven identical to `audit/T-0005-verified` | `main` | test_logs/T-0005/T-0005-post-merge.md |
| 2026-08-17 | /audit T-0007 | RED — B-0032 (mid-week raise overstated a week 50%), B-0033 (AC-013 guards the write, not the read it names) | `forge/T-0007` | bench/BENCH.md |
| 2026-08-17 | /bench | B-0032 → A, B-0033 → C; D-036, D-037; SPEC-PPL-001 → v1.3.0 (AC-012a, CON-006, INV-006 scoped); T-0007 → rework | `main` | DECISIONS.md · specs/SPEC-PPL-001.md |
| 2026-08-17 | /audit T-0007 | RED (rework) — B-0034 (empty week returns a confident $0), B-0035 (tests write punches to real stores); rework itself verified clean | `forge/T-0007` | bench/BENCH.md |
| 2026-08-17 | /bench | B-0034 → B, B-0035 → A, B-0036 → A; D-038…D-040; SPEC-PPL-001 → v1.4.0; T-0016 minted | `main` | DECISIONS.md · specs/SPEC-PPL-001.md |
| 2026-08-17 | T-0007 | built (rework 2) — empty-week rate (D-038), synthetic test stores (D-039); 33 cost tests; pre-merge 0 @ `11433ec` | `forge/T-0007` | journal/T-0007.md · test_logs/T-0007/ |
| 2026-08-18 | /audit T-0007 | **GREEN** — 8 ACs re-derived from the EARS lines; 58 task tests + 38 independent probes green; D-036/D-038 defects confirmed fixed; fences clean. Note: CON-003's arg list still omits `actor_role` that AC-013 requires | `forge/T-0007` | test_logs/T-0007/T-0007-pre-merge.md |
| 2026-08-17 | T-0007 | **merged** — audit green (38 independent probes); post-merge clean; baseline rotated. Two audits, two reworks, D-036…D-039 | `main` | test_logs/T-0007/T-0007-post-merge.md |
