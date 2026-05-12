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

### `[ ]` 0.3 — Reference data: stores, field managers, users
- **Accomplishes:** DB knows your 15 stores, who manages each, and who has dashboard access. Seed script reads from CSVs.
- **Branch:** `task-0.3-ref-tables`
- **PR:**
- **Time:** 45 min
- **Notes:**

### `[ ]` 0.4 — Business calendar helpers + tests
- **Accomplishes:** One module owns every date and week calculation. 02:00 day cutoff and Wed–Tue week as trustworthy primitives.
- **Branch:** `task-0.4-calendar`
- **PR:**
- **Time:** 30 min
- **Notes:**

### `[ ]` 0.5 — Database connection, migration runner, ops_job_runs
- **Accomplishes:** Idempotent SQL migrations from Python. First operational metadata table. Every job logs its outcome.
- **Branch:** `task-0.5-db-connection`
- **PR:**
- **Time:** 45 min
- **Notes:**

---

## Phase 1 — Fresh Connect Client

### `[ ]` 1.1 — FreshConnect HTTP client (auth, retry, rate-limit)
- **Accomplishes:** Single class for every HTTP call to Fresh Connect. Auth headers, exponential backoff on 5xx, specific exception types for each documented failure code, per-endpoint limit validation.
- **Branch:** `task-1.1-client`
- **PR:**
- **Time:** 60 min
- **Notes:**

### `[ ]` 1.2 — Pydantic models for all 13 endpoints
- **Accomplishes:** Every Fresh Connect response shape becomes a statically-typed Pydantic model. Schema drift fails loudly with `extra="forbid"`.
- **Branch:** `task-1.2-models`
- **PR:**
- **Time:** 90 min
- **Notes:**

### `[ ]` 1.3 — Discovery script + recorded fixtures
- **Accomplishes:** Hits every endpoint with your real credentials, saves response bodies as test fixtures, produces a field-coverage report. First real-world confirmation the API behaves as documented.
- **Branch:** `task-1.3-discovery`
- **PR:**
- **Time:** 60 min (+ wait time if rate-limited)
- **Notes:**

---

## Phase 2 — Ingestion Layer

### `[ ]` 2.1 — Schema + ingest: DailySalesSummary
- **Accomplishes:** Daily per-store totals flowing end-to-end. Sets the pattern every other ingest follows.
- **Branch:** `task-2.1-daily-sales`
- **PR:**
- **Time:** 60 min
- **Notes:**

### `[ ]` 2.2 — Schema + ingest: ControlSheet (weekly)
- **Accomplishes:** The richest endpoint — weekly cash control, sales itemization, bread, labor — flattened into one wide table (~120 columns). Foundation for both the weekly mart and the entire reconciliation flow.
- **Branch:** `task-2.2-controlsheet`
- **PR:**
- **Time:** 90 min
- **Notes:**

### `[ ]` 2.3 — Schema + ingest: PaidOutsAndNoSales (cash drops)
- **Accomplishes:** Every POS-recorded cash drop event lands in staging. Combined with ControlSheet's `depositInBank`, this is the data backbone of reconciliation.
- **Branch:** `task-2.3-paidouts`
- **PR:**
- **Time:** 60 min
- **Notes:**

### `[ ]` 2.4 — Schema + ingest: InventoryMovement
- **Accomplishes:** Daily per-item inventory deltas (deliveries, transfers, waste) flow into staging.
- **Branch:** `task-2.4-inventory`
- **PR:**
- **Time:** 60 min
- **Notes:**

### `[ ]` 2.5 — Schema + ingest: Wisr (weekly WISR)
- **Accomplishes:** Subway's gold-standard weekly food-cost analysis lands in staging. Drives food-cost variance KPIs in `mart_store_weekly`.
- **Branch:** `task-2.5-wisr`
- **PR:**
- **Time:** 90 min
- **Notes:**

### `[ ]` 2.6 — Schema + ingest: DailyTimeclock + ThirdPartyDailySalesSummary
- **Accomplishes:** Last two daily-grain endpoints. Timeclock fills labor detail; third-party fills delivery channel breakdown.
- **Branch:** `task-2.6-timeclock-3p`
- **PR:**
- **Time:** 60 min
- **Notes:**

### `[ ]` 2.7 — Daily orchestrator + GitHub Actions cron
- **Accomplishes:** Single `daily_pull.py` runs all six ingests with right windows. GitHub Actions fires it every morning at 03:00 PT. System is now ingesting automatically.
- **Branch:** `task-2.7-orchestrator`
- **PR:**
- **Time:** 60 min
- **Notes:**

---

## Phase 3 — Marts & Backfill

### `[ ]` 3.1 — `mart_store_daily`
- **Accomplishes:** One row per store per business date with every daily-grain KPI computed. Powers dashboard "current week" views and 30-day trends.
- **Branch:** `task-3.1-mart-daily`
- **PR:**
- **Time:** 60 min
- **Notes:**

### `[ ]` 3.2 — `mart_store_weekly`
- **Accomplishes:** One row per store per Tuesday week-end, blending ControlSheet, Wisr, daily rollups. KPIs flagged against 22%/28% store-level targets.
- **Branch:** `task-3.2-mart-weekly`
- **PR:**
- **Time:** 60 min
- **Notes:**

### `[ ]` 3.3 — `mart_field_manager_portfolio`
- **Accomplishes:** Rollup to FM level with sales-weighted KPIs vs portfolio targets (20%/25%).
- **Branch:** `task-3.3-mart-fm`
- **PR:**
- **Time:** 45 min
- **Notes:**

### `[ ]` 3.4 — 12-month backfill script
- **Accomplishes:** Loads 12 months of history. Respects rate limits. Fully resumable via `ops_backfill_progress`. Refreshes marts at the end.
- **Branch:** `task-3.4-backfill`
- **PR:**
- **Time:** 90 min code + days of wall-clock for full run
- **Notes:**

### `[ ]` 3.5 — Mart refresh job + schedule
- **Accomplishes:** Marts stay current throughout the day without manual intervention. Dashboard never more than 4 hours stale.
- **Branch:** `task-3.5-refresh-cron`
- **PR:**
- **Time:** 30 min
- **Notes:**

---

## Phase 4 — Dashboard

### `[ ]` 4.1 — Streamlit app skeleton + authentication
- **Accomplishes:** Multipage Streamlit app with login. Role-based store visibility (owner sees all 15; FMs see their cluster).
- **Branch:** `task-4.1-streamlit-skeleton`
- **PR:**
- **Time:** 60 min
- **Notes:**

### `[ ]` 4.2 — Owner overview page (15-store grid)
- **Accomplishes:** At-a-glance view of all 15 stores. Sortable, color-coded grid plus 13-week trend chart.
- **Branch:** `task-4.2-owner-overview`
- **PR:**
- **Time:** 90 min
- **Notes:**

### `[ ]` 4.3 — Store detail drill-down page
- **Accomplishes:** Single store's full picture across four tabs: daily trend, weekly history, WISR inventory detail, cash drops.
- **Branch:** `task-4.3-store-detail`
- **PR:**
- **Time:** 90 min
- **Notes:**

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
