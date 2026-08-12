---
status: authoritative
source: harvested from the pre-Burst CLAUDE.md
---

# 13 — Build Conventions

The mechanical rules. Where a rule is machine-checked, the checker is named —
that is the authority, not this page.

## Stack

Python 3.12, `uv` for packaging. Postgres (Supabase). Pydantic v2 for API
contracts. httpx + tenacity for HTTP. pandas for transforms. structlog for
logging. Streamlit for the current dashboard, retiring in favour of
FastAPI + Jinja2 + HTMX (D-019).

## Layout

```
src/subway_ops/
├── config.py            # pydantic-settings, one Settings singleton
├── calendar.py          # the business calendar — see codex/01
├── observability.py     # configure_logging()
├── db/                  # connection, migrations, upsert, job_runs
├── freshconnect/        # client.py, models.py
├── ingest/              # one module per endpoint
├── transform/           # one module per mart
├── digest/              # weekly digest builder + sender
└── dashboard/           # Streamlit app, pages, components
```

`tools/` holds gate machinery and is not part of the shipped package.

## Rules

- **No new dependency** without updating `pyproject.toml` **and** `DECISIONS.md`
  with why. After any `pyproject.toml` change, regenerate the deployment lock:
  `uv export --frozen --no-dev --no-emit-project --no-hashes > requirements.txt`,
  and commit it alongside `pyproject.toml` and `uv.lock`.
- **No `print()`** outside a CLI entrypoint. Use structlog. Checked by
  `check_no_print.py`, which exempts `__main__` guards and the `main()` /
  `_main()` they call.
- **Pydantic models use `extra="forbid"`.** Checked by `check_extra_forbid.py`.
- **Money is `Decimal`.** See [02-DATA-MODEL](../02-DATA-MODEL/README.md).
- **All SQL is parameter-bound** through `db.connection.execute_sql`.
- **Tests travel with the unit.** Every public function gets at least one.
- `mypy --strict` and `ruff check` are clean. `pyproject.toml` already sets
  `strict = true`.

## Adding an ingest endpoint

1. Migration creating `raw_<endpoint>` and `stg_<endpoint>`.
2. Pydantic model in `freshconnect/models.py`, inheriting `_FCModel`.
3. `ingest/<endpoint>.py` exposing `ingest(start, end, store_numbers) -> int`.
4. **Register it in `scripts/daily_pull.py`** — either `_default_daily_ingests()`
   (yesterday's window) or `_default_weekly_ingests()` (week-end Tuesday, runs
   Wednesdays). This is the step everyone forgets, so `check_ingest_registered.py`
   fails the gate if you do.
5. Fixture-based test at `tests/test_ingest_<endpoint>.py`.

## Adding a mart

1. Migration creating `mart_<name>`.
2. `transform/mart_<name>.py` with `refresh(...)`, wrapped in `track_job`.
3. Add to `scripts/refresh_marts.py`.
4. Synthetic-fixture test.

## Adding a store

1. Append a row to `seed/stores.csv` — every column, in header order.
   `check_seed_wellformed.py` fails on a short row, which is how store 10393
   got a date into its timezone column and kept it for three months.
2. If the store joins a new territory, add its number to that manager's
   `store_numbers_csv` in `seed/field_managers.csv`.
3. `uv run python scripts/seed_reference.py`. Upserts are idempotent.
4. A new store has no ingested history. Backfill it.

## Tests and the database

DB-backed tests currently run against **production** (B-0001). Until that is
fixed:

- **Never point a test at a real store number.** Use a synthetic identifier and
  seed it `is_active=false` so the ingests cannot pick it up.
- **Never hardcode a date.** Derive it from `subway_ops.calendar`.
- Clean up in teardown, in foreign-key order.

Both rules exist because both were broken: `test_mart_recon_weekly.py` was
hard-deleting store 4092's history on every run, against a week that had stopped
being refreshed two months earlier.
