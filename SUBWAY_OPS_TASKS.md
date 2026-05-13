# Subway Operations System — Task Tracker

> Slim companion to `SUBWAY_OPS_BUILD_PLAYBOOK.md`. Use this file as your
> working checklist. The full prompts, acceptance criteria, and verification
> commands live in the playbook — open it side-by-side as you build.

## Status legend

- `[ ]` Not started
- `[~]` In progress
- `[x]` Done

## How to update

For each task, when you start: change `[ ]` to `[~]` and fill in the branch
name. When the PR merges: change `[~]` to `[x]` and fill in the PR link.
Drop short notes (issues encountered, deviations from the prompt) under the
task. Keep notes short — long discussion goes in `decisions.md`.

## Time summary

| Phase | Tasks | Est. time | Status |
|---|---|---|---|
| 0 — Foundation | 5 | 2.8 hrs | 0 / 5 |
| 1 — API Client | 3 | 3.5 hrs | 0 / 3 |
| 2 — Ingestion | 7 | 7.0 hrs | 0 / 7 |
| 3 — Marts & Backfill | 5 | 4.8 hrs | 0 / 5 |
| 4 — Dashboard | 6 | 6.5 hrs | 0 / 6 |
| 5 — Recon & Digest | 4 | 5.3 hrs | 0 / 4 |
| 6 — uOS | 3 | 3.3 hrs | 0 / 3 |
| 7 — Hardening | 4 | 4.5 hrs | 0 / 4 |
| **Total** | **37** | **~37.5 hrs** | **0 / 37** |

At 8 hrs/week → ~5 weeks of build. With debugging and tuning, plan 8–12
calendar weeks.

---

## Day-Zero Pre-Flight (do before Task 0.1)

- [ ] Generate Fresh Connect credentials in LiveIQ
- [ ] Build `seed/stores.csv` (15 stores)
- [ ] Build `seed/field_managers.csv` (Maria, James, Kevin)
- [ ] Create private GitHub repo `subway-ops`
- [ ] Create Supabase project (region us-west-1)
- [ ] Decide on 5 dashboard user emails
- [ ] Set up Gmail "UoS" label + filter
- [ ] Generate Gmail App Password
- [ ] Install local dev tools (uv, Python 3.12, git, Claude Code)

---

---

## Phase 0 — Foundation

### `[~]` 0.1 — Initialize repo, project structure, pyproject
- **Accomplishes:** Scaffolded Python project. After this, `uv sync`, `ruff`, `mypy`, `pytest` all run clean on a skeleton.
- **Branch:** `task-0.1-init`
- **PR:**
- **Time:** 30 min
- **Notes:** Local commit `84c85ed` on `task-0.1-init`. Installed `uv` via official installer (Day-Zero pre-flight gap). Added `.claude/settings.local.json` to `.gitignore`. Open PR when GitHub remote is wired.

### `[~]` 0.2 — Write CLAUDE.md and decisions.md
- **Accomplishes:** Conventions, stack, and rules encoded so every future Claude Code session starts informed.
- **Branch:** `task-0.2-claude-md`
- **PR:**
- **Time:** 20 min
- **Notes:** CLAUDE.md populated verbatim from Appendix A. decisions.md has three foundational entries dated 2026-05-11 (stack, calendar, recon model). Open PR when remote is wired.

### `[~]` 0.3 — Reference data: stores, field managers, users
- **Accomplishes:** DB knows your 15 stores, who manages each, and who has dashboard access. Seed script reads from CSVs.
- **Branch:** `task-0.3-ref-tables`
- **PR:**
- **Time:** 45 min
- **Notes:** Migration `001_ref_tables.sql` + idempotent `scripts/seed_reference.py` + 18 tests. Currently 14 stores in CSV (15th coming); `stores.csv.field_manager_name` is the **in-store** manager (stored as `ref_stores.store_manager_name`); FM↔store assignment derived from `field_managers.csv` and written to `ref_stores.field_manager_name` (FK). Lauren's store 10393 referenced but not yet in stores.csv (warned at seed-time, lands May-end). Added `seed/users.csv` with 5 dashboard users (Bir + Taran as owners; Sokhavy/Ekta/Lauren as field_manager). Added `bcrypt` dep. DB integration tests skip when `DATABASE_URL` unset — need to wire Supabase URL into `.env` to run end-to-end.

### `[~]` 0.4 — Business calendar helpers + tests
- **Accomplishes:** One module owns every date and week calculation. 02:00 day cutoff and Wed–Tue week as trustworthy primitives.
- **Branch:** `task-0.4-calendar`
- **PR:**
- **Time:** 30 min
- **Notes:** Five functions: `business_date_now`, `dt_to_business_date`, `business_week_of`, `previous_business_week`, `is_business_week_end`. Stdlib only (datetime + zoneinfo). 22 tests, 100% coverage on the module. DST cases covered: 2025-03-09 spring-forward (skipped 02:00) and 2025-11-02 fall-back (both `fold=0`/`fold=1` 01:30 occurrences still map to the prior business date).

### `[~]` 0.5 — Database connection, migration runner, ops_job_runs
- **Accomplishes:** Idempotent SQL migrations from Python. First operational metadata table. Every job logs its outcome.
- **Branch:** `task-0.5-db-connection`
- **PR:**
- **Time:** 45 min
- **Notes:** SQLAlchemy engine in `subway_ops.db.connection` (lazy, `pool_pre_ping`, psycopg v3 via URL rewrite); raw-SQL workhorse `execute_sql(sql, params)`. Migration runner in `subway_ops.db.migrate` with checksum-tracked `ops_migrations`; `scripts/migrate.py` is a thin CLI. `subway_ops.db.job_runs.track_job(name)` context manager wraps every scheduled job — sets `meta["rows_written"]`, captures exceptions as `failed`, lands everything else in `metadata` JSONB. Migration `002_ops_tables.sql` creates `ops_migrations` + `ops_job_runs`. 8 db-integration tests + 2 unit tests; all 48 tests + ruff + mypy green against live Supabase. Decision recorded in `decisions.md`. Open PR when remote is wired.

---

## Phase 1 — Fresh Connect Client

### `[~]` 1.1 — FreshConnect HTTP client (auth, retry, rate-limit)
- **Accomplishes:** Single class for every HTTP call to Fresh Connect. Auth headers, exponential backoff on 5xx, specific exception types for each documented failure code, per-endpoint limit validation.
- **Branch:** `task-1.1-client`
- **PR:**
- **Time:** 60 min
- **Notes:** `FreshConnectClient` (httpx + tenacity) with `api-client`/`api-key`/`Accept` headers, structured request logging, context-manager support, and tunable retry knobs (`max_retries`, `retry_initial_wait`, `retry_max_wait`) so tests don't sleep. Exception hierarchy: `FreshConnectError` → `AuthError` (401) / `ForbiddenError` (403) / `BadRequestError` (400) / `NotFoundError` (404) / `RateLimitError` (429, no retry) / `ServerError` (5xx after retries). Pre-call limit validation per endpoint (stores + day-span); `get_transaction_details` / `get_tips_details` additionally reject comma-joined single-store args. `list_restaurants` unwraps the real live shape `[{"restaurantNumber": "..."}, …]` returned by the API on 2026-05-12 (15 stores, smoke-tested). 19 client tests using `httpx.MockTransport` (no respx/responses dep needed) — full suite 64 passed + 4 db-gated skips, ruff + mypy green.

### `[~]` 1.2 — Pydantic models for all 13 endpoints
- **Accomplishes:** Every Fresh Connect response shape becomes a statically-typed Pydantic model. Schema drift fails loudly with `extra="forbid"`.
- **Branch:** `task-1.2-models`
- **PR:**
- **Time:** 90 min
- **Notes:** Pulled `APIDocumentation.pdf` + `APIUrlsDocumentation.pdf` into `docs/freshconnect/` and built models for all 15 endpoints (the playbook listed 13; SalesSummary and TransactionSummary are also documented). Every model inherits `_FCModel` (`populate_by_name=True`, `extra="forbid"`). One `DaysOfWeek` covers all 7-day variants (total / average / percentage all Optional); `DaysOfWeekLong` handles Wisr's full-name day keys. Restaurant numbers accept both `restaurantNumber` and the documented typo `resturantNumber` via `AliasChoices`. All money/percentage fields are `Decimal`; datetimes are naive (storage layer attaches LA tz). 16 model tests (one per envelope) parse the doc samples; full suite 80 passed + 4 db-gated skips, ruff + mypy green. Task 1.3 will replace inline samples with recorded fixtures.

### `[~]` 1.3 — Discovery script + recorded fixtures
- **Accomplishes:** Hits every endpoint with your real credentials, saves response bodies as test fixtures, produces a field-coverage report. First real-world confirmation the API behaves as documented.
- **Branch:** `task-1.3-discovery`
- **PR:**
- **Time:** 60 min (+ wait time if rate-limited)
- **Notes:** `scripts/discovery.py` exercises all 15 endpoints against a single store (defaults to first active in `ref_stores`; `--store` overrides; `--no-db` for DB-less runs). Wraps itself in `track_job("discovery")` with the day/week-end/endpoint list in metadata. On 429 it stops gracefully and prints the resume list. `tests/fixtures/recorded/` is gitignored; `tests/test_recorded_fixtures.py` skips on fresh checkouts and parses each fixture against its model otherwise. Ran live against store 4092 on 2026-05-12: 15/15 endpoints HTTP-200; first pass parsed 13/15. Fixed two real-vs-doc drifts (decisions.md entry dated 2026-05-12): `TimeclockEntry` now uses `hoursBeforeAdj`/`hoursAfterAdj`/`adjAmount` (live names) instead of the doc-sample's `hours`/`totalAdj`/`totalBeforeAdj`; `Tender.card_last_four` accepts both `cardLast4` (live) and `cardLastFour` (doc) and is Optional. Second discovery run: 15/15 parsed. `docs/api_field_coverage.md` regenerated. Full suite: 95 passed + 4 db-gated skips.

---

## Phase 2 — Ingestion Layer

### `[~]` 2.1 — Schema + ingest: DailySalesSummary
- **Accomplishes:** Daily per-store totals flowing end-to-end. Sets the pattern every other ingest follows.
- **Branch:** `task-2.1-daily-sales`
- **PR:**
- **Time:** 60 min
- **Notes:** Migration `003_daily_sales.sql` creates `raw_daily_sales` (JSONB envelope log) and `stg_daily_sales` (typed, FK on `ref_stores`, PK on (restaurant_number, business_date)). New `subway_ops.db.upsert.upsert_rows(table, rows, key_cols)` is the canonical `INSERT … ON CONFLICT DO UPDATE` helper — identifier-validated, accepts an empty list, falls back to `DO NOTHING` when all cols are keys. `subway_ops.ingest.daily_sales.ingest(start, end, store_numbers=None, *, client=None)`: resolves default stores from `ref_stores`, plans batches (20-store × 50-day caps via `plan_batches`), persists raw + parses via `DailySalesSummaryResponse` + upserts to stg, wrapped in `track_job("ingest_daily_sales")`. Tests: 4 unit (batching) + 3 db-integration (writes / idempotency / ops_job_runs row). Verified live against store 4092 for 2026-05-05..05-11 → 7 rows; re-run = 7 rows (no dupes). Full suite 102 passed + 4 db-gated skips.

### `[~]` 2.2 — Schema + ingest: ControlSheet (weekly)
- **Accomplishes:** The richest endpoint — weekly cash control, sales itemization, bread, labor — flattened into one wide table (~120 columns). Foundation for both the weekly mart and the entire reconciliation flow.
- **Branch:** `task-2.2-controlsheet`
- **PR:**
- **Time:** 90 min
- **Notes:** ControlSheet's six nested sections (cash control / bread / labor / metrics / sales itemization / unit itemization) each contain ~20 fields, every field a 7-day dict plus a footer. Strict "8 cols per field" flatten produced **820 columns** in `stg_controlsheet_weekly` (well below PG's 1600 ceiling), not the playbook's "~120" estimate. Schema authored in Python (`subway_ops.ingest.controlsheet` field-section tables → `column_definitions()` → `generate_ddl()`); migration `004_controlsheet.sql` was emitted by `python -m subway_ops.ingest.controlsheet --print-ddl`. A test asserts the on-disk migration equals the generator's current output so future schema changes are guaranteed to round-trip. Footer column unifies `total` and `average` (labor/rate fields emit the latter); percentage cols only created where the API returns them (live coverage drives the truth, not the doc sample). `ingest(week_end, store_numbers=None, *, client=None)` chunks 40 stores per call, persists raw envelope, parses, flattens, upserts; wrapped in `track_job("ingest_controlsheet")`. 5 tests (2 DDL/flatten unit + 3 db integration). Verified live against store 4092 for week ending 2026-05-05 → netSales $6,566.89, 428 customers, $680 deposit, footlong 64.89% mix. Idempotent. CLAUDE.md updated with wide-table rationale.

### `[~]` 2.3 — Schema + ingest: PaidOutsAndNoSales (cash drops)
- **Accomplishes:** Every POS-recorded cash drop event lands in staging. Combined with ControlSheet's `depositInBank`, this is the data backbone of reconciliation.
- **Branch:** `task-2.3-paidouts`
- **PR:**
- **Time:** 60 min
- **Notes:** Migration `005_paidouts_no_sales.sql`: `raw_paidouts_no_sales` JSONB log; `stg_no_sales` PK on `(restaurant_number, event_time, clerk_id, no_sale_type)`; `stg_paid_outs` PK on `(restaurant_number, event_time, clerk_id, amount, reason)`; `stg_cash_drops` view filters `no_sale_type='cash drop'`. `business_date` is computed at ingest by attaching `STORE_TZ` to the model's naive `time` and applying the 02:00 cutoff via `dt_to_business_date`. `subway_ops.ingest.paidouts.ingest(start, end, store_numbers=None, *, client=None)` batches 20-store × 31-day windows, deduplicates per-batch by PK before upserting (live batches can carry duplicate keys), wraps in `track_job("ingest_paidouts_no_sales")`. 8 tests: 5 unit (cutoff math + batching) + 3 db integration (write / view / idempotency). Live verified against store 4092 for 2026-05-05..05-11 — 86 noSales (74 cash-in / 9 cash-drop / 3 no-sale) + 2 paid-outs ($26 total); re-run unchanged. Full suite 115 passed + 4 db-gated skips.

### `[~]` 2.4 — Schema + ingest: InventoryMovement
- **Accomplishes:** Daily per-item inventory deltas (deliveries, transfers, waste) flow into staging.
- **Branch:** `task-2.4-inventory`
- **PR:**
- **Time:** 60 min
- **Notes:** Migration `006_inventory_movement.sql`: `raw_inventory_movement` JSONB log; `stg_inventory_movement` PK on `(restaurant_number, business_date, inventory_item)`; `stg_inventory_movement_totals` PK on `(restaurant_number, business_date, metric_name)`. `subway_ops.ingest.inventory_movement.ingest(start, end, store_numbers=None, *, client=None)` chunks 20-store × 50-day windows, persists raw + parses + flattens day's `items[]` and `totals[]` into their tables, dedupes by PK, wrapped in `track_job("ingest_inventory_movement")`. Recorded fixture refreshed to a 7-day window since single days return empty (`inventory_movement.json`: 1 reporting day, 20 items + 3 totals). 5 tests (3 batching unit + 2 db integration). Live verified against store 4092 for 2026-05-05..05-11: 20 inventory items + 3 totals (UNITS / DRINKS / COST OF GOODS) → 23 rows; rerun unchanged. Full suite 120 passed + 4 db-gated skips.

### `[~]` 2.5 — Schema + ingest: Wisr (weekly WISR)
- **Accomplishes:** Subway's gold-standard weekly food-cost analysis lands in staging. Drives food-cost variance KPIs in `mart_store_weekly`.
- **Branch:** `task-2.5-wisr`
- **PR:**
- **Time:** 90 min
- **Notes:** Generated DDL like ControlSheet — `subway_ops.ingest.wisr.column_definitions()` drives `python -m subway_ops.ingest.wisr --print-ddl` → `007_wisr.sql`. Short section prefixes (`acg_` / `ics_` / `ssi_` / `usi_` / `csi_` / `dc_` / `cbost_`) prevent name clashes between subfields that share names across sections (e.g. `costOfGoods` appears in both salesSummaryItems and inventoryCategoriesSummary). `stg_wisr_weekly` is ~187 cols wide on PK `(restaurant_number, week_end_date)`; `stg_wisr_inventory_items` is the per-item table on PK `(restaurant_number, week_end_date, item_name)`. `ingest(week_end, store_numbers=None, *, client=None)` chunks 25 stores/call (per the documented cap), persists raw, parses, flattens, dedupes items per-batch, wrapped in `track_job("ingest_wisr")`. 5 tests (3 unit: DDL/flatten coverage + migration round-trip; 2 db integration). Live verified against store 4092 week ending 2026-05-05: 1 weekly row (428 customers, factor 9.90, avg ticket $15.34, net Subway sales $6,566.89) + 121 inventory items. Re-run unchanged. Full suite 125 passed + 4 db-gated skips.

### `[~]` 2.6 — Schema + ingest: DailyTimeclock + ThirdPartyDailySalesSummary
- **Accomplishes:** Last two daily-grain endpoints. Timeclock fills labor detail; third-party fills delivery channel breakdown.
- **Branch:** `task-2.6-timeclock-3p`
- **PR:**
- **Time:** 60 min
- **Notes:** Migration `008_timeclock.sql`: `raw_timeclock` + `stg_timeclock` (PK on (restaurant_number, clerk_id, clock_in); `business_date` computed via 02:00 cutoff; stores `hours_before_adj` and `hours_after_adj` directly — playbook's `hours_total` collapsed to the explicit pair to keep both signals). Migration `009_third_party_daily.sql`: `raw_third_party_daily` + `stg_3p_daily` (PK on (restaurant_number, business_date)) + `stg_3p_daily_provider` (PK adds provider). Ingest modules `subway_ops.ingest.timeclock` (10-store × 30-day caps) and `subway_ops.ingest.third_party_daily` (20-store × 30-day caps), both wrapped in their respective `track_job(...)`s. Heavy transactional-grain endpoints (TransactionDetails, TipsDetails, TransactionSummary, ThirdPartyTransactionSummary, WasteBreadCredits) deferred to Phase 7 per playbook. 10 tests (6 unit batching + 4 db integration). Live verified store 4092 for 2026-05-05..05-11: 13 timeclock shifts (96.5 hours); 7 days of 3P sales totaling $800.61 across doordash ($572.79 / 25 txns) / uber ($182.11 / 10 txns) / grubhub ($45.71 / 2 txns). Idempotent. Full suite 135 passed + 4 db-gated skips.

### `[~]` 2.7 — Daily orchestrator + GitHub Actions cron
- **Accomplishes:** Single `daily_pull.py` runs all six ingests with right windows. GitHub Actions fires it every morning at 03:00 PT. System is now ingesting automatically.
- **Branch:** `task-2.7-orchestrator`
- **PR:**
- **Time:** 60 min
- **Notes:** `scripts/daily_pull.py` factored into pure `run_daily_pull(today, daily_ingests, weekly_ingests)` (testable) and a thin `main()` that wraps it in `track_job("daily_pull")`. 5 daily ingests fire every run with yesterday's window; 2 weekly ingests (controlsheet, wisr) only on Wednesday for the just-closed Tuesday. `scripts/notify_failure.py` sends a plain-text Gmail SMTP_SSL email with the GitHub Actions run URL stitched from `GITHUB_SERVER_URL`/`GITHUB_REPOSITORY`/`GITHUB_RUN_ID`. `.github/workflows/daily_pull.yml` runs `migrate.py` then `daily_pull.py` then `notify_failure.py` on failure, cron at 10:00 UTC + `workflow_dispatch`. Settings extended with gmail/alert/dashboard env vars (empty defaults). CLAUDE.md "how to add a new ingest" updated to point at the new dispatcher. 7 tests (3 orchestrator dispatch + 4 notify_failure). End-to-end live run on 2026-05-12 (Tue, no weeklies): daily_pull row in `ops_job_runs` shows `status=success`, `rows_written=223` (14 daily_sales, 127 paidouts, 0 inventory, 46 timeclock, 36 3p_daily) with per-ingest breakdown in metadata JSONB. Full suite 142 passed + 4 db-gated skips.

---

## Phase 3 — Marts & Backfill

### `[~]` 3.1 — `mart_store_daily`
- **Accomplishes:** One row per store per business date with every daily-grain KPI computed. Powers dashboard "current week" views and 30-day trends.
- **Branch:** `task-3.1-mart-daily`
- **PR:**
- **Time:** 60 min
- **Notes:** Migration `010_mart_store_daily.sql` defines the mart with four GENERATED ALWAYS STORED columns (`sales_per_labor_hour`, `average_ticket`, `third_party_pct`, `food_cost_pct`) so Python never recomputes a rate — Postgres owns the math. PK on `(restaurant_number, business_date)`. `subway_ops.transform.mart_store_daily.refresh(start, end)` runs one `INSERT … ON CONFLICT DO UPDATE` over a CTE union of `stg_daily_sales` / `stg_3p_daily` / `stg_inventory_movement_totals` (filtered to `COST OF GOODS COST`) / `stg_cash_drops` count. Default window is the last 14 days to absorb late corrections. Wrapped in `track_job("refresh_mart_store_daily")`. 4 tests (3 db integration with synthetic seed: generated columns + idempotency + zero-denominator guards; 1 unit on default lookback). Live verified across store 4092 for 2026-05-05..05-11: 7 mart rows, sales/labor $30–88, average ticket $12.83–$19.19, 3p mix 7.8–31% — the days where upstream inventory totals are 0 leave `food_cost_pct` null by design (no fake imputation). Full suite 146 passed + 4 db-gated skips.

### `[~]` 3.2 — `mart_store_weekly`
- **Accomplishes:** One row per store per Tuesday week-end, blending ControlSheet, Wisr, daily rollups. KPIs flagged against 22%/28% store-level targets.
- **Branch:** `task-3.2-mart-weekly`
- **PR:**
- **Time:** 60 min
- **Notes:** Migration `011_mart_store_weekly.sql`: one row per `(restaurant_number, week_end_date Tuesday)`, with `week_start_date` GENERATED as `week_end_date - 6 days`. Two GENERATED BOOLEAN flags compare fractional pct columns against the 22%/28% targets (NULL-safe via CASE). Targets live in `subway_ops.config` as `TARGET_FOOD_COST_STORE` / `TARGET_LABOR_COST_STORE` (module constants, not env-driven). `refresh(week_end=None)` defaults to `previous_business_week()`; single `INSERT ... ON CONFLICT DO UPDATE` joining `stg_controlsheet_weekly` with `stg_wisr_weekly` (LEFT JOIN) and a small CTE that sums `stg_daily_sales.transactions` across the 7-day window for `transactions_total`. **WISR percentages are stored upstream as whole-percent (e.g. 27.23) and converted to fractional (÷100) at refresh time** so the GENERATED flags compare naturally. `labor_cost_pct` left NULL with a TODO — no wage source yet. Wrapped in `track_job("refresh_mart_store_weekly")`. 4 tests (1 unit on target constants + 3 db integration: join+conversion+flags / above-target flag flip / idempotency). Live verified store 4092 week ending 2026-05-05: net_sales $6,566.89, 573 units, 101.64 hours, 428 customers, factor 9.90, average ticket $15.34, productivity 5.64, food_cost_expected_pct 0.185588 (18.56%), `is_food_cost_in_target=True`. Full suite 150 passed + 4 db-gated skips.

### `[~]` 3.3 — `mart_field_manager_portfolio`
- **Accomplishes:** Rollup to FM level with sales-weighted KPIs vs portfolio targets (20%/25%).
- **Branch:** `task-3.3-mart-fm`
- **PR:**
- **Time:** 45 min
- **Notes:** Migration `012_mart_field_manager_portfolio.sql`: PK on `(field_manager_name, week_end_date)`, two GENERATED flags vs the 20%/25% portfolio thresholds. Targets land in `subway_ops.config` (`TARGET_FOOD_COST_PORTFOLIO=0.20`, `TARGET_LABOR_COST_PORTFOLIO=0.25`). `refresh(week_end=None)` joins `mart_store_weekly` to `ref_stores`, groups by FM, computes sales-weighted `portfolio_food_cost_pct = SUM(food_pct * net_sales) / SUM(net_sales)` — but only over rows where the pct is non-NULL (numerator AND denominator), so a missing food cost on one store doesn't silently drag the weighted average toward 0. Store-in-target counts come straight from upstream BOOLEAN flags. Wrapped in `track_job("refresh_mart_field_manager_portfolio")`. 5 tests (1 unit on targets + 4 db integration: weighted-skew correctness, NULL-pct guard, store_count flag passthrough, idempotency). Live verified for week ending 2026-05-05: Sokhavy → 1 store, $6,566.89 net sales, portfolio_food_cost_pct 0.000000 (matches WISR actualPercentage=0), `is_food_cost_in_portfolio_target=True`. Full suite 155 passed + 4 db-gated skips.

### `[~]` 3.4 — 12-month backfill script
- **Accomplishes:** Loads 12 months of history. Respects rate limits. Fully resumable via `ops_backfill_progress`. Refreshes marts at the end.
- **Branch:** `task-3.4-backfill`
- **PR:**
- **Time:** 90 min code + days of wall-clock for full run
- **Notes:** Migration `013_backfill_progress.sql` creates `ops_backfill_progress` PK on (job_name, endpoint, window_start, window_end). `scripts/backfill.py` plans windows per endpoint (daily endpoints chunked by their per-call day-cap: 50/31/50/30/30; weekly endpoints emit one Tuesday per chunk), filters out already-completed windows, calls the right ingest, records each success. On `RateLimitError` exits 0 with a status table + resume hint. After all endpoints clean, refreshes mart_store_daily for the whole range plus mart_store_weekly + mart_field_manager_portfolio per Tuesday. CLI flags: `--start` / `--end` (default end=today, start=end-365) / `--status` / `--no-refresh`. Wrapped in `track_job("backfill")`. 12 tests (10 unit pure window planning + dispatch, 2 db integration on checkpoint round-trip). Two existing mart tests fixed to assert "at least one row" instead of "exactly one" so they work alongside live backfilled data. Smoke-tested live for 2026-05-05..05-12: 9 windows loaded (1 each for daily endpoints, 2 for controlsheet+wisr); resume run = 0 windows; with `--refresh` populated marts: 112 daily / 28 weekly / 8 FM portfolio rows. Status table afterwards shows 9/9 done across 7 endpoints. Full suite 167 passed + 4 db-gated skips.

### `[~]` 3.5 — Mart refresh job + schedule
- **Accomplishes:** Marts stay current throughout the day without manual intervention. Dashboard never more than 4 hours stale.
- **Branch:** `task-3.5-refresh-cron`
- **PR:**
- **Time:** 30 min
- **Notes:** `scripts/refresh_marts.py` factored into `run_refresh(today, *, refresh_daily, refresh_weekly, refresh_fm)` (testable with mocks) plus a `main()` that wraps in `track_job("refresh_marts")`. Daily mart refreshes the rolling 14-day window; weekly + FM marts refresh the **last 2 closed Tuesdays** (catches late corrections two weeks back without burning cycles on stable history). `.github/workflows/refresh_marts.yml` cron `0 */4 * * *` (every 4 hours) + `workflow_dispatch`; same notify_failure plumbing as daily_pull. 5 unit tests covering week-end math and dispatcher call shape — no DB needed. Live smoke run on 2026-05-13: 1 daily refresh (113 rows), 2 weekly refreshes (27 rows total), 2 FM refreshes (8 rows). `ops_job_runs` shows `status=success`, `rows_written=148`, full per-mart breakdown in metadata. Full suite 172 passed + 4 db-gated skips.

---

## Phase 4 — Dashboard

### `[~]` 4.1 — Streamlit app skeleton + authentication
- **Accomplishes:** Multipage Streamlit app with login. Role-based store visibility (owner sees all 15; FMs see their cluster).
- **Branch:** `task-4.1-streamlit-skeleton`
- **PR:**
- **Time:** 60 min
- **Notes:** Added `streamlit>=1.36` + `streamlit-authenticator>=0.3.2` as runtime deps (the dashboard ships to Streamlit Cloud). Module layout per playbook: `dashboard/{app,auth,data}.py` + `dashboard/components/{__init__,kpi_card,store_grid,filters}.py` + `dashboard/pages/{1_owner_overview,2_store_detail,3_field_manager,4_reconciliation}.py`. `auth.py` loads `ref_users` into the `Authenticate` config with `auto_hash=False` (seed already bcrypts); cookie signing key reads `.streamlit/secrets.toml` first, falls back to `AUTH_COOKIE_KEY` env. `visible_stores()` returns full roster for owners and for users with NULL `assigned_stores`, otherwise filters. `data.py` exposes `@st.cache_resource cached_engine()` + `@st.cache_data(ttl=300)` query helpers for `mart_store_daily/weekly` and FM portfolio. Sidebar shows display name, role, store count, "Last data refresh" = `MAX(refreshed_at)` from the daily mart, plus Sign-Out. Each page is a "Welcome {name}…" placeholder pending Tasks 4.2-4.6. Ruff per-file-ignore for `N999` on the digit-prefixed Streamlit page files. 8 auth unit tests (credentials shape, list/CSV assignment parsing, owner-sees-all, null-fallback, filter ordering). decisions.md entry on the auth choice. Smoke-launched headless on :8765 → HTTP 200. Full suite 180 passed + 4 db-gated skips.

### `[~]` 4.2 — Owner overview page (15-store grid)
- **Accomplishes:** At-a-glance view of all 15 stores. Sortable, color-coded grid plus 13-week trend chart.
- **Branch:** `task-4.2-owner-overview`
- **PR:**
- **Time:** 90 min
- **Notes:** Page top: a "Last closed week" vs "Current week (in progress)" radio that pivots through `current_and_last_week_ends()` (new in `dashboard/data.py`). Six KPI cards: total net sales, transactions, portfolio food-cost % (sales-weighted in Python over the visible rows; respects NULL pct), portfolio labor cost (placeholder — pending wage source), stores-in-target count, recon status (placeholder — Task 5.1). Color rules in `dashboard/components/__init__.py`: `status_bucket()` returns `in_target`/`near`/`off`/`unknown` against the per-store targets from `config.py` ± `NEAR_TARGET_TOLERANCE` (2pp); `food_cost_emoji` / `labor_cost_emoji` adapt for `portfolio=True`. Grid uses `st.dataframe` with `selection_mode="single-row"` + `on_select="rerun"`; selecting a row sets `st.session_state["selected_store"]` and `st.switch_page` jumps to store detail. 13-week portfolio net-sales trend via Altair (`portfolio_trend()` adds the new mart query). `weekly_overview` extended with FM name and cash o/s. 11 new helper tests (status bucketing, week selector, weighted-food-cost util pulled via importlib because of the digit-prefixed page filename). Smoke launched headless → both `/` and `/owner_overview` return HTTP 200. Full suite 191 passed + 4 db-gated skips.

### `[~]` 4.3 — Store detail drill-down page
- **Accomplishes:** Single store's full picture across four tabs: daily trend, weekly history, WISR inventory detail, cash drops.
- **Branch:** `task-4.3-store-detail`
- **PR:**
- **Time:** 90 min
- **Notes:** Store selector at top defaults to `st.session_state["selected_store"]` (set by the owner-overview row-click), falls back to first visible store. Four tabs: **Daily** (30-day Altair line charts for net sales / transactions / sales-per-labor-hour / food-cost % from `mart_store_daily`, with the 22% target overlay), **Weekly** (13-week trends from `mart_store_weekly` with both 22% and 28% target lines), **Inventory** (`stg_wisr_inventory_items` for a chosen Tuesday, sorted by largest negative `value_difference` first, with red/green text via pandas Styler), **Cash drops** (events for a chosen date range, each joined to the same-day `deposit_in_bank` via a `VALUES`-based unpivot of ControlSheet's seven per-day columns). Three new cached helpers in `data.py`: `store_weekly_history(store, weeks)`, `wisr_inventory_items(store, week_end)`, `cash_drops_with_deposits(store, start, end)`. Variance colouring is a pure helper (`_style_value_difference`) so it's unit-tested without Streamlit. 10 new tests (3 pure colour + 5 DB-integration on helper shape and the unpivot join correctness + 2 importability sanity). Smoke launched headless: `/`, `/owner_overview`, `/store_detail` all return HTTP 200. Full suite 199 passed + 6 db-gated skips.

### `[ ]` 4.4 — Field manager portfolio page
- **Accomplishes:** FM-level view: their 5 stores vs portfolio targets with side-by-side comparison.
- **Branch:** `task-4.4-fm-page`
- **PR:**
- **Time:** 60 min
- **Notes:**

### `[ ]` 4.5 — Deploy to Streamlit Cloud (or Fly.io)
- **Accomplishes:** Dashboard reachable at a stable URL by all 5 users. Decide: Streamlit Cloud (free, public URL with in-app auth) vs Fly.io ($5/mo, private URL).
- **Branch:** `task-4.5-deploy`
- **PR:**
- **Time:** 30–45 min
- **Notes:**

### `[ ]` 4.6 — Polish: filters, exports, KPI thresholds
- **Accomplishes:** Dashboard becomes pleasant. State persists across pages, tables export to CSV, thresholds configurable via `config.py`.
- **Branch:** `task-4.6-polish`
- **PR:**
- **Time:** 60 min
- **Notes:**

---

## Phase 5 — Reconciliation & Weekly Digest

### `[ ]` 5.1 — `mart_recon_weekly` + `ops_variance` table
- **Accomplishes:** Reconciliation mart with auto-computed status (clean/flagged/escalated/unverified) from POS deposit vs operator-entered actual deposit.
- **Branch:** `task-5.1-mart-recon`
- **PR:**
- **Time:** 75 min
- **Notes:**

### `[ ]` 5.2 — Reconciliation review page (variance entry)
- **Accomplishes:** Page where operator reviews each store/week and enters actual bank deposit only when it differs from POS-recorded. Audit-logged.
- **Branch:** `task-5.2-recon-page`
- **PR:**
- **Time:** 90 min
- **Notes:**

### `[ ]` 5.3 — Weekly digest builder (HTML email body)
- **Accomplishes:** Function that produces self-contained HTML email summarizing the just-closed business week. Inline CSS, no JS, no external images — renders in any email client.
- **Branch:** `task-5.3-digest-builder`
- **PR:**
- **Time:** 90 min
- **Notes:**

### `[ ]` 5.4 — Wednesday digest sender + GitHub Actions cron
- **Accomplishes:** Email digest goes out every Wednesday morning at 07:00 PT (06:00 PT during PDT). Idempotent — re-running for same week is a no-op.
- **Branch:** `task-5.4-digest-cron`
- **PR:**
- **Time:** 60 min
- **Notes:**

---

## Phase 6 — University of Subway Pipeline

### `[ ]` 6.1 — Gmail API setup + token + tests
- **Accomplishes:** Read-only OAuth access to Gmail inbox containing uOS emails. After this, system can list and read those emails programmatically.
- **Branch:** `task-6.1-gmail-api`
- **PR:**
- **Time:** 60 min
- **Notes:**

### `[ ]` 6.2 — uOS email parser + ingest
- **Accomplishes:** Parses uOS training compliance email and lands per-employee, per-course rows in staging. Schema-flexible — courses change quarterly without schema changes.
- **Branch:** `task-6.2-uos-parser`
- **PR:**
- **Time:** 90 min
- **Notes:** Drop a real uOS `.eml` into `tests/fixtures/uos_sample_email.eml` BEFORE starting this task so Claude Code can infer structure.

### `[ ]` 6.3 — Compliance widget in dashboard
- **Accomplishes:** Training compliance % shows on owner overview, store detail, and weekly digest. Stores below 90% flagged.
- **Branch:** `task-6.3-compliance-widget`
- **PR:**
- **Time:** 45 min
- **Notes:**

---

## Phase 7 — Hardening & Operate

### `[ ]` 7.1 — Test coverage pass + CI green
- **Accomplishes:** Every module tested; CI runs on every PR. Know within 2 minutes if any change breaks anything.
- **Branch:** `task-7.1-ci`
- **PR:**
- **Time:** 90 min
- **Notes:**

### `[ ]` 7.2 — Observability: structured logs + ops_job_runs surfaced
- **Accomplishes:** When something breaks at 3am you can see what happened. Job history visible in dashboard.
- **Branch:** `task-7.2-observability`
- **PR:**
- **Time:** 60 min
- **Notes:**

### `[ ]` 7.3 — Runbook for every recurring failure mode
- **Accomplishes:** `docs/runbook.md` covers 16 scenarios with symptom → cause → diagnosis → fix. Anyone can operate the system without re-deriving its design.
- **Branch:** `task-7.3-runbook`
- **PR:**
- **Time:** 60 min
- **Notes:**

### `[ ]` 7.4 — Backfill verification + audit reconciliation
- **Accomplishes:** Spot-check 12 months of history against LiveIQ's own reports. Catch any silent data gaps before declaring production-ready.
- **Branch:** `task-7.4-audit`
- **PR:**
- **Time:** 60 min code + hours of manual cross-checks
- **Notes:**

---

## Post-Build

After Task 7.4 merges, the system is in operate mode. Monthly review:
- `[ ]` Confirm all GitHub Actions workflows ran (check Actions tab)
- `[ ]` Confirm `ops_job_runs` shows no recurring failures
- `[ ]` Confirm backfill is current (run `scripts/backfill.py --status`)
- `[ ]` Run `scripts/audit_backfill.py` quarterly

Phase 8+ extensions (when ready):
- `[ ]` Transaction-detail analytics (PLU mix, discounts by employee)
- `[ ]` Anomaly detection on daily KPIs
- `[ ]` SubVentory parity check
- `[ ]` System API for the trading operation to consume
- `[ ]` Mentor / lender view with PII redaction
- `[ ]` Dubai-entity-compatible deployment posture

---

## End of Tracker
