# Bench — Open Founder Decisions

Drained by `/bench`, one sitting per founder window. Decided policy-shaped
items also append to `DECISIONS.md`. Format: see root `CLAUDE.md`.

---

### B-0001 — The test suite runs against the production database
Task: — · Blocks: all DB-backed tests · Raised: 2026-08-11
There is no test database. `DATABASE_URL` points at live Supabase, so
DB-backed tests read and write production. Two defects already came from
this: `test_mart_recon_weekly.py` hard-deleted a real store's history on
every run for three months, and DB-backed tests still write real rows to
`ops_job_runs` (42 `refresh_mart_recon_weekly` entries were added by the
Part 0 runs alone, and they surface on the system status page).
Options:
  A) Separate Supabase project for tests, `DATABASE_URL` swapped in CI and
     locally via `.env.test` — true isolation, costs a second free-tier
     project and a migration run per environment.
  B) Postgres in a container for tests (testcontainers or a compose service)
     — fully local, fast, no cloud dependency; migrations run per session.
  C) Schema-per-run inside the existing database (`SET search_path`) —
     cheapest, but a bug in the isolation still lands on production infra.
Burst recommends: **B** — the tests only need Postgres, not Supabase, and a
container removes the production blast radius entirely.   [recommendation]
Status: OPEN

### B-0002 — The cash drop reconciliation sheet is the missing domain source
Task: — · Blocks: `codex/09-MONEY-AND-RECONCILIATION/`, SPEC-RCN-002 · Raised: 2026-08-11
The founder has an existing cash drop reconciliation sheet and has described
it as tacky and hard to use. It is the only written statement of what
"reconciled" means for cash, what tolerances apply, and which fields a
manager actually fills in. Without it the codex chapter is guesswork, and
Rule 1 forbids guessing.
Options:
  A) Founder uploads the sheet; the chapter is written from it and the parts
     that are hard to use are designed away explicitly.
  B) Interview-only reconstruction — slower, and risks missing the edge cases
     that only show up in the sheet's own columns.
Burst recommends: **A**.   [recommendation]
Status: OPEN

### B-0003 — Provider names for the money-side integrations
Task: — · Blocks: SPEC-RCN-003, SPEC-RCN-004, SPEC-RCN-005, D-022 report format · Raised: 2026-08-11
Third-party delivery platforms, the card merchant/processor, and the payroll
provider are all unnamed. Each determines a statement format, and payroll
determines the locked report's layout.
Options:
  A) Founder names all three now; specs pin the formats.
  B) Build format-agnostic importers first and calibrate on a real file later
     — more rework, but unblocks Phase B's shape.
Burst recommends: **A**.   [recommendation]
Status: OPEN

### B-0004 — The coverage floor
Task: — · Blocks: `scripts/verify.sh` reaching its designed bar · Raised: 2026-08-11
Coverage is held at the existing 75% floor rather than the 80% the ceremony
tiering implies. Measured today: 77-78%, so 80 is close but not free — the
Streamlit page modules sit at 21-43% and are the whole gap.
Note: the mypy half of this item was **wrong when raised**. `pyproject.toml`
already sets `strict = true`, and `mypy --strict src/` passes clean on 48
files today. The gate runs `--strict` and always did in effect.
Options:
  A) Hold 75 until the Streamlit pages are retired by the new app (D-019),
     then raise to 80 against what is left — the pages are going away anyway,
     so covering them now is work with a short half-life.
  B) Raise to 80 now and backfill page tests.
Burst recommends: **A**.   [recommendation]
Status: OPEN

### B-0005 — The repo has never been `ruff format`ed
Task: — · Blocks: the `ruff format --check` line in the gate · Raised: 2026-08-11
`ruff format --check .` reports 68 files would change, ~58 of them
pre-existing. The check is commented out of `scripts/verify.sh` with a
pointer here; new files added by the harness were formatted individually so
they do not add to the debt.
Options:
  A) One `refactor`-TYPE task: run `ruff format .`, commit the reformat alone
     with no behavioral change, re-enable the gate line in the same commit.
     One noisy diff, reviewable because it is provably formatting-only.
  B) Format incrementally as files are touched — no big diff, but the gate
     line cannot be re-enabled for months and formatting drift persists.
Burst recommends: **A** — the diff is mechanical and `git diff -w` verifies
it changed nothing but whitespace.   [recommendation]
Status: OPEN
