# Subway Operations System

This is the Claude Code working file. Read it at the start of every session.

## Project goal

Build and operate a unified data system for a 15-store Subway franchise
operation. Ingest from Fresh Connect (LiveIQ), parse University of Subway
compliance emails, surface dashboards for owner + 3 field managers, and
email a weekly digest every Wednesday morning.

Owner: Bir Amitoj Singh Bhullar.
Build playbook: `SUBWAY_OPS_BUILD_PLAYBOOK.md` (canonical reference).
Task tracker: `SUBWAY_OPS_TASKS.md` (slim checklist).
Architectural decisions: `decisions.md`.

## Stack

- Python 3.12 + `uv` for packaging.
- Postgres (Supabase free tier) for storage.
- Streamlit (Streamlit Cloud free) for dashboards.
- GitHub Actions cron for scheduled jobs (free tier).
- Gmail (SMTP for outbound, API for inbound uOS).
- Pydantic v2 for typed API contracts.
- httpx + tenacity for resilient HTTP.
- pandas for transforms.

## Directory layout

src/subway_ops/
├── config.py            # pydantic-settings, single Settings singleton
├── calendar.py          # business calendar — Wed-Tue weeks, 02:00 day cutoff
├── db/                  # connection, migrations, upsert helpers, job_runs
├── freshconnect/        # client.py, models.py
├── ingest/              # one module per endpoint
├── transform/           # one module per mart
├── uos/                 # gmail client, parser, ingest
├── digest/              # weekly digest builder + sender
└── dashboard/           # Streamlit app + pages + components

## Naming conventions

Table prefixes:
- raw_* — append-only, untouched payloads (JSONB)
- stg_* — typed, deduplicated, derivable from raw
- mart_* — denormalized, dashboard-ready, derivable from stg
- ref_* — reference data (stores, users, managers)
- ops_* — system metadata (jobs, audit, variances)

Money: NUMERIC(12,4), never float.
Timestamps: TIMESTAMPTZ in UTC.
Dates: DATE representing Subway business date.
Booleans: is_*.

## Business calendar (load-bearing)

- Business day: 02:00 → 01:59 local (America/Los_Angeles for all stores).
- Business week: Wednesday → Tuesday.
- The FreshConnect API's `date` field is business-date-aligned. Trust it.
- The FreshConnect API's `weekEndDate` is always a Tuesday. Trust it.
- Helper functions live in `subway_ops.calendar`. Use them everywhere.

## Idempotency rules

- Every ingest UPSERTs on a natural composite key. Re-running ingest never
  duplicates data. This is the default recovery path for any failure.
- Every long-running job records itself in `ops_job_runs` via the
  `track_job(name)` context manager from `subway_ops.db.job_runs`. This is
  non-negotiable: ingests, mart refreshes, the daily orchestrator, the
  weekly digest sender, the uOS ingest — anything launched on a schedule
  or by a CLI script — MUST wrap its work in `with track_job(...) as meta`.
  Set `meta["rows_written"]` for ingests; everything else useful for
  debugging goes elsewhere in `meta` and lands in the `metadata` JSONB
  column. Exceptions are caught, recorded as failures, and re-raised.
- Backfill uses `ops_backfill_progress` so partial runs are resumable.

## How to add a new ingest endpoint

1. New SQL migration creating `raw_<endpoint>` and `stg_<endpoint>`.
2. New Pydantic model in `freshconnect/models.py`.
3. New ingest module in `ingest/<endpoint>.py` exposing
   `ingest(start, end, store_numbers) -> int`.
4. Add to `scripts/daily_pull.py` if it should run daily.
5. Add a fixture-based test in `tests/test_ingest_<endpoint>.py`.

## How to add a new mart

1. New SQL migration creating `mart_<name>`.
2. New transform module in `transform/mart_<name>.py` with `refresh(...)`.
3. Add to `scripts/refresh_marts.py`.
4. Add a synthetic-fixture test.

## How to add a new store

1. Append a row to `seed/stores.csv` (store_number, store_name, city,
   state, in-store manager name, timezone, opening date).
2. If the new store is in a new field manager's cluster, add the
   store_number to that FM's `store_numbers_csv` in
   `seed/field_managers.csv`.
3. Re-run `uv run python scripts/seed_reference.py`. Upserts are
   idempotent; existing rows update, the new one inserts.

## How to add a new dashboard page

1. New file `dashboard/pages/<N>_<name>.py`.
2. Import data helpers from `dashboard/data.py`.
3. Use components from `dashboard/components/`.
4. Respect `st.session_state["assigned_stores"]` for filtering.

## Rules for Claude Code

- One task per PR.
- Always read the relevant Task section of `SUBWAY_OPS_BUILD_PLAYBOOK.md`
  before starting.
- Tests are non-negotiable: every public function gets at least one test.
- Migrations are append-only. Never edit a migration after it has been
  applied. New change = new migration file.
- All raw SQL goes through `db.connection.execute_sql` with parameter
  binding. Never string-format SQL.
- No `print()` outside `__main__` blocks. Use `structlog`.
- Pydantic models use `extra="forbid"` — unknown fields fail loudly.
- Money: `Decimal`, not `float`.
- No new dependencies without updating `pyproject.toml` AND `decisions.md`
  explaining why.

## Secrets and environment

Local dev: `.env` (gitignored), loaded by `pydantic-settings`.
GitHub Actions: encrypted secrets named in the workflow YAML.
Streamlit Cloud: secrets pasted into the platform UI.

Required env vars:
- DATABASE_URL
- FRESHCONNECT_API_CLIENT
- FRESHCONNECT_API_KEY
- GMAIL_USER
- GMAIL_APP_PASSWORD
- GMAIL_TOKEN_JSON_B64 (for inbound uOS API)
- ALERT_EMAIL (where failures go)
- DASHBOARD_URL (referenced in weekly digest)
- APP_ENV (dev | prod)

## Definition of done (for any task)

- Acceptance criteria from `SUBWAY_OPS_BUILD_PLAYBOOK.md` met.
- Tests pass: `uv run pytest`.
- Lint passes: `uv run ruff check .`.
- Type-check passes: `uv run mypy src/`.
- New SQL migrations apply cleanly: `uv run python scripts/migrate.py`.
- Committed and pushed.
- PR opened and merged.
- `decisions.md` updated if any architectural choice was made.
- Status updated in `SUBWAY_OPS_TASKS.md`.
