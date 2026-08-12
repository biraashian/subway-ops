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

### `[~]` 4.4 — Field manager portfolio page
- **Accomplishes:** FM-level view: their 5 stores vs portfolio targets with side-by-side comparison.
- **Branch:** `task-4.4-fm-page`
- **PR:**
- **Time:** 60 min
- **Notes:** FM selector locks to the user's own FM when the role is `field_manager` (looked up via `ref_field_managers.email`), shows a dropdown for owners. Four KPI cards: food cost %, labor cost %, total sales, stores-in-target — each carries a "+/-Xpp vs target" delta badge. Side-by-side store mini-grid from `mart_store_weekly` with food/labor emoji chips. Two Altair trend charts (13 weeks) with horizontal target lines at 20% / 25%; labor chart gracefully degrades to a placeholder banner while `labor_cost_pct` is still NULL upstream. Four new data helpers: `list_field_managers`, `fm_name_for_email`, `fm_portfolio_history`, `fm_stores_for_week`. `delta_badge_text(actual, target)` is a pure helper (positive = OVER target/bad, negative = under/good, "0.0pp" on equality) — 6 unit tests cover the sign conventions and None/edge cases. Smoke launched headless: `/`, `/owner_overview`, `/store_detail`, `/field_manager` all return HTTP 200. Full suite 205 passed + 6 db-gated skips.

### `[~]` 4.5 — Deploy to Streamlit Cloud (or Fly.io)
- **Accomplishes:** Dashboard reachable at a stable URL by all 5 users. Decide: Streamlit Cloud (free, public URL with in-app auth) vs Fly.io ($5/mo, private URL).
- **Branch:** `task-4.5-deploy`
- **PR:**
- **Time:** 30–45 min
- **Notes:** Root-level `streamlit_app.py` registers all five pages programmatically via `st.navigation()` so the canonical page sources stay under `src/subway_ops/dashboard/pages/` instead of duplicating at the root. Shim adds `src/` to `sys.path` so the package imports without `pip install -e .`. `requirements.txt` (193 lines, no hashes, no editable project line) generated by `uv export --frozen --no-dev --no-emit-project --no-hashes`. `Dockerfile` at repo root for Fly.io (python:3.12-slim, EXPOSE 8501, CMD streamlit run streamlit_app.py). Two deployment docs: `docs/deployment_streamlit_cloud.md` (default; free; public URL + in-app auth) and `docs/deployment_flyio.md` (private URL; ~$5/mo). CLAUDE.md adds the "regenerate requirements.txt after pyproject.toml changes" rule; README.md gains a Deployment section pointing at both docs. Smoke launched the shim headless: all five pages (`/`, `/owner_overview`, `/store_detail`, `/field_manager`, `/reconciliation`) return HTTP 200. Full suite 205 passed + 6 db-gated skips.

### `[~]` 4.6 — Polish: filters, exports, KPI thresholds
- **Accomplishes:** Dashboard becomes pleasant. State persists across pages, tables export to CSV, thresholds configurable via `config.py`.
- **Branch:** `task-4.6-polish`
- **PR:**
- **Time:** 60 min
- **Notes:** Reconciliation thresholds (`VARIANCE_FLAGGED_USD=$5`, `VARIANCE_ESCALATED_USD=$50`) moved into `subway_ops.config` next to the existing 22/28/20/25% KPI targets — every threshold the dashboard reasons about now lives in one place. New `components/helpers.py`: `humanize_relative(ts)` ("12 minutes ago" / "yesterday" / "3 days ago"; tz-aware AND naive inputs OK; future timestamps degrade to "just now") and `csv_download_button(df, filename, key)` (no-ops on empty input). New `components/sidebar.py` — `render_sidebar()` is now called from every page (was only on `app.py`); rebuilds the authenticator for the Sign-Out button so the action works from any page; humanised refresh-age chip + feedback footer driven by `settings.alert_email`. Cross-page filter persistence via shared session-state keys (`KEY_FILTER_WEEK_CHOICE`, `KEY_FILTER_STORE`, `KEY_FILTER_STATUS`) — the week-end radio remembers the operator's pick when they jump between pages, the selected_store carries through the click-to-drill flow, and a new status multiselect on the owner overview filters the grid by food-cost bucket. CSV download buttons added to every grid/chart dataframe on the three real pages. 11 new helper tests (8 humanize_relative coverage + empty CSV no-op + filter-key uniqueness + variance threshold sanity). Smoke launched headless: all five pages return HTTP 200. Full suite 216 passed + 6 db-gated skips.

---

## Phase 5 — Reconciliation & Weekly Digest

### `[~]` 5.1 — `mart_recon_weekly` + `ops_variance` table
- **Accomplishes:** Reconciliation mart with auto-computed status (clean/flagged/escalated/unverified) from POS deposit vs operator-entered actual deposit.
- **Branch:** `task-5.1-mart-recon`
- **PR:**
- **Time:** 75 min
- **Notes:** Migration `014_recon.sql` creates `ops_variance_entries` (PK `(restaurant_number, week_end_date)`, `entered_by` FK on `ref_users.email`, audit `entered_at`) and `mart_recon_weekly` with two GENERATED ALWAYS STORED columns: `variance = pos - actual` (NULL when no entry) and a four-way `status` CASE bucketed by `|variance|` against $5 / $50 thresholds. Postgres owns the math; Python never recomputes status. The $5 / $50 thresholds in the DDL duplicate `subway_ops.config.VARIANCE_FLAGGED_USD / VARIANCE_ESCALATED_USD` (GENERATED columns can't reference Python) — module docstring + migration header call out the sync rule. `subway_ops.transform.mart_recon_weekly.refresh(weeks_back=8)` rebuilds the last N weeks from `stg_controlsheet_weekly.cash_control_deposit_in_bank_total` LEFT JOIN `ops_variance_entries` via a `keys` union so weeks with only a variance entry (no controlsheet yet) still surface as `unverified`. Convenience `refresh_for_week(week_end)` for the recon page's save-and-recompute flow in Task 5.2. Wired into `scripts/refresh_marts.py` with `RECON_LOOKBACK_WEEKS=8` (wider than the 2-week weekly mart window because operators reconcile late). 9 unit/integration tests covering all four status buckets, exact-threshold boundaries ($5 and $50), negative-variance (|abs| bucketing), idempotency, and the zero-weeks-back guard. Live refresh wrote **26 rows** across all 14 stores for the last 8 closed weeks — all `unverified` until Task 5.2's entry form is wired up. Full suite 226 passed + 6 db-gated skips.

### `[~]` 5.2 — Reconciliation review page (variance entry)
- **Accomplishes:** Page where operator reviews each store/week and enters actual bank deposit only when it differs from POS-recorded. Audit-logged.
- **Branch:** `task-5.2-recon-page`
- **PR:**
- **Time:** 90 min
- **Notes:** Filters at top: multi-select week range (defaults to last 4 closed Tuesdays via new `recent_week_ends(n)` helper), store filter respecting `visible_stores()`, status multiselect (4-way). Editable `st.data_editor` disables everything except `actual_bank_deposit` and `note`. Snapshot of original values cached in `st.session_state` (keyed by filter tuple) so the next render can diff. `_diff_rows` is a pure helper that returns `(upserts, deletes)`: amount changes → upsert; note-only change WITH an existing amount → upsert; clearing a previously-saved amount → delete (gated by a "Confirm deletions" checkbox so accidental row clears never destroy audit data). Save flow batches into one transaction per operation via new `data.save_variance_entries(rows, *, entered_by)` (requires `entered_by`, stamps it on every row server-side) and `data.delete_variance_entries(keys)`, then calls `mart_recon_weekly.refresh_for_week(...)` for each touched week so the status chip updates in-place. CSV download for the editor contents. 13 tests (5 pure diff cases + 2 helper week math + 6 db integration on save/delete round-trips). Smoke launched: all 5 pages return HTTP 200. Full suite 239 passed + 6 db-gated skips.

### `[~]` 5.3 — Weekly digest builder (HTML email body)
- **Accomplishes:** Function that produces self-contained HTML email summarizing the just-closed business week. Inline CSS, no JS, no external images — renders in any email client.
- **Branch:** `task-5.3-digest-builder`
- **PR:**
- **Time:** 90 min
- **Notes:** `subway_ops.digest.builder.build_digest(week_end=None)` returns `(subject, html_body)`; defaults to `previous_business_week()`. Split into a pure renderer (`render_digest(DigestData)`) and a DB collector (`_collect_digest_data`) so the unit-test surface needs no live database. `DigestData` is a frozen dataclass — portfolio snapshot, targets table, recon summary, FM rollups, per-store list. Inline `style="..."` on every traffic-light cell; only typography lives in a single `<style>` block in `<head>` (heavy clients drop it, inline backups handle critical cells). 600px max width. Color tokens (GREEN `#22c55e`, YELLOW `#eab308`, RED `#ef4444`, NEUTRAL_BG `#f9fafb`) added to `dashboard/components/__init__.py` and re-exported as `COLOR_*` from the builder so dashboard + email share one palette. Subject format `Subway weekly — week ending {Tue YYYY-MM-DD} — {n} flagged, {m} escalated` regex-pinned in tests. Portfolio percentages computed inline via FILTER-aware sales-weighted CASE expressions so missing pct values don't collapse the denominator. Escalated cases sorted by `|variance|` desc. 29 unit tests in `tests/test_digest_builder.py` — pure helpers (money/pct/delta formatters, bucket math, palette round-trip), a synthetic-fixture render that asserts every store name + every status chip + every target percentage + inline-style count + no `<script>` / no `<img>` / no unrendered `{{}}` placeholders, plus a deterministic-render check (two renders byte-equal). Smoke-rendered to `/tmp/digest.html` from the same fixture: 21KB body. Full suite 268 passed + 6 db-gated skips.

### `[~]` 5.4 — Wednesday digest sender + GitHub Actions cron
- **Accomplishes:** Email digest goes out every Wednesday morning at 07:00 PT (06:00 PT during PDT). Idempotent — re-running for same week is a no-op.
- **Branch:** `task-5.4-digest-cron`
- **PR:**
- **Time:** 60 min
- **Notes:** Migration `015_digest_log.sql` creates `ops_digest_log` (PK `week_end_date`, `sent_at` default `now()`, `recipient_count`, `subject`). `subway_ops.digest.sender.send_email(*, to, subject, html, text, user, password)` wraps `smtplib.SMTP_SSL("smtp.gmail.com", 465)` and builds a `multipart/alternative` `EmailMessage` with `Bcc` for the recipient list so individual operators don't see each other's addresses. `scripts/send_weekly_digest.py` factored into pure `run_send_weekly_digest(...)` (every dependency injectable: refresh fns, recipients fetcher, log read/write, send) and a thin `main()` that wraps in `track_job("send_weekly_digest")`. Resolves `week_end` from `previous_business_week()` (overridable via `--week-end`); refreshes `mart_store_weekly.refresh(week_end)` + `mart_recon_weekly.refresh_for_week(week_end)` before sending so the body reflects fresh marts; on existing `ops_digest_log` row skips build+send (returns `status="already_sent"`); recipients = `ref_users` where `is_active=true AND role IN ('owner','field_manager')`; plain-text alternative is subject + dashboard URL + a "your client suppressed HTML" line. Outcome encoded in frozen `DigestResult(status, week_end, subject, recipient_count, sent_at)` — `status` is `sent` / `already_sent` / `no_recipients`. `.github/workflows/weekly_digest.yml` runs migrations + the script on cron `0 14 * * 3` plus `workflow_dispatch`; same `notify_failure.py` failure plumbing as `daily_pull.yml`. **DST drift accepted** (digest lands 06:00 PT PDT / 07:00 PT PST) — decisions.md entry dated 2026-05-13 spells out when to revisit (worker-based self-scheduler). 14 unit tests across `test_digest_sender.py` (5: header shape, multipart/alternative structure, empty-recipients rejection, SMTP login+send, missing-credential guard) and `test_send_weekly_digest.py` (9: happy path, already-sent short-circuit, no-recipients skip, mart refresh failure propagates, send failure does NOT write log, default week-end resolution, plain-text body coverage, format_summary paths). Migration applied to live Supabase (15/15 tracked). Full suite 282 passed + 6 db-gated skips.

---

## Phase 6 — University of Subway Pipeline

### `[~]` 6.1 — Gmail API setup + token + tests
- **Accomplishes:** Read-only OAuth access to Gmail inbox containing uOS emails. After this, system can list and read those emails programmatically.
- **Branch:** `task-6.1-gmail-api`
- **PR:**
- **Time:** 60 min
- **Notes:** Three new runtime deps (`google-api-python-client`, `google-auth-oauthlib`, `google-auth-httplib2`) plus mypy override for the four Google namespaces; `requirements.txt` regenerated (238 lines). `subway_ops.config.settings` extended with `gmail_token_json_b64` (env var of the same name). `src/subway_ops/uos/gmail_client.py` exposes `GmailClient` (search + get_message + get_attachment), `Message` / `Attachment` frozen dataclasses, and pure payload-flattening helpers (`_walk_parts`, `_decode_body`, `_header`, `message_from_payload`). Credentials load env-first via `_decode_token_b64` (the CI path) then `./token.json` (the local-dev path) — never both, so a stale CI token can't shadow a local file. `_refresh_if_needed` calls `creds.refresh(Request())` when expired, writes the refreshed JSON back only when we read it from disk, and raises with "re-run gmail_get_token.py" if no refresh token is present. The constructor accepts an injected `service=` so unit tests skip the network entirely. Scope is read-only (`gmail.readonly`). `scripts/gmail_get_token.py` runs the `InstalledAppFlow` against `~/.config/subway-ops/client_secret.json` (overridable via CLI arg) and writes `./token.json` with the `base64 -w0` next-step. `.gitignore` extended with `token.json`, `token.b64`, `client_secret*.json`. `docs/gmail_setup.md` walks through GCP project creation → API enable → OAuth consent (External, Testing mode, test user = the operator) → Desktop OAuth client → local token run → GitHub Actions secret. 23 unit tests in `tests/test_gmail_client.py` cover: case-insensitive header lookup, URL-safe base64 decode w/o padding, multipart walk leaves-only, full-payload round-trip incl. attachment metadata, single-part fallback, env→file credential precedence, refresh path with/without write-back, refresh-raise on missing refresh token, mock-`service` paginated search w/ max-results cap, get_message round-trip, get_attachment decoding, input-validation guards. Full suite 305 passed + 6 db-gated skips.

### `[~]` 6.2 — uOS email parser + ingest
- **Accomplishes:** Parses uOS training compliance email and lands per-employee, per-course rows in staging. Schema-flexible — courses change quarterly without schema changes.
- **Branch:** `task-6.2-uos-parser`
- **PR:**
- **Time:** 90 min
- **Notes:** Built **without** a real uOS `.eml` fixture (the playbook requested one but none was on disk). Implementation covers all three documented payload shapes so a real email can drop in with minimal calibration — see "Real-world calibration" below. Migration `016_uos.sql` creates `raw_uos_emails` (append-only JSONB envelope log, UNIQUE on `gmail_message_id`) + `stg_uos_compliance` (PK on `(restaurant_number, report_date, employee_name, course_name)`, CHECK constraint enforces `completion_status IN ('complete','overdue','pending')`). Two runtime deps added (`pypdf`, `beautifulsoup4`); `requirements.txt` regenerated (245 lines). `src/subway_ops/uos/parser.py` exposes `parse_csv` / `parse_html` / `parse_pdf` / `parse_email_payload` (CSV > PDF > HTML preference) and pure helpers: `normalise_status`, `parse_date`, `extract_store_number`, `_map_headers`. **Status normalisation** uses word-boundary regex matching with tier order overdue → complete → pending so "Past Due" → overdue (not "due" → pending) and "Incomplete" → pending (not "complete"). Header mapping is substring-based against tokens (`employee`/`store`/`course`/`status`/`completed`); banner rows are skipped by requiring 3+ field matches. `src/subway_ops/uos/ingest.py` defines `ingest_recent(days, *, client=None, query=None)`: searches `label:UoS newer_than:{days}d`, skips already-fetched `gmail_message_id`s, persists raw envelope, parses, filters rows to `ref_stores`, UPSERTs into `stg_uos_compliance`, captures unparsed rows in `ops_job_runs.metadata` (capped at 50 to keep the JSONB column readable). Wrapped in `track_job("ingest_uos")`. Returns frozen `IngestResult(messages_seen, messages_new, rows_written, rows_skipped_unknown_store, unparsed_rows)`. `scripts/uos_pull.py` is the thin entrypoint; `.github/workflows/uos_pull.yml` cron `0 11 * * *` (one hour after `daily_pull`) + `workflow_dispatch`, same `notify_failure` plumbing. **Real-world calibration:** drop a real uOS email into `tests/fixtures/uos/sample_report.eml` once available; the parser may need tweaks to (a) the `_HEADER_TOKENS` substring lists if uOS uses non-obvious column names, (b) `_STORE_NUMBER_RE` if franchise numbers don't fit the 3-5 digit window, (c) status synonyms if quarterly wording introduces new variants. 35 unit tests across `tests/test_uos_parser.py` (28 — status normalisation incl. "Incomplete" trap, date parsing, store-number extraction, header mapping, format detection, PDF row splitting, CSV round-trip from synthetic fixture with banner row + UTF-8 BOM, HTML largest-table heuristic, PDF parsing via monkey-patched `PdfReader`, payload-dispatch precedence) + `tests/test_uos_ingest.py` (7 — empty-search short-circuit, idempotent skip on already-fetched ids, store-FK filtering, no-payload graceful handling, RFC-2822 date parse, query override). Migration applied to live Supabase (16/16 tracked). Full suite 340 passed + 6 db-gated skips.

### `[~]` 6.3 — Compliance widget in dashboard
- **Accomplishes:** Training compliance % shows on owner overview, store detail, and weekly digest. Stores below 90% flagged.
- **Branch:** `task-6.3-compliance-widget`
- **PR:**
- **Time:** 45 min
- **Notes:** Compliance thresholds added to `dashboard/components/__init__.py` (`COMPLIANCE_GREEN_MIN=0.90`, `COMPLIANCE_YELLOW_MIN=0.80`) + bucket/emoji helpers (`compliance_bucket`, `compliance_emoji`) mirroring the food/labor traffic-light pattern. Three new `dashboard/data.py` helpers: `get_compliance_summary(report_date, store_filter)` (latest report on/before date per store via CTE; returns store#, name, latest_report_date, total/complete/overdue/pending cells, compliance_pct), `get_store_compliance_detail(store, report_date)` (per-employee, per-course detail), `get_store_compliance_trend(store, weeks)` (chronological % series for the Altair line chart). Empty `store_filter` tuple short-circuits to an empty frame so a misconfigured page doesn't accidentally query the whole portfolio. **Owner overview** (`pages/1_owner_overview.py`): `Training %` + `training_status` emoji columns merged into the grid via `_build_display_df(df, compliance)`; falls back to a nullable column when the compliance call returns empty so live data isn't required to render. **Store detail** (`pages/2_store_detail.py`): new "Training" tab — three `st.metric` cards (compliance %, overdue count, pending count), 13-week trend chart with the 90% target rule overlay (reuses the existing `_line_chart` helper so the visual matches food/labor charts), per-employee compliance table (complete / total / pct), overdue items table sorted by days-overdue desc, CSV download. Skips rendering with an info banner when there's no uOS data yet. **Digest builder** (`digest/builder.py`): new `ComplianceSummary` frozen dataclass + `DigestData.compliance` optional tuple (default empty); `_compliance_bucket()` mirrors the dashboard's threshold logic; `_render_compliance()` renders a single table after the per-store summary with red row tint (`background:#fef2f2`) on every sub-90% row and matching color-cell badge — empty `compliance` tuple → section is skipped per playbook. `_collect_digest_data` runs a fifth query joining `stg_uos_compliance` to `ref_stores` via a `latest`-per-store CTE; one extra DB round-trip on the weekly digest send isn't worth optimising. 14 new tests: 3 `test_dashboard_helpers.py` (threshold ordering, bucket on Decimal/float boundaries, emoji palette round-trip), 5 `test_digest_builder.py` (`_compliance_bucket` boundaries, every-bucket render coverage, red-tint count ≥ 2 for sub-90% rows, section-dropped contract when `compliance` is empty, section-placement-after-per-store). Full suite 348 passed + 6 db-gated skips. Smoke launched: `/`, `/owner_overview`, `/store_detail` all return HTTP 200.

---

## Phase 7 — Hardening & Operate

### `[~]` 7.1 — Test coverage pass + CI green
- **Accomplishes:** Every module tested; CI runs on every PR. Know within 2 minutes if any change breaks anything.
- **Branch:** `task-7.1-ci`
- **PR:**
- **Time:** 90 min
- **Notes:** Baseline coverage was **77%** before this task — already over the 75% playbook gate, but two non-Streamlit modules sat below 80%: `dashboard/auth.py` 62% (`_cookie_signing_key` fallback chain + DB helpers never exercised) and `db/connection.py` 69% (URL normaliser + no-URL raise + session helpers). New `tests/test_coverage_lifts.py` (15 tests) lifts both: cookie key tier resolution (secrets → env → dev default; treats empty secrets as missing), every `_normalize_url` branch (passthrough / `postgresql://` rewrite / `postgres://` rewrite / unknown-scheme fall-through), `get_engine` raise on missing DATABASE_URL, `make_authenticator` happy path + DB-load fallback, `lookup_user` hit/miss, `all_active_store_numbers` + `load_user_rows` exercised against a mocked engine (no live DB needed). After the lift: `dashboard/auth.py` 98%, `db/connection.py` 79%, **TOTAL 78.32%**. Streamlit page modules (21-43% coverage) deliberately stay below 80% — they're rendered by the Streamlit harness in production and smoke-tested via the headless launch in earlier task notes; unit-testing them in isolation pulls in too much fixture machinery for the value. `.github/workflows/ci.yml` runs ruff → mypy → `pytest --cov=src/subway_ops --cov-fail-under=75` on every PR and on push-to-main; `concurrency.cancel-in-progress: true` so newer pushes drop stale runs. README gets a CI badge pointing at the workflow (owner placeholder = `amitoj`, comment in markdown calls out the swap-when-remote-lands). Full suite 363 passed + 6 db-gated skips.

### `[~]` 7.2 — Observability: structured logs + ops_job_runs surfaced
- **Accomplishes:** When something breaks at 3am you can see what happened. Job history visible in dashboard.
- **Branch:** `task-7.2-observability`
- **PR:**
- **Time:** 60 min
- **Notes:** New `subway_ops/observability.py::configure_logging(*, force_json=None)` picks the renderer from `settings.app_env`: **prod → JSON one-event-per-line** (ISO-8601 UTC timestamp + level + event + bound context), **dev → console with colors off** (same shape, readable). The processor chain (`add_log_level`, `TimeStamper(fmt="iso", utc=True)`, `StackInfoRenderer`, `format_exc_info`) lands the contract keys before the renderer sees them. Every script that was calling `structlog.configure(processors=[structlog.dev.ConsoleRenderer()])` now calls `configure_logging()` instead: `migrate.py`, `daily_pull.py`, `uos_pull.py`, `refresh_marts.py`, `seed_reference.py`, `backfill.py`, `discovery.py`, `send_weekly_digest.py`. No stdlib logging calls remain; the leftover `print()` calls are either `__main__`-block DDL emitters (`controlsheet.py`, `wisr.py`) or script-output lines, both allowed by CLAUDE.md. New `dashboard/data.py` helpers: `recent_job_runs(limit, job_filter, status_filter)` (60-second cache TTL — tighter than the marts' 5 minutes because observability needs freshness; returns the 8 columns the page renders, with `duration_seconds` computed via `EXTRACT(EPOCH FROM (COALESCE(finished_at, now()) - started_at))` so running jobs show elapsed time too) and `distinct_job_names()` for the filter dropdown. New owner-check helper `dashboard/auth.is_owner(user_role)` mirrors the existing `ALL_STORE_ROLES` frozenset so the sidebar nav and page guard agree on the rule. **New page** `pages/5_system_status.py`: filter row (job multiselect + status multiselect) outside the auto-refresh fragment so widget state survives the tick; `st.fragment(run_every=60)` re-renders the grid only (sidebar + header stay stable); grid uses `st.dataframe` with `LinkColumn` for the **Re-run** column — `_rerun_url(job_name)` maps to a GitHub Actions workflow_dispatch URL via a static lookup (`daily_pull` → `daily_pull.yml`, `refresh_marts` → `refresh_marts.yml`, `send_weekly_digest` → `weekly_digest.yml`, `ingest_uos` → `uos_pull.yml`; one-off jobs like `backfill` / `discovery` return None so no misleading link is offered). Repo defaults to `amitoj/subway-ops`, overridable via `GITHUB_REPOSITORY` env or `github_repository` Streamlit secret. Defence in depth: `streamlit_app.py` only registers the page when `st.session_state.get("user_role") == "owner"`; the page's `main()` also re-checks and `st.error`s a typed-URL bypass attempt. **Tests**: `tests/test_observability.py` (7 — `force_json` round-trip via captured sink, console renderer is non-JSON, prod/dev defaults follow settings, idempotency on re-call), `tests/test_dashboard_auth.py` extended (+2: `is_owner` true on `owner`, false on anything else incl. `None`/empty), `tests/test_dashboard_system_status.py` (8 — `_format_duration` seconds/minutes/hours/None/non-numeric, `_status_chip` known + unknown statuses carry inline `background:`, `_rerun_url` known → workflow link, unknown → None, explicit-None workflow → None, `_gh_repo` env-var precedence + fallback). Smoke launch headless: all six pages (`/`, `/owner_overview`, `/store_detail`, `/field_manager`, `/reconciliation`, `/system_status`) return HTTP 200. Full suite 379 passed + 6 db-gated skips. Coverage 77.64%, CI gate satisfied.

### `[~]` 7.3 — Runbook for every recurring failure mode
- **Accomplishes:** `docs/runbook.md` covers 16 scenarios with symptom → cause → diagnosis → fix. Anyone can operate the system without re-deriving its design.
- **Branch:** `task-7.3-runbook`
- **PR:**
- **Time:** 60 min
- **Notes:** `docs/runbook.md` lands all 16 playbook scenarios with the four-line structure (symptom / cause / diagnosis / fix), each 50-150 words. Diagnosis commands use the actual module / column / job names from this codebase — every `ops_job_runs` query, every Pydantic exception type (`AuthError` / `RateLimitError` / `ServerError`), every script CLI (`scripts/backfill.py --status`, `scripts/gmail_get_token.py`, `scripts/discovery.py`). Cross-links to `gmail_setup.md`, deployment docs, and the **System status** page from Task 7.2 (one-click Re-run is the runbook's escape hatch for every "re-trigger via workflow_dispatch" instruction). `docs/operations_calendar.md` summarises every scheduled event: table of automated GHA workflows (daily_pull 10:00 UTC, uos_pull 11:00 UTC, refresh_marts every 4 h, weekly_digest Wed 14:00 UTC, CI on PR / push-to-main) with the PT wall-clock and DST drift called out; manual cadence table (monthly backfill check, quarterly audit, annual FreshConnect credential rotation, Gmail re-consent on uOS 401, Supabase backup verification, cold-start check, add/remove store/user); explicit "what an operator does each Wednesday / month / quarter" sections. **Verification**: three random scenarios (§4 daily-pull diagnosis query, §13 uOS unparsed_sample query, §15 quarterly course-count query) executed live against Supabase — every query ran cleanly; §13/§15 returned empty rowsets because uOS data isn't loaded yet, which is the expected pre-data state and confirms the SQL syntax is correct. Full suite untouched.

### `[~]` 7.4 — Backfill verification + audit reconciliation
- **Accomplishes:** Spot-check 12 months of history against LiveIQ's own reports. Catch any silent data gaps before declaring production-ready.
- **Branch:** `task-7.4-audit`
- **PR:**
- **Time:** 60 min code + hours of manual cross-checks
- **Notes:** `scripts/audit_backfill.py` is **read-only** and runs in `track_job("audit_backfill")` so each invocation lands in `ops_job_runs` + the system-status page. Factored into a pure `run_audit(...)` (every DB hop injectable for tests) + thin `main()` CLI with `--window-days` / `--sample-size` / `--out` / `--seed` flags. Three frozen dataclasses model the output: `SampleRow`, `CoverageReport` (with capped `missing_cells`), `AuditReport`. Coverage math is pure: `expected_daily_cells(stores, start, end)` and `expected_weekly_cells(...)` consume `(store_number, opening_date)` tuples — stores with no `opening_date` are assumed to have always existed (safer for gap discovery); stores with an `opening_date` only contribute days/Tuesdays on or after that date. `compute_coverage` returns the sorted missing set capped to `MAX_GAP_LIST=50`. `sample_pairs(pairs, n, rng=...)` is seedable so reruns are reproducible (the CLI's `--seed` flag pins the audit picks). `render_markdown` is split into `_render_header` / `_render_notes` / `_render_sample_section` / `_render_coverage_section` (parameterised so the daily and weekly sections share a single implementation; refactored after ruff PLR0912/PLR0915 complained at the original 75-statement single function). LiveIQ deep-links aren't deterministically constructable; the operator instead gets a navigation hint per row. Output lands at `docs/audit_<YYYY-MM-DD>.md`. `audit_backfill` added to the system-status page's workflow map (`None` — manual, no scheduled cron). 23 unit tests covering: opening-date clipping for daily + weekly, coverage gap sorting + cap, seeded sample reproducibility, every render branch (incl. empty-sample / clean-coverage / notes paths), and the orchestrator's empty-stores / empty-controlsheet / window-anchoring behaviour. **Live audit findings**: ran against Supabase with `--seed 42`; daily coverage **111 / 4,704** cells, weekly coverage **27 / 681** cells. Both deficits captured in `decisions.md` (entry dated 2026-05-13) as a legitimate operational finding — the 12-month backfill was only smoke-tested in Phase 3 (per the §3.4 task note); the full multi-day backfill is a manual step that must be run before declaring production-ready. Also caught and documented: the playbook's `net_sales_total` reference is stale — the actual `stg_controlsheet_weekly` column is `net_sales` (the wide-table generator drops the `_total` suffix on top-level weekly metrics). Audit script + rendered markdown reference the correct column. Full suite 402 passed + 6 db-gated skips; coverage 77.30%, CI gate satisfied. Lint + mypy green.

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
