# Subway Operations System — Build Playbook

> The complete reference and build guide for a unified operations system
> covering 15 Subway franchise locations, built in Python on a fully-free
> stack, with Claude Code as the construction agent.
>
> This is the canonical document. Everything you need is here: architecture,
> conventions, the 37 chronological tasks with full Claude Code prompts,
> environment configuration, common pitfalls, and the glossary.
>
> **Owner:** Bir Amitoj Singh Bhullar
> **Build assistant:** Claude Code
> **Target:** Personally owned by the operator; runs cheap; legible to anyone
> who picks it up in 2027.
>
> **Companion file:** `SUBWAY_OPS_TASKS.md` — a slim checklist for tracking
> task completion while you build. Use it to mark progress; come here for the
> actual prompts and rationale.

---

## Table of Contents

### Part I — Reference
1. [Project Overview](#1-project-overview)
2. [Architecture Summary](#2-architecture-summary)
3. [Stack & Cost Profile](#3-stack--cost-profile)
4. [Naming & Convention System](#4-naming--convention-system)
5. [Business Calendar Rules](#5-business-calendar-rules)
6. [Data Model — End-State View](#6-data-model--end-state-view)
7. [Day-Zero Pre-Flight Checklist](#7-day-zero-pre-flight-checklist)
8. [How to Use This Playbook](#8-how-to-use-this-playbook)
9. [Task Index (Chronological)](#9-task-index-chronological)

### Part II — Tasks
- **Phase 0 — Foundation** (Tasks 0.1 – 0.5)
- **Phase 1 — Fresh Connect Client** (Tasks 1.1 – 1.3)
- **Phase 2 — Ingestion Layer** (Tasks 2.1 – 2.7)
- **Phase 3 — Marts & Backfill** (Tasks 3.1 – 3.5)
- **Phase 4 — Dashboard** (Tasks 4.1 – 4.6)
- **Phase 5 — Reconciliation & Weekly Digest** (Tasks 5.1 – 5.4)
- **Phase 6 — University of Subway Pipeline** (Tasks 6.1 – 6.3)
- **Phase 7 — Hardening & Operate** (Tasks 7.1 – 7.4)

### Part III — Appendices
- [Appendix A — `CLAUDE.md` (full text)](#appendix-a--claudemd-full-text)
- [Appendix B — Environment Variables](#appendix-b--environment-variables)
- [Appendix C — Common Pitfalls](#appendix-c--common-pitfalls)
- [Appendix D — Hosting Alternatives](#appendix-d--hosting-alternatives)
- [Appendix E — Glossary](#appendix-e--glossary)

---

---

# PART I — REFERENCE

---

## 1. Project Overview

This system is the operational instrumentation layer for a 15-store Subway
franchise operation across Washington and Oregon. It ingests data from
Subway's Fresh Connect API (LiveIQ), parses University of Subway compliance
emails, and presents unified dashboards plus a weekly variance digest to the
operator and three field managers.

**What it replaces:**
- A 6-tab, ~8,100-formula reconciliation workbook
- Manual logins across LiveIQ, SubVentory, and email reports
- Eyeball-driven KPI tracking against franchise targets

**What it produces:**
- A 12-month rolling warehouse of every store's daily and weekly performance
- A reconciliation register flagging cash-deposit variance per store per week
- A Wednesday-morning email digest of the prior business week (Wed–Tue)
- A multi-user dashboard with owner and field-manager views
- A defensible, auditable data history of the operation

**What it explicitly does NOT do (Phase 1):**
- Replace the POS (LiveIQ remains the source of truth)
- Ingest bank-issued deposit confirmations (variance flagged manually only)
- Replace SubVentory (skipped pending parity check against Fresh Connect)
- Forecast, predict, or recommend — only report

---

## 2. Architecture Summary

```
┌─ Inputs ───────────────────────────────────────────────────────────────┐
│                                                                         │
│   Fresh Connect API ◄──── api-client + api-key (HTTP headers)          │
│   Gmail inbox      ◄──── University of Subway emails                   │
│   Dashboard form   ◄──── Variance entries when over/short              │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─ Compute ──────────────────────────────────────────────────────────────┐
│                                                                         │
│   GitHub Actions (free cron):                                          │
│     daily_pull.yml      — 03:00 PT daily, pulls FreshConnect           │
│     refresh_marts.yml   — every 4 hours, rebuilds marts                │
│     weekly_digest.yml   — 07:00 PT Wednesday, builds + sends digest    │
│     uos_pull.yml        — 04:00 PT daily, reads Gmail                  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─ Storage ──────────────────────────────────────────────────────────────┐
│                                                                         │
│   Supabase Postgres (free tier, 500MB):                                │
│                                                                         │
│     raw_*    ← untouched API payloads (JSONB)                          │
│     stg_*    ← typed, flattened, deduplicated                          │
│     mart_*   ← denormalized, dashboard-ready                           │
│     ref_*    ← reference data (stores, field managers, users)          │
│     ops_*    ← operational metadata (job_runs, audit, variances)       │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─ Output ───────────────────────────────────────────────────────────────┐
│                                                                         │
│   Streamlit Cloud (free):                                              │
│     - Owner overview (all 15 stores)                                   │
│     - Field manager view (cluster)                                     │
│     - Store detail drill-down                                          │
│     - Weekly reconciliation review                                     │
│                                                                         │
│   Gmail SMTP (free): Wednesday digest email                            │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**Data flow principle.** Every external byte lands first in `raw_*` with its
original payload preserved as JSONB. The `stg_*` and `mart_*` tables are
derivations. A parser change, schema change, or downstream bug never costs
us source data — we just re-run the transformation.

**Idempotency principle.** Every ingest is keyed on a natural composite key
so re-running the same pull never duplicates rows. Re-running is the default
recovery path.

**Single-tenant principle.** The system is built for one operator (15 stores,
one franchise group). Multi-tenancy is explicitly out of scope. If the model
is ever applied to another operation, it's a fork, not a tenant.

---

## 3. Stack & Cost Profile

| Component | Choice | Cost | Why this choice |
|---|---|---|---|
| Language | Python 3.12 | Free | Operator preference; mature data stack |
| Package manager | `uv` | Free | Faster than pip/poetry; great with Claude Code |
| HTTP client | `httpx` | Free | Sync + async; better timeout/retry primitives than requests |
| Retry/backoff | `tenacity` | Free | Declarative retries with jitter |
| Data validation | `pydantic` v2 | Free | Catches API schema drift at parse time |
| Database | Supabase Postgres | Free (500 MB) | Hosted Postgres without ops burden |
| DB driver | `psycopg[binary]` 3.x | Free | Modern Postgres driver |
| Migrations | Plain SQL files | Free | Simpler than Alembic for one operator |
| Data transforms | `pandas` 2.x + `pyarrow` | Free | Standard; well-known to Claude Code |
| Dashboard | `streamlit` 1.x | Free | One Python file = working web app |
| Auth | `streamlit-authenticator` | Free | YAML-based, sufficient for 5 users |
| Charts | `altair` (preferred) or `plotly` | Free | Altair is declarative + small payload |
| Job scheduler | GitHub Actions cron | Free (2,000 min/mo private) | No infra; secrets included |
| Email out | Gmail SMTP via `smtplib` | Free | Operator already has Workspace |
| Email in (uOS) | Gmail API via `google-api-python-client` | Free | OAuth refresh handled cleanly |
| Hosting (app) | Streamlit Community Cloud | Free | Direct GitHub deploy |
| Secrets | GitHub Actions secrets + Streamlit secrets | Free | Built-in |
| Testing | `pytest` + `pytest-mock` + `responses` | Free | Fixture-based against recorded API responses |
| Lint/format | `ruff` | Free | One tool, fast, well-supported |
| Type check | `mypy` (strict on `src/`) | Free | Catches Pydantic mismatches early |
| Structured logs | `structlog` | Free | JSON in prod, pretty in dev |

**Estimated total monthly cost: $0.**

Upgrade paths (only if the system outgrows free tiers):
- Supabase Pro: $25/month → 8 GB Postgres, no inactivity pause.
- Fly.io VM: $5/month → private dashboard hosting if Streamlit Cloud's
  public-URL posture becomes a problem. See Appendix D.

GitHub Actions free tier note: 2,000 minutes/month on private repos. Our
total scheduled job time is roughly 150 minutes/month (daily_pull ~5 min
× 30 days = 150; weekly digest negligible; mart refresh negligible). Fits
comfortably with headroom for debugging and backfill runs.

---

## 4. Naming & Convention System

These conventions are encoded in `CLAUDE.md` (Appendix A). Claude Code is
instructed to enforce them on every change.

**Table prefixes** (also serve as directory names in `src/`):

| Prefix | Meaning | Mutability |
|---|---|---|
| `raw_` | Untouched external payloads | Append-only |
| `stg_` | Typed, cleaned, deduplicated | Re-derivable from raw |
| `mart_` | Denormalized, dashboard-ready | Re-derivable from stg |
| `ref_` | Reference / dimension data | Hand-edited or seeded |
| `ops_` | System-internal (jobs, audit, etc.) | App-managed |

**Column conventions:**
- All timestamps stored as `TIMESTAMP WITH TIME ZONE` in UTC.
- All dates in `business_date` columns = Subway business date (02:00–01:59 local).
- All money in `NUMERIC(12, 4)` to avoid float drift on percentages.
- Boolean columns named `is_*` (e.g. `is_reconciled`).
- Foreign keys named `<table>_id` even when referring to a string PK
  (e.g. `store_number` is the PK of `ref_stores`; FK columns named
  `store_number`).

**Python conventions:**
- One module = one endpoint or one mart.
- Pydantic models live in `freshconnect/models.py`, mirroring API responses
  field-for-field with `model_config = ConfigDict(populate_by_name=True,
  extra="forbid")`.
- All DB writes go through one upsert helper that takes
  `(table, rows, key_cols)`.
- Logs structured: `logger.info("event", extra={"store": s, "rows": n})`.
- No `print()` outside `__main__` blocks in scripts.

---

## 5. Business Calendar Rules

These rules are encoded in `src/subway_ops/calendar.py` and referenced
everywhere. The four-line decision tree:

1. **Business day** runs 02:00 local → 01:59 next-calendar-day local.
2. **Business week** runs Wednesday business-day 00:00 (02:00 wall clock)
   through Tuesday business-day 23:59 (01:59 wall clock next Wednesday).
3. The API's `date` field on daily endpoints is **already business-date**.
   Trust it. Do not re-derive.
4. The API's `weekEndDate` parameter and field is **always a Tuesday**.
   Trust it. Do not re-derive.

**Helper functions** (built in Task 0.4, used everywhere after):
- `business_week_of(d: date) -> tuple[date, date]` → `(Wed_start, Tue_end)`
- `previous_business_week() -> tuple[date, date]` → for digests
- `business_date_now(tz: str) -> date` → current business date right now
- `dt_to_business_date(dt: datetime) -> date` → convert a wall-clock
  timestamp to its Subway business date

**Timezone**: All 15 stores are in WA and OR — single TZ
`America/Los_Angeles`. The system assumes this. If a future store is in a
different TZ, this becomes per-store. Defer that until needed.

**DST and cron**: Cron schedules are in UTC. The 14:00 UTC Wednesday digest
arrives at 07:00 PT during Pacific Standard Time (Nov–Mar) and 06:00 PT
during Pacific Daylight Time (Mar–Nov). This drift is acceptable; documented
in Appendix C.

---

## 6. Data Model — End-State View

When all 37 tasks are complete, the database contains roughly the following
tables. This is the target shape — Phase 2 builds the staging layer, Phase 3
builds the marts, Phase 5 builds the recon mart.

**Reference (`ref_`)**
- `ref_stores` — 15 rows, one per store. Includes `field_manager_name` FK.
- `ref_field_managers` — 3+ rows (Maria, James, Kevin).
- `ref_users` — 5 rows (owner, mentor, 3 FMs) with bcrypt password hashes.

**Operational (`ops_`)**
- `ops_migrations` — applied SQL migration filenames + checksums.
- `ops_job_runs` — every scheduled job's start/finish/status/rows/error.
- `ops_backfill_progress` — resumable backfill window tracking.
- `ops_variance_entries` — operator-entered actual-bank-deposit values when
  POS deposit doesn't match.
- `ops_digest_log` — one row per Wednesday digest sent.

**Raw (`raw_`)** — append-only JSONB payloads from each FreshConnect endpoint
plus uOS email envelopes. Roughly 11 tables (one per ingested endpoint plus
`raw_uos_emails`).

**Staging (`stg_`)**:
- `stg_daily_sales` — one row per store per business date.
- `stg_controlsheet_weekly` — one row per store per week_end_date, ~120
  columns wide (day-of-week dicts flattened).
- `stg_no_sales` / `stg_paid_outs` — per-event rows.
- `stg_cash_drops` — VIEW filtering `stg_no_sales` to cash drops only.
- `stg_inventory_movement` — per store, business date, inventory item.
- `stg_inventory_movement_totals` — daily UNITS COST totals.
- `stg_wisr_weekly` — per store, week_end_date, ~80 columns.
- `stg_wisr_inventory_items` — per store, week, item.
- `stg_3p_daily` and `stg_3p_daily_provider` — third-party daily.
- `stg_timeclock` — per shift entry.
- `stg_uos_compliance` — per store, report_date, employee, course.

**Marts (`mart_`)**:
- `mart_store_daily` — one row per store per business date with derived
  daily KPIs.
- `mart_store_weekly` — per store per Tuesday week-end with weekly KPIs
  including food cost % vs target and labor cost % vs target.
- `mart_field_manager_portfolio` — per FM per week, sales-weighted rollup.
- `mart_recon_weekly` — per store per week, POS deposit vs actual deposit
  vs computed status (clean/flagged/escalated/unverified).

Total table count: ~32. Total storage at 15 stores × 12 months ≈ 100–200 MB,
well within Supabase's 500 MB free tier.

---

## 7. Day-Zero Pre-Flight Checklist

Complete these manually before Task 0.1. Estimated time: 60–90 minutes.

- [ ] **Generate Fresh Connect credentials.** In LiveIQ → Reporting →
      FreshConnect → follow the on-screen instructions. Record the
      `api-client` and `api-key`. **Note**: Generating a new key invalidates
      any previous one, so coordinate with anyone else (mentor / IT) who
      might be using it.
- [ ] **Inventory your 15 stores.** Build a CSV with columns:
      `store_number, store_name, city, state, field_manager_name, timezone,
      opening_date_estimate`. Save as `seed/stores.csv` (committed in Task 0.3).
- [ ] **Inventory your field managers.** A CSV with columns:
      `field_manager_name, email, store_numbers_csv, role`. Save as
      `seed/field_managers.csv`.
- [ ] **Create GitHub account / org** for the project. Create a **private**
      repository named `subway-ops`.
- [ ] **Create Supabase project.** Sign up at supabase.com, create a new
      project (region: us-west-1, closest to WA/OR). Record:
      - Project URL
      - Database password (strong; store in password manager)
      - Service role key (what GitHub Actions will use)
- [ ] **Decide on dashboard users.** Five emails: you, mentor, Maria, James,
      Kevin.
- [ ] **Designate a Gmail inbox for uOS reports.** Either:
      - Use your existing inbox (apply a Gmail filter / label "UoS").
      - Or create `subway-uos@yourdomain.com` and forward UoS emails there.
- [ ] **Create a Gmail App Password** for SMTP (2FA must be on). Google
      account → Security → App passwords → "Subway Ops Email". Record it.
- [ ] **Install local dev tools:**
      - Python 3.12 (via `uv python install 3.12`)
      - `uv` (https://docs.astral.sh/uv/)
      - `git`
      - VS Code or your editor of choice
      - Claude Code

Once all boxes are checked, proceed to Task 0.1.

---

## 8. How to Use This Playbook

The playbook contains **37 tasks** organized into **8 phases**. Each task is
designed to be a single, contained Claude Code session.

For each task you'll find:

- **What this accomplishes** — the outcome in operational terms.
- **Inputs / Prerequisites** — files or state that should already exist.
- **Acceptance criteria** — checkable boxes for completion.
- **Prompt for Claude Code** — the literal prompt to paste into Claude Code.
- **Verification** — commands to confirm it actually worked.
- **Estimated session time** — how long this should take.

**The workflow per task:**

1. Make sure you're on a fresh branch: `git checkout -b task-X.Y-short-name`.
2. Open Claude Code in the repo.
3. Paste the prompt verbatim.
4. Review what Claude Code produces; iterate until acceptance criteria are met.
5. Run the verification.
6. Commit, open PR, merge to main.
7. Move to the next task.

**One task per branch, one PR per task.** Non-negotiable for keeping the
git history navigable when you're debugging in 2027.

**Do not skip tasks.** Each builds on the prior. If you must skip, write the
reason in `decisions.md` (Task 0.1 creates this file).

**Track progress in `SUBWAY_OPS_TASKS.md`** — the slim companion file with
checkboxes per task. Mark `[~]` when in progress, `[x]` when done. Add PR
links and notes in the spaces provided.

---

## 9. Task Index (Chronological)

| # | Task | Phase | Est. time |
|---|---|---|---|
| 0.1 | Initialize repo, project structure, pyproject | Foundation | 30 min |
| 0.2 | Write CLAUDE.md and decisions.md | Foundation | 20 min |
| 0.3 | Reference data: stores, field managers, users | Foundation | 45 min |
| 0.4 | Business calendar helpers + tests | Foundation | 30 min |
| 0.5 | Database connection, migration runner, ops_job_runs | Foundation | 45 min |
| 1.1 | FreshConnect HTTP client (auth, retry, rate-limit) | API Client | 60 min |
| 1.2 | Pydantic models for all 13 endpoints | API Client | 90 min |
| 1.3 | Discovery script + recorded fixtures | API Client | 60 min |
| 2.1 | Schema + ingest: DailySalesSummary | Ingestion | 60 min |
| 2.2 | Schema + ingest: ControlSheet (weekly) | Ingestion | 90 min |
| 2.3 | Schema + ingest: PaidOutsAndNoSales (cash drops) | Ingestion | 60 min |
| 2.4 | Schema + ingest: InventoryMovement | Ingestion | 60 min |
| 2.5 | Schema + ingest: Wisr (weekly WISR) | Ingestion | 90 min |
| 2.6 | Schema + ingest: DailyTimeclock, ThirdPartyDailySalesSummary | Ingestion | 60 min |
| 2.7 | Daily orchestrator + GitHub Actions cron | Ingestion | 60 min |
| 3.1 | mart_store_daily | Marts | 60 min |
| 3.2 | mart_store_weekly | Marts | 60 min |
| 3.3 | mart_field_manager_portfolio | Marts | 45 min |
| 3.4 | 12-month backfill script | Marts | 90 min |
| 3.5 | Mart refresh job + schedule | Marts | 30 min |
| 4.1 | Streamlit app skeleton + authentication | Dashboard | 60 min |
| 4.2 | Owner overview page (15-store grid) | Dashboard | 90 min |
| 4.3 | Store detail drill-down page | Dashboard | 90 min |
| 4.4 | Field manager portfolio page | Dashboard | 60 min |
| 4.5 | Deploy to Streamlit Cloud (or Fly.io) | Dashboard | 30 min |
| 4.6 | Polish: filters, exports, KPI thresholds | Dashboard | 60 min |
| 5.1 | mart_recon_weekly + ops_variance table | Recon | 75 min |
| 5.2 | Reconciliation review page (variance entry) | Recon | 90 min |
| 5.3 | Weekly digest builder (HTML email body) | Recon | 90 min |
| 5.4 | Wednesday digest sender + GitHub Actions cron | Recon | 60 min |
| 6.1 | Gmail API setup + token + tests | uOS | 60 min |
| 6.2 | uOS email parser + ingest | uOS | 90 min |
| 6.3 | Compliance widget in dashboard | uOS | 45 min |
| 7.1 | Test coverage pass + CI green | Hardening | 90 min |
| 7.2 | Observability: structured logs + ops_job_runs surfaced | Hardening | 60 min |
| 7.3 | Runbook for every recurring failure mode | Hardening | 60 min |
| 7.4 | Backfill verification + audit reconciliation | Hardening | 60 min |

**Total estimated time: ~37.5 hours of focused Claude Code work.** At 8
hours/week, that's ~5 weeks of build time. With reviewing, debugging, and
real-world tuning, plan for 8–12 calendar weeks.

---

---

# PART II — TASKS

---

# Phase 0 — Foundation

The goal of Phase 0 is to make Claude Code productive. Every minute spent
on conventions here saves an hour of correction later.

---

## Task 0.1 — Initialize repo, project structure, pyproject

**What this accomplishes:** A scaffolded Python project that every later
task assumes exists. Sets the directory structure, dependencies, lint/type
config, and `pyproject.toml`. After this task you can run `uv sync`, `ruff`,
`mypy`, and `pytest` with no errors — but no business logic exists yet.

**Inputs / Prerequisites:** Day-Zero checklist complete. GitHub repo created.
Both markdown files (`SUBWAY_OPS_BUILD_PLAYBOOK.md` and `SUBWAY_OPS_TASKS.md`)
already present at repo root.

**Acceptance criteria:**
- [ ] Directory tree matches the structure in the prompt.
- [ ] `uv sync` installs all base dependencies cleanly.
- [ ] `ruff check .` and `mypy src/` both run with zero errors on the skeleton.
- [ ] `pytest` runs with zero tests collected and zero errors.
- [ ] `.gitignore` excludes `.env`, `.venv`, `__pycache__`, `.pytest_cache`,
      `.ruff_cache`, `.mypy_cache`, `secrets.toml`, `tests/fixtures/recorded/`.
- [ ] First commit on `main` with these files in place.

**Prompt for Claude Code:**

```text
Initialize a Python 3.12 project for a Subway franchise operations system.
Use `uv` for package management.

Create this directory structure exactly:

subway-ops/
├── pyproject.toml
├── .python-version          # contains: 3.12
├── .gitignore
├── README.md                # short, points to SUBWAY_OPS_BUILD_PLAYBOOK.md
├── CLAUDE.md                # placeholder — Task 0.2 will fill it
├── decisions.md             # placeholder — log of architectural decisions
├── SUBWAY_OPS_BUILD_PLAYBOOK.md   # already present, do not touch
├── SUBWAY_OPS_TASKS.md             # already present, do not touch
├── seed/
│   ├── stores.csv           # placeholder
│   └── field_managers.csv   # placeholder
├── src/subway_ops/
│   ├── __init__.py
│   ├── config.py            # pydantic-settings (Task 0.5 populates)
│   ├── calendar.py          # business calendar (Task 0.4 populates)
│   ├── db/
│   │   ├── __init__.py
│   │   ├── connection.py    # Task 0.5
│   │   └── migrations/
│   ├── freshconnect/
│   │   ├── __init__.py
│   │   ├── client.py        # Task 1.1
│   │   └── models.py        # Task 1.2
│   ├── ingest/              # one module per endpoint, populated Phase 2
│   │   └── __init__.py
│   ├── transform/           # one module per mart, populated Phase 3
│   │   └── __init__.py
│   ├── uos/                 # Phase 6
│   │   └── __init__.py
│   ├── digest/              # Phase 5
│   │   └── __init__.py
│   └── dashboard/
│       ├── __init__.py
│       └── app.py           # Phase 4
├── scripts/
│   ├── discovery.py         # Task 1.3
│   └── backfill.py          # Task 3.4
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   └── fixtures/
│       └── recorded/        # gitignored
└── .github/workflows/       # populated in Phase 2 and Phase 5

In `pyproject.toml`, configure:

- Project name: `subway-ops`, version `0.1.0`, requires-python `>=3.12,<3.13`.
- Dependencies: httpx, tenacity, pydantic>=2.5, pydantic-settings,
  psycopg[binary]>=3.1, sqlalchemy>=2, pandas>=2.2, pyarrow, python-dateutil,
  pytz, structlog.
- Dev dependencies: pytest, pytest-mock, pytest-cov, responses, ruff, mypy,
  types-python-dateutil, types-pytz.
- Ruff config: line-length 100, target-version py312, select E, F, I, B, UP,
  N, SIM, PL, RUF; ignore PLR0913 (too-many-args) and PLR2004 (magic numbers).
- Mypy config: strict on src/subway_ops/; ignore_missing_imports for
  pandas.*, pyarrow.*, streamlit.*.
- Pytest config: testpaths "tests", addopts "--strict-markers -ra".

Write a `.gitignore` covering Python, pytest, ruff, mypy, venv, .env,
secrets.toml, and tests/fixtures/recorded/.

Write a minimal README.md that points to SUBWAY_OPS_BUILD_PLAYBOOK.md and
SUBWAY_OPS_TASKS.md, and lists the quick-start commands (uv sync, ruff
check, mypy, pytest).

Create CLAUDE.md and decisions.md as empty placeholders with a one-line note
"Populated in Task 0.2".

Do not write any business logic yet. Skeleton only.
```

**Verification:**
```bash
uv sync
uv run ruff check .
uv run mypy src/
uv run pytest
git status                  # confirm nothing tracked that shouldn't be
git add -A && git commit -m "Task 0.1: project skeleton"
```

**Estimated session time:** 30 min.

---

## Task 0.2 — Write CLAUDE.md and decisions.md

**What this accomplishes:** Encodes the conventions, stack, and rules so
every future Claude Code session starts informed. After this, you never have
to re-explain "we use Decimal not float" or "table prefixes mean X".

**Inputs / Prerequisites:** Task 0.1 complete.

**Acceptance criteria:**
- [ ] `CLAUDE.md` contains the full text from Appendix A of this playbook.
- [ ] `decisions.md` contains the first three foundational entries.

**Prompt for Claude Code:**

```text
Replace CLAUDE.md with the literal contents of "Appendix A — CLAUDE.md
(full text)" from SUBWAY_OPS_BUILD_PLAYBOOK.md in the repo root. Copy the
markdown verbatim, including the fenced code blocks.

Replace decisions.md with a markdown table-of-decisions document. Format
each decision as:

## YYYY-MM-DD — Decision title

**Context:** ...
**Decision:** ...
**Consequences:** ...

Add these three entries dated today:

1. Language and stack — Decision: Python 3.12, Streamlit, Supabase Postgres,
   GitHub Actions for orchestration. Context: operator preference for Python;
   need free-tier-only hosting; need declarative dashboards. Consequences:
   locked into Python ecosystem; Streamlit's auth limitations accepted;
   daily-batch architecture rather than real-time.

2. Business calendar — Decision: Business day is 02:00–01:59 local
   (America/Los_Angeles for all 15 stores). Business week is Wednesday
   through Tuesday. The Fresh Connect API's `date` field is already
   business-date-aligned and its `weekEndDate` is always a Tuesday; both
   are trusted and not re-derived.

3. Bank reconciliation model — Decision: We do not ingest bank-issued
   deposit confirmations. The dashboard surfaces the POS-recorded
   `depositInBank` from ControlSheet. A variance entry form exists for
   operators to record actual bank-deposited amounts only when they differ
   from the POS-recorded amount. Context: 15 stores deposit to multiple
   banks; building per-bank CSV parsers exceeds the value of the variance
   signal. Consequences: we catch over/short via human-in-the-loop, not
   automation. Acceptable for v1; revisit if variance frequency grows.

Do not modify any other file.
```

**Verification:**
```bash
cat CLAUDE.md | head -40       # confirm it filled in
cat decisions.md               # confirm three entries
git add -A && git commit -m "Task 0.2: CLAUDE.md and decisions.md"
```

**Estimated session time:** 20 min.

---

## Task 0.3 — Reference data: stores, field managers, users

**What this accomplishes:** Creates the three reference tables — stores,
field managers, users — and a seed script that populates them from the CSVs
you prepared in Day-Zero. After this, the database knows what your 15 stores
are, who manages each one, and who has dashboard access.

**Inputs / Prerequisites:** Tasks 0.1 and 0.2 complete. `seed/stores.csv` and
`seed/field_managers.csv` already populated with real data.

**Acceptance criteria:**
- [ ] SQL migration `001_ref_tables.sql` creates the three tables.
- [ ] `scripts/seed_reference.py` reads the CSVs and populates Postgres.
- [ ] Re-running the seed is idempotent (upsert behavior).
- [ ] `tests/test_reference_data.py` confirms 15 stores load.

**Prompt for Claude Code:**

```text
Create the first SQL migration file
src/subway_ops/db/migrations/001_ref_tables.sql with three tables:

ref_stores
- store_number TEXT PRIMARY KEY  (matches FreshConnect restaurant numbers)
- store_name TEXT NOT NULL
- city TEXT NOT NULL
- state CHAR(2) NOT NULL CHECK (state IN ('WA', 'OR'))
- timezone TEXT NOT NULL DEFAULT 'America/Los_Angeles'
- field_manager_name TEXT REFERENCES ref_field_managers(name)
- opening_date DATE
- is_active BOOLEAN NOT NULL DEFAULT true
- created_at TIMESTAMPTZ NOT NULL DEFAULT now()
- updated_at TIMESTAMPTZ NOT NULL DEFAULT now()

ref_field_managers
- name TEXT PRIMARY KEY
- email TEXT NOT NULL UNIQUE
- phone TEXT
- is_active BOOLEAN NOT NULL DEFAULT true

ref_users
- email TEXT PRIMARY KEY
- display_name TEXT NOT NULL
- role TEXT NOT NULL CHECK (role IN ('owner','field_manager','readonly'))
- password_hash TEXT NOT NULL  (bcrypt, for streamlit-authenticator)
- assigned_stores TEXT[]  (array of store_numbers visible to this user;
  NULL means "all stores" for owner role)
- is_active BOOLEAN NOT NULL DEFAULT true
- created_at TIMESTAMPTZ NOT NULL DEFAULT now()

Create ref_field_managers BEFORE ref_stores so the FK works. Or add the FK
constraint at the bottom of the migration after both tables exist.

Write scripts/seed_reference.py that:
- Reads seed/field_managers.csv and upserts into ref_field_managers.
- Reads seed/stores.csv and upserts into ref_stores.
- For ref_users: prompts interactively for password input using getpass,
  hashes with bcrypt, upserts. First run creates the five known users
  (owner + mentor + 3 field managers). Subsequent runs no-op if the user
  exists; offer a --reset-password <email> flag.

Add tests/test_reference_data.py that, after seeding, asserts:
- 15 rows in ref_stores
- At least 3 rows in ref_field_managers
- Every store's field_manager_name matches an existing FM.

Add `bcrypt` to project dependencies in pyproject.toml.

Update CLAUDE.md with a note that adding a new store means: edit
seed/stores.csv, re-run seed_reference.py.

Note: we don't yet have a migration runner (Task 0.5 builds it). For now,
the seed script applies migrations by reading the SQL file and executing
it via psycopg if not already applied (track in a temporary inline
applied-migrations set; Task 0.5 formalizes this).
```

**Verification:**
```bash
# After setting DATABASE_URL in .env:
uv run python scripts/seed_reference.py
uv run pytest tests/test_reference_data.py
git add -A && git commit -m "Task 0.3: reference tables and seed"
```

**Estimated session time:** 45 min.

---

## Task 0.4 — Business calendar helpers + tests

**What this accomplishes:** One module that owns every date and week
calculation in the system. The 02:00 day cutoff and Wed–Tue week become
trustworthy primitives that every other module uses. Without this, every
mart and digest would re-implement these rules with subtle bugs.

**Inputs / Prerequisites:** Task 0.1 complete.

**Acceptance criteria:**
- [ ] `src/subway_ops/calendar.py` exports the four functions below.
- [ ] Every function has a docstring with a worked example.
- [ ] Test coverage 100% on this module (small, load-bearing).
- [ ] Tests cover: midnight edge cases, Wed–Tue week boundaries, DST
      transitions.

**Prompt for Claude Code:**

```text
Create src/subway_ops/calendar.py with these functions and no others:

from datetime import date, datetime
from zoneinfo import ZoneInfo

STORE_TZ = ZoneInfo("America/Los_Angeles")

def business_date_now(now: datetime | None = None) -> date:
    """Return the current Subway business date.

    Subway's business day runs 02:00 → 01:59 local. At 01:30 wall-clock on
    2025-04-16, the business date is still 2025-04-15.

    If `now` is provided (for testing), it must be timezone-aware.
    """

def dt_to_business_date(dt: datetime) -> date:
    """Convert a wall-clock timestamp to its Subway business date.

    Subtract 2 hours, then take the date.
    """

def business_week_of(d: date) -> tuple[date, date]:
    """Return (wednesday_start, tuesday_end) of the Wed–Tue business week
    containing the given business date.

    Example: business_week_of(date(2025, 4, 18))  # a Friday
             → (date(2025, 4, 16), date(2025, 4, 22))
    """

def previous_business_week(today: date | None = None) -> tuple[date, date]:
    """Return the most recently closed business week as of `today`.

    On Wednesday business_date_now=2025-04-23, the previous closed week is
    (2025-04-16 Wed, 2025-04-22 Tue).
    """

def is_business_week_end(d: date) -> bool:
    """True if `d` is a Tuesday (end of a Subway business week)."""

Use stdlib only (datetime, zoneinfo). Don't reach for dateutil.

Write tests/test_calendar.py covering:
- business_date_now at 01:30 PT, 02:30 PT, 12:00 PT, 23:30 PT.
- business_week_of for each day Wed through Tue (verify all yield the
  same week tuple).
- previous_business_week called on each day of a known week.
- DST transition handling (March 2025 spring-forward, November fall-back).
- dt_to_business_date for timestamps that cross the 02:00 boundary.

Do not add a CLI to this module. Pure functions only.
```

**Verification:**
```bash
uv run pytest tests/test_calendar.py -v --cov=src/subway_ops/calendar
uv run python -c "from subway_ops.calendar import previous_business_week; print(previous_business_week())"
git add -A && git commit -m "Task 0.4: business calendar helpers"
```

**Estimated session time:** 30 min.

---

## Task 0.5 — Database connection, migration runner, ops_job_runs

**What this accomplishes:** A way to apply SQL migrations idempotently from
Python, and the first operational metadata table — `ops_job_runs` — that
records every scheduled job's outcome. After this, every ingest and refresh
job will be wrapped in a context manager that logs to this table.

**Inputs / Prerequisites:** Tasks 0.1 and 0.3 complete. Supabase project
provisioned. `DATABASE_URL` in `.env`.

**Acceptance criteria:**
- [ ] `src/subway_ops/db/connection.py` exposes engine and session helpers.
- [ ] `scripts/migrate.py` applies migrations in order, tracked in
      `ops_migrations`.
- [ ] Migration `002_ops_tables.sql` creates `ops_migrations` and
      `ops_job_runs`.
- [ ] Re-running migrate.py is a no-op when nothing new exists.
- [ ] `tests/test_db_connection.py` connects and selects one row.

**Prompt for Claude Code:**

```text
Build the database layer.

src/subway_ops/config.py: pydantic-settings Settings model with:
- database_url: str
- freshconnect_api_client: str
- freshconnect_api_key: str
- app_env: Literal["dev", "prod"] = "dev"
Loads from .env in dev, env vars in prod. Export `settings = Settings()`.

src/subway_ops/db/connection.py:
- get_engine() → SQLAlchemy engine from settings.database_url, pool_pre_ping
  enabled.
- get_session() → context manager yielding a Session.
- execute_sql(sql: str, params: dict | None = None) → helper for raw SQL
  with parameter binding (we use a lot of raw SQL).

src/subway_ops/db/migrations/002_ops_tables.sql:

CREATE TABLE IF NOT EXISTS ops_migrations (
    filename     TEXT PRIMARY KEY,
    applied_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    checksum     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_job_runs (
    id           BIGSERIAL PRIMARY KEY,
    job_name     TEXT NOT NULL,
    started_at   TIMESTAMPTZ NOT NULL,
    finished_at  TIMESTAMPTZ,
    status       TEXT NOT NULL CHECK (status IN ('running','success','failed')),
    rows_written INTEGER,
    error_text   TEXT,
    metadata     JSONB
);

CREATE INDEX idx_job_runs_name_started ON ops_job_runs (job_name, started_at DESC);

scripts/migrate.py:
- Discover all *.sql files in src/subway_ops/db/migrations/ sorted by filename.
- Compute SHA-256 of each file's contents.
- Apply any file whose filename is not in ops_migrations, transactionally.
- If a filename is in ops_migrations but the checksum differs, abort with
  an error (we never modify applied migrations; create new ones instead).
- Print a summary: "Applied N migrations, skipped M."

src/subway_ops/db/job_runs.py:
- start_job(name: str) → int. Inserts a `running` row, returns the id.
- finish_job(job_id, status, rows_written=None, error=None, metadata=None).
- A context manager track_job(name: str) that wraps the above and yields a
  mutable dict for metadata, marking success/failure based on exceptions.
  Re-raises exceptions after marking failed.

Add tests/test_db_connection.py that does a SELECT 1 and asserts.

Update CLAUDE.md (in the relevant section): every ingest / mart job MUST
be wrapped in track_job("job_name").

Update scripts/seed_reference.py from Task 0.3 to use the new migrate.py
pattern: call migrate.py first, then run the seed.
```

**Verification:**
```bash
uv run python scripts/migrate.py     # applies 001 and 002
uv run python scripts/migrate.py     # second run prints "Skipped 2"
uv run pytest tests/test_db_connection.py
git add -A && git commit -m "Task 0.5: db connection, migration runner, ops_job_runs"
```

**Estimated session time:** 45 min.

---

---

# Phase 1 — Fresh Connect Client

---

## Task 1.1 — FreshConnect HTTP client

**What this accomplishes:** A single class handling every HTTP call to Fresh
Connect — correct auth headers, exponential backoff on transient errors,
specific exception types for each documented failure code, and per-endpoint
limit validation before any call goes out. After this, every Phase 2 ingest
module just calls a method on this client.

**Inputs / Prerequisites:** Phase 0 complete. FreshConnect credentials in
`.env`.

**Acceptance criteria:**
- [ ] `FreshConnectClient` accepts credentials via settings.
- [ ] All requests carry `api-client`, `api-key`, `Accept: application/json`.
- [ ] 429 raises `RateLimitError` immediately (no in-job retry).
- [ ] 401, 403, 404, 400 raise specific exception types.
- [ ] 5xx and network errors retry with exponential backoff + jitter, max 5.
- [ ] Every request logs: method, URL, status, duration.
- [ ] Single-restaurant helper, multi-restaurant helper (comma-joined).
- [ ] Pre-call limit validation for each endpoint's documented max.

**Prompt for Claude Code:**

```text
Build src/subway_ops/freshconnect/client.py with a FreshConnectClient class.

Base URL: https://liveiqfranchiseeapi.subway.com/api

Authentication: per the Fresh Connect docs (see docs/freshconnect/
APIDocumentation.pdf — paste it there if not present), every request
includes HTTP headers `api-client` and `api-key` plus
`Accept: application/json`. Pull values from settings.freshconnect_api_client
and settings.freshconnect_api_key.

Define these custom exceptions in the same module:
- FreshConnectError (base)
- AuthError (401)
- ForbiddenError (403)
- BadRequestError (400)
- NotFoundError (404)
- RateLimitError (429)

Implement using httpx.Client with timeout=httpx.Timeout(30.0, connect=10.0).

Retry policy via tenacity:
- On 5xx, on httpx.ConnectError, on httpx.ReadTimeout: retry up to 5 times,
  exponential backoff (base 2s, max 60s), with jitter.
- On 429: do NOT retry within the same job run. Raise RateLimitError with
  a message noting the daily limit resets at midnight UTC.
- On 4xx other than 429: do not retry.

Public methods (all enforce documented per-endpoint limits before issuing
the HTTP call, raising ValueError if exceeded):

def get(self, path: str, *, params: dict | None = None) -> dict:
    """Raw GET. Used by endpoint-specific methods."""

def list_restaurants(self) -> list[str]:
    """GET /Restaurants → list of restaurant_number strings."""

def get_daily_sales_summary(
    self, store_numbers: list[str], start: date, end: date
) -> dict:
    """GET /DailySalesSummary/{stores}/startDate/{start}/endDate/{end}.
    Max 20 stores, max 50 days.
    """

def get_control_sheet(self, store_numbers: list[str], week_end: date) -> dict:
    """GET /controlsheet/{stores}/{weekEndDate}. Max 40 stores, 1-day range
    (week_end is a Tuesday)."""

def get_paidouts_and_no_sales(
    self, store_numbers: list[str], start: date, end: date
) -> dict:
    """Max 20 stores, max 31 days."""

def get_inventory_movement(
    self, store_numbers: list[str], start: date, end: date
) -> dict:
    """Max 20 stores, max 50 days."""

def get_wisr(self, store_numbers: list[str], week_end: date) -> dict:
    """Max 25 stores, week_end is a Tuesday."""

def get_daily_timeclock(
    self, store_numbers: list[str], start: date, end: date
) -> dict:
    """Max 10 stores, max 30 days."""

def get_third_party_daily(
    self, store_numbers: list[str], start: date, end: date
) -> dict:
    """Max 20 stores, max 30 days."""

def get_transaction_details(
    self, store_number: str, start: date, end: date
) -> dict:
    """Single store, max 14 days. Heaviest endpoint."""

def get_tips_details(
    self, store_number: str, start: date, end: date
) -> dict:
    """Single store, max 14 days."""

def get_waste_bread_credits(
    self, store_numbers: list[str], start: date, end: date
) -> dict:
    """Max 10 stores, max 20 days."""

Date params are formatted YYYY-MM-DD. Multiple store_numbers are
comma-joined for the URL.

Add a close() method and __enter__/__exit__ so the client is usable as a
context manager.

Use structlog logger; every request logs method, URL, status code, duration_ms.

Add tests/test_client.py using the `responses` library to mock httpx:
- 200 happy path on get_daily_sales_summary.
- 401 raises AuthError.
- 429 raises RateLimitError.
- 500 retries 5 times then succeeds.
- 500 retries 5 times then fails (final attempt 500 also).
- Calling get_transaction_details with more than 1 store or > 14 days
  raises ValueError before any HTTP call.

All test requests intercepted; no real network calls.
```

**Verification:**
```bash
uv run pytest tests/test_client.py -v
# Smoke test against the real API:
uv run python -c "
from subway_ops.freshconnect.client import FreshConnectClient
with FreshConnectClient() as c:
    print(c.list_restaurants())
"
git add -A && git commit -m "Task 1.1: FreshConnect HTTP client"
```

**Estimated session time:** 60 min.

---

## Task 1.2 — Pydantic models for all 13 endpoints

**What this accomplishes:** Every Fresh Connect response shape becomes a
statically-typed Pydantic model. When Subway changes their API, our parser
fails loudly with a precise error rather than silently dropping data.

**Inputs / Prerequisites:** Task 1.1 complete.

**Acceptance criteria:**
- [ ] `src/subway_ops/freshconnect/models.py` contains a Pydantic model for
      each of the 13 endpoint response envelopes plus their nested types.
- [ ] All models use `ConfigDict(populate_by_name=True, extra="forbid")`.
- [ ] Field aliases handle inconsistencies (`resturantNumber` typo, day-of-week
      keys, etc.).
- [ ] `tests/test_models.py` parses each sample response from the FreshConnect
      docs and asserts success.

**Prompt for Claude Code:**

```text
Build src/subway_ops/freshconnect/models.py with Pydantic v2 models for
every Fresh Connect response shape.

Reference: the response samples in the Fresh Connect documentation PDFs in
docs/freshconnect/ (APIDocumentation.pdf and APIUrlsDocumentation.pdf).

Models to create, one per endpoint envelope, plus all their nested types:

- RestaurantsResponse (list of {restaurantNumber: str})
- DailySalesSummaryResponse with DailySalesRow items
- ControlSheetResponse with nested ControlSheetSummary, CashControl,
  BreadSection, LaborSection, MetricsSection, SalesItemization,
  UnitItemization. Each day-keyed dict ({"wed": 1.0, "thu": 2.0, ...,
  "total": ...}) becomes a DaysOfWeek model with fields wed, thu, fri,
  sat, sun, mon, tue, total — all Decimal | None.
- PaidOutsAndNoSalesResponse with NoSaleEvent and PaidOutEvent items
- InventoryMovementResponse with InventoryMovementItem, InventoryTotal
- WisrResponse with WisrRow, AdjustedCostOfGoods,
  InventoryCategoriesSummary, SalesSummaryItems, UnitsSummaryItems,
  CateringSummaryItems, DistributionCosts, WisrInventoryItem,
  CashBreadOverShortTotals
- DailyTimeclockResponse with TimeclockEntry
- SalesSummaryResponse
- ThirdPartyDailySalesSummaryResponse and ThirdPartySalesSummaryResponse
  sharing a ThirdPartyProvider model
- ThirdPartyTransactionSummaryResponse
- TransactionSummaryResponse
- TransactionDetailsResponse (nests items, tenders, loyalty, taxes,
  discounts, nonSubwayItems)
- TipsDetailsResponse
- WasteBreadCreditsResponse

Conventions:
- Every model: model_config = ConfigDict(populate_by_name=True, extra="forbid")
- Use snake_case Python field names with camelCase aliases:
    restaurant_number: str = Field(alias="restaurantNumber")
- For the typo: alias restaurant_number to BOTH "restaurantNumber" and
  "resturantNumber" using AliasChoices (the API uses both inconsistently).
- Use datetime for ISO datetime strings (API uses "2025-04-15T00:00:00"
  with no timezone). Treat as naive at the model layer; the storage layer
  attaches America/Los_Angeles.
- Money fields: Decimal from decimal.Decimal, never float.
- Percentages: Decimal. Don't interpret here — interpretation lives in the
  mart layer.

Write tests/test_models.py with one test per endpoint that loads its
sample JSON (from the PDF samples) and asserts it parses without error.
Store the sample JSON as Python string literals inside the test file for
now (Task 1.3 will replace these with recorded fixtures).
```

**Verification:**
```bash
uv run pytest tests/test_models.py -v
uv run mypy src/subway_ops/freshconnect/models.py
git add -A && git commit -m "Task 1.2: Pydantic models for all 13 endpoints"
```

**Estimated session time:** 90 min.

---

## Task 1.3 — Discovery script + recorded fixtures

**What this accomplishes:** Hits every Fresh Connect endpoint against your
real credentials for one store + small window, saves the response bodies to
disk as test fixtures, and produces a field-coverage report comparing actual
responses against the documented schema. This is your first real-world
confirmation that the API behaves as documented — and your first chance to
discover the daily rate limit.

**Inputs / Prerequisites:** Tasks 1.1, 1.2 complete. FreshConnect credentials
in `.env`. At least one active store in `ref_stores`.

**Acceptance criteria:**
- [ ] `scripts/discovery.py` exercises all 13 endpoints, saves each response
      to `tests/fixtures/recorded/<endpoint>.json` (gitignored).
- [ ] Generates `docs/api_field_coverage.md` comparing actual vs documented.
- [ ] Discovery is read-only, idempotent, respects rate limits (sleeps
      between endpoints).
- [ ] One test parses each recorded fixture against its model.

**Prompt for Claude Code:**

```text
Create scripts/discovery.py that does these things in order:

1. Load credentials from .env via settings.
2. Pick one active store from ref_stores (or accept --store argument).
3. Use yesterday's business date and the most recent Tuesday's weekEndDate.
4. For each of the 13 endpoints in FreshConnectClient:
   a. Call the endpoint with the smallest valid window.
   b. Save the raw JSON to tests/fixtures/recorded/{endpoint_name}.json.
   c. Attempt to parse with the corresponding Pydantic model; log success
      or capture the validation error.
   d. Sleep 5 seconds between endpoints (be conservative; rate limit is
      unknown).
5. After all endpoints, generate docs/api_field_coverage.md with one
   section per endpoint:
   - URL pattern (verbatim from the docs)
   - Top-level fields returned
   - Nested object paths
   - Fields in the response but NOT in our Pydantic model (red flag)
   - Fields in our Pydantic model but NOT in the response (yellow flag —
     may just be empty for this date)
   - Any Pydantic validation errors encountered

Add tests/test_recorded_fixtures.py that, if any recorded fixtures exist
locally (gitignored), parses each against its model. Skip the test if
fixtures don't exist so CI doesn't fail on a fresh checkout (use
pytest.mark.skipif).

Important:
- The script is safe to re-run; it overwrites fixtures.
- It logs every request to ops_job_runs as job_name='discovery'.
- On rate-limit (429), it stops gracefully with a clear message:
  "Daily rate limit hit. Resume tomorrow after 17:00 PT (00:00 UTC).
   Endpoints completed: [...]"

After running, review docs/api_field_coverage.md manually and capture any
field discrepancies as new entries in decisions.md.
```

**Verification:**
```bash
uv run python scripts/discovery.py --store 25785
cat docs/api_field_coverage.md | head -100
ls tests/fixtures/recorded/
uv run pytest tests/test_recorded_fixtures.py
git add -A && git commit -m "Task 1.3: discovery script and field coverage doc"
```

**Estimated session time:** 60 min. (Plus possibly multiple days if rate
limits force resumption — but the field coverage doc and fixture set are
foundational.)

---

---

# Phase 2 — Ingestion Layer

Each task in this phase follows the same pattern: SQL migration creating
`raw_*` and `stg_*` tables, Python ingest module wrapping the client call
and writing to both, idempotent upsert on natural keys, and tests against
fixtures. By Task 2.3, Claude Code is replicating its own pattern — prompts
get shorter.

---

## Task 2.1 — Schema + ingest: DailySalesSummary

**What this accomplishes:** Daily per-store totals flowing in cleanly,
end-to-end. This is the pattern every other ingest follows. After this,
your `stg_daily_sales` table is the foundation for `mart_store_daily`.

**Inputs / Prerequisites:** Phase 1 complete.

**Acceptance criteria:**
- [ ] Migration `003_daily_sales.sql` creates `raw_daily_sales` and
      `stg_daily_sales`.
- [ ] `src/subway_ops/ingest/daily_sales.py` exposes
      `ingest(start, end, stores)`.
- [ ] Upsert idempotent on `(restaurant_number, business_date)`.
- [ ] Logs to `ops_job_runs` with row counts.
- [ ] Test against recorded fixture.

**Prompt for Claude Code:**

```text
Build the first end-to-end ingest pipeline as the pattern for Phase 2.

Migration 003_daily_sales.sql:

CREATE TABLE IF NOT EXISTS raw_daily_sales (
    id            BIGSERIAL PRIMARY KEY,
    fetched_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    start_date    DATE NOT NULL,
    end_date      DATE NOT NULL,
    payload       JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS stg_daily_sales (
    restaurant_number          TEXT NOT NULL REFERENCES ref_stores(store_number),
    business_date              DATE NOT NULL,
    net_sales                  NUMERIC(12,4) NOT NULL,
    tax                        NUMERIC(12,4) NOT NULL,
    units                      INTEGER NOT NULL,
    transactions               INTEGER NOT NULL,
    cash_card_total            NUMERIC(12,4) NOT NULL,
    third_party_sales          NUMERIC(12,4) NOT NULL,
    third_party_transactions   INTEGER NOT NULL,
    hours_worked               NUMERIC(8,2) NOT NULL,
    ingested_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (restaurant_number, business_date)
);

CREATE INDEX idx_stg_daily_sales_date ON stg_daily_sales (business_date);

Module src/subway_ops/ingest/daily_sales.py:

def ingest(start: date, end: date, store_numbers: list[str] | None = None) -> int:
    """Pulls daily sales for the date range, writes raw + stg, returns row count.

    If store_numbers is None, uses all active stores from ref_stores.
    Batches into chunks of 20 stores × 50 days to respect the endpoint limits.
    Wraps the whole call in track_job("ingest_daily_sales").
    """

Implementation:
1. Resolve store list (default = all active stores from ref_stores).
2. Compute call batches respecting the 20-store / 50-day limits.
3. For each batch:
   - Call FreshConnectClient.get_daily_sales_summary(...).
   - Insert one row to raw_daily_sales with the full payload.
   - Parse via DailySalesSummaryResponse.
   - Upsert each row to stg_daily_sales using ON CONFLICT
     (restaurant_number, business_date) DO UPDATE.
4. Return total rows upserted.

Use a batched-upsert helper (create src/subway_ops/db/upsert.py):

def upsert_rows(table: str, rows: list[dict], key_cols: list[str]) -> int:
    """Generic UPSERT for any staging table. Returns rows affected."""

Write tests/test_ingest_daily_sales.py:
- Loads tests/fixtures/recorded/daily_sales_summary.json if present (skip
  otherwise).
- Mocks FreshConnectClient.get_daily_sales_summary to return that payload.
- Calls ingest(...).
- Asserts row count > 0.
- Re-runs ingest with the same payload; asserts the same row count
  (idempotent — UPDATE not INSERT).
```

**Verification:**
```bash
uv run python scripts/migrate.py
uv run python -c "
from datetime import date
from subway_ops.ingest.daily_sales import ingest
print('rows:', ingest(date(2025,4,16), date(2025,4,22)))
print('rows on rerun:', ingest(date(2025,4,16), date(2025,4,22)))
"
uv run pytest tests/test_ingest_daily_sales.py
git add -A && git commit -m "Task 2.1: DailySalesSummary ingest"
```

**Estimated session time:** 60 min.

---

## Task 2.2 — Schema + ingest: ControlSheet (weekly)

**What this accomplishes:** The richest endpoint — weekly cash control,
sales itemization, unit itemization, bread, labor — flattened into one wide
table. This becomes the backbone of `mart_store_weekly`, and the
POS-recorded `depositInBank` here is the basis for the entire
reconciliation flow.

**Inputs / Prerequisites:** Task 2.1 complete.

**Acceptance criteria:**
- [ ] Migration `004_controlsheet.sql` creates `raw_controlsheet` and
      `stg_controlsheet_weekly` (one row per store per week_end_date).
- [ ] All day-of-week sections flattened to 8 columns each (wed–tue + total).
- [ ] Idempotent on `(restaurant_number, week_end_date)`.
- [ ] Test from recorded fixture.

**Prompt for Claude Code:**

```text
Build the ControlSheet ingest following the same pattern as Task 2.1.

The ControlSheet endpoint returns weekly per-store rollups across cash
control, sales itemization, unit itemization, bread, labor, and metrics,
with most fields broken down by day of week (wed, thu, fri, sat, sun, mon,
tue) and a total.

Migration 004_controlsheet.sql:
- Create raw_controlsheet (id, fetched_at, week_end_date DATE, payload JSONB)
- Create stg_controlsheet_weekly with these flattened columns. For every
  dict-by-day-of-week field, create 8 columns: <field>_wed, <field>_thu,
  <field>_fri, <field>_sat, <field>_sun, <field>_mon, <field>_tue,
  <field>_total. Reference the field-by-field schema in
  docs/freshconnect/APIUrlsDocumentation.pdf, ControlSheet section.

Column types:
- cashControl.* → NUMERIC(12,4)
- bread.* → NUMERIC(8,4)
- labor.* → NUMERIC(8,4)
- metrics.* → NUMERIC(8,4)
- salesItemization.* → NUMERIC(12,4) (amounts) and NUMERIC(8,4) for the
  paired *_percentage column where present
- unitItemization.* → INTEGER (quantities) and NUMERIC(8,4) for percentage

Primary key: (restaurant_number, week_end_date).

The salesItemization.*.percentage and unitItemization.*.percentage fields
stay as separate columns alongside the by-day amounts. Name them
sales_itemization_footlong_percentage etc.

Module src/subway_ops/ingest/controlsheet.py with ingest(week_end: date,
store_numbers: list[str] | None = None) -> int. Batches 40 stores per call.

Test that re-running for the same week_end produces the same row count.

Update CLAUDE.md with a one-line note: "ControlSheet ingest produces ~120
columns by design. Reads are cheap via the PK index; queries stay narrow
because the dashboard selects only what it needs."
```

**Verification:**
```bash
uv run python scripts/migrate.py
uv run python -c "
from datetime import date
from subway_ops.ingest.controlsheet import ingest
print(ingest(date(2025, 4, 22)))   # a Tuesday
"
uv run pytest tests/test_ingest_controlsheet.py
git add -A && git commit -m "Task 2.2: ControlSheet ingest"
```

**Estimated session time:** 90 min.

---

## Task 2.3 — Schema + ingest: PaidOutsAndNoSales (cash drops)

**What this accomplishes:** Every POS-recorded cash drop event lands in
staging. Combined with ControlSheet's daily `depositInBank`, this is the
data backbone of the reconciliation system.

**Inputs / Prerequisites:** Tasks 2.1, 2.2 complete.

**Acceptance criteria:**
- [ ] Migration creates `raw_paidouts_no_sales`, `stg_no_sales`,
      `stg_paid_outs`, and `stg_cash_drops` VIEW.
- [ ] Idempotent on natural composite keys.
- [ ] Tested against recorded fixture.

**Prompt for Claude Code:**

```text
Follow the Phase 2 pattern (see Tasks 2.1, 2.2) to ingest the
PaidOutsAndNoSales endpoint.

The endpoint returns two top-level arrays:
- noSales: each with restaurantNumber, time, clerkId, clerkName,
  noSaleType, reasonType, reason
- paidOuts: each with restaurantNumber, time, clerkId, clerkName, amount,
  reason, comment

Migration 005_paidouts_no_sales.sql:

CREATE TABLE raw_paidouts_no_sales (
    id BIGSERIAL PRIMARY KEY,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    payload JSONB NOT NULL
);

CREATE TABLE stg_no_sales (
    restaurant_number TEXT NOT NULL REFERENCES ref_stores(store_number),
    event_time   TIMESTAMP NOT NULL,
    business_date DATE NOT NULL,
    clerk_id     TEXT NOT NULL,
    clerk_name   TEXT,
    no_sale_type TEXT NOT NULL,
    reason_type  TEXT,
    reason       TEXT,
    ingested_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (restaurant_number, event_time, clerk_id, no_sale_type)
);

CREATE TABLE stg_paid_outs (
    restaurant_number TEXT NOT NULL REFERENCES ref_stores(store_number),
    event_time   TIMESTAMP NOT NULL,
    business_date DATE NOT NULL,
    clerk_id     TEXT NOT NULL,
    clerk_name   TEXT,
    amount       NUMERIC(12,4) NOT NULL,
    reason       TEXT,
    comment      TEXT,
    ingested_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (restaurant_number, event_time, clerk_id, amount, reason)
);

CREATE VIEW stg_cash_drops AS
SELECT * FROM stg_no_sales WHERE no_sale_type = 'cash drop';

The business_date column is computed at ingest from event_time using
subway_ops.calendar.dt_to_business_date.

Module src/subway_ops/ingest/paidouts.py with ingest(start, end,
store_numbers). Batches 20 stores × 31 days per call.

Tests: from recorded fixture, assert that cash drop events end up in
stg_cash_drops (the VIEW), paid outs in stg_paid_outs, and the count of
each matches what's in the fixture.
```

**Verification:**
```bash
uv run python scripts/migrate.py
uv run python -c "
from datetime import date
from subway_ops.ingest.paidouts import ingest
print(ingest(date(2025,4,16), date(2025,4,22)))
"
uv run pytest tests/test_ingest_paidouts.py
git add -A && git commit -m "Task 2.3: PaidOutsAndNoSales ingest"
```

**Estimated session time:** 60 min.

---

## Task 2.4 — Schema + ingest: InventoryMovement

**What this accomplishes:** Daily per-item inventory deltas — deliveries,
transfers, waste — flow into staging. The pattern is now familiar; this
task should feel routine.

**Inputs / Prerequisites:** Tasks 2.1–2.3 complete.

**Acceptance criteria:** Migration `006_inventory_movement.sql` creates raw
+ two staging tables. Idempotent. Tested.

**Prompt for Claude Code:**

```text
Follow the Phase 2 pattern. Endpoint: InventoryMovement. Limits per docs:
20 stores, 50 days.

The response has nested `totals` (currently a single item per day: "UNITS
COST" with totalCost and wasteValue) and `items` (Bread, Cheese, etc.).
Flatten both into rows.

Migration 006_inventory_movement.sql:

CREATE TABLE raw_inventory_movement (
    id BIGSERIAL PRIMARY KEY,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    payload JSONB NOT NULL
);

CREATE TABLE stg_inventory_movement (
    restaurant_number TEXT NOT NULL REFERENCES ref_stores(store_number),
    business_date DATE NOT NULL,
    item_category TEXT NOT NULL,        -- "Bread", "Cheese", etc.
    inventory_item TEXT NOT NULL,        -- "Bread, White, 80/1"
    unit_of_measure TEXT,
    unit_cost NUMERIC(12,4),
    delivery NUMERIC(12,4),
    transfer NUMERIC(12,4),
    total_cost NUMERIC(12,4),
    waste NUMERIC(12,4),
    waste_value NUMERIC(12,4),
    PRIMARY KEY (restaurant_number, business_date, inventory_item)
);

CREATE TABLE stg_inventory_movement_totals (
    restaurant_number TEXT NOT NULL REFERENCES ref_stores(store_number),
    business_date DATE NOT NULL,
    metric_name TEXT NOT NULL,           -- "UNITS COST"
    total_cost NUMERIC(12,4),
    waste_value NUMERIC(12,4),
    PRIMARY KEY (restaurant_number, business_date, metric_name)
);

Module: src/subway_ops/ingest/inventory_movement.py.
Tests: same pattern as Task 2.1.
```

**Verification:** Same pattern as Task 2.1. Commit message:
`Task 2.4: InventoryMovement ingest`.

**Estimated session time:** 60 min.

---

## Task 2.5 — Schema + ingest: Wisr (weekly WISR)

**What this accomplishes:** Subway's gold-standard weekly food-cost analysis
lands in staging. Two tables: one wide row per store per week, and one row
per inventory item per store per week. This drives the food-cost variance
KPIs in `mart_store_weekly`.

**Inputs / Prerequisites:** Tasks 2.1–2.4 complete.

**Acceptance criteria:** Migrations create three tables. Idempotent. Tested.

**Prompt for Claude Code:**

```text
Follow the Phase 2 pattern. Wisr endpoint: max 25 stores per call,
1 weekEndDate per call.

The response is dense. Two staging tables, plus raw:

Migration 007_wisr.sql:

CREATE TABLE raw_wisr (
    id BIGSERIAL PRIMARY KEY,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    week_end_date DATE NOT NULL,
    payload JSONB NOT NULL
);

stg_wisr_weekly — one row per store per week_end_date with these flattened
columns:

Top-level:
- total_inventory_value, customer_count, units_per_customer, factor,
  average_ticket.

All adjustedCostOfGoods.* (freeUnits, employeeFree, employeeDiscounts,
otherDiscountValue, fvmDiscountsValue, miscAndDrinkDiscValue,
totalDiscountValue, discountValuePctOfSales, adjustedCostOfGoods)
get 3 columns each: _quantity, _value, _percentage.

All inventoryCategoriesSummary.* (cheese, meatProtein, breadCarrier,
veggies, toppings, papergoods, unitsCost, drinksCost, miscCost,
costOfGoods, distributionCost) get 5 columns each:
_value_used, _value_diff, _actual_pct, _expected_pct, _pct_diff.

All salesSummaryItems.* (unitSales, cateringSales, drinkSales, miscSales,
netSubwaySales, gas, electric, telephone, garbage, insurance, rent,
laundry, misc, repairMaintenance, operatingExpenses, laborAndTaxes,
costOfGoods, royalty, faf, localAdvertising, totalExpenses, balance,
financialStrength, loans) get 2 columns each: _value, _pct.

All unitsSummaryItems.* (footlong, sixInch, threeInchAndMuffin, salads,
pizza, otherUnits, totalUnits, drinks) get 2 columns each: _quantity, _pct.

All cateringSummaryItems.* (giantSubs, sandwichPlatters, boxedMeals,
dessertPlatters) get 2 columns each: _quantity, _value.

All distributionCosts.* (deliveryFee, distributorCredits, annualIpcPatronage,
distributionCosts) get 2 columns each: _value_used, _actual_pct.

All cashBreadOverShortTotals.* get 16 columns: 8 weekdays × 2 (cash vs bread).

Primary key: (restaurant_number, week_end_date).

stg_wisr_inventory_items — one row per store per week_end_date per item:

CREATE TABLE stg_wisr_inventory_items (
    restaurant_number TEXT NOT NULL REFERENCES ref_stores(store_number),
    week_end_date DATE NOT NULL,
    item_name TEXT NOT NULL,
    open_qty NUMERIC(12,4),
    delivered_qty NUMERIC(12,4),
    left_qty NUMERIC(12,4),
    used_qty NUMERIC(12,4),
    pos_difference NUMERIC(12,4),
    recorded_waste NUMERIC(12,4),
    cost NUMERIC(12,4),
    value_used NUMERIC(12,4),
    value_difference NUMERIC(12,4),
    actual_percentage NUMERIC(8,6),
    expected_percentage NUMERIC(8,6),
    diff_percentage NUMERIC(8,6),
    PRIMARY KEY (restaurant_number, week_end_date, item_name)
);

Module: src/subway_ops/ingest/wisr.py. Tests: parse fixture, assert
top-level row created and one row per inventory item in the fixture.
```

**Verification:** Same pattern as Task 2.1. Commit:
`Task 2.5: Wisr ingest`.

**Estimated session time:** 90 min.

---

## Task 2.6 — Schema + ingest: DailyTimeclock + ThirdPartyDailySalesSummary

**What this accomplishes:** Two remaining daily-grain endpoints we want
routinely. Timeclock fills in labor detail; third-party daily fills in
delivery channel breakdown.

**Inputs / Prerequisites:** Tasks 2.1–2.5 complete.

**Acceptance criteria:** Migrations 008 and 009. Ingest modules. Tests.

**Prompt for Claude Code:**

```text
Follow the Phase 2 pattern for two endpoints.

DailyTimeclock (limits: 10 stores, 30 days)
- Fields per docs: restaurantNumber, clerkId, employeeName, clockIn,
  clockOut, hours, totalAdj, totalBeforeAdj, adjAmount. Note the docs are
  inconsistent — the sample shows `hours` but the field table shows
  `hoursBeforeAdj` and `hoursAfterAdj`. Handle both shapes with Pydantic
  field aliases on a single canonical column `hours_total`.
- Migration 008_timeclock.sql with raw_timeclock and stg_timeclock.
  PK: (restaurant_number, clerk_id, clock_in).

ThirdPartyDailySalesSummary (limits: 20 stores, 30 days)
- Migration 009_third_party_daily.sql with two staging tables:
  stg_3p_daily (one per store per day with totals: totalSales,
  totalNetSales, totalTransactions; PK restaurant_number, business_date)
  and stg_3p_daily_provider (one per store per day per provider; PK
  restaurant_number, business_date, provider).

Modules: src/subway_ops/ingest/timeclock.py and
src/subway_ops/ingest/third_party_daily.py.

Skip these heavy endpoints for now (transactional-grain — useful for later
analytics but not Phase 2 essentials):
- TransactionDetails
- TipsDetails
- TransactionSummary
- ThirdPartyTransactionSummary
- WasteBreadCredits

They become Phase 7+ optional extras via a separate
scripts/backfill_deep.py.

Tests: standard pattern.
```

**Verification:** Same pattern. Commit:
`Task 2.6: Timeclock and ThirdPartyDailySalesSummary ingest`.

**Estimated session time:** 60 min.

---

## Task 2.7 — Daily orchestrator + GitHub Actions cron

**What this accomplishes:** A single `daily_pull.py` script that runs all
six ingest modules for the appropriate windows, and a GitHub Actions
workflow that fires it on schedule. After this, the system is ingesting
automatically every morning.

**Inputs / Prerequisites:** Tasks 2.1–2.6 complete. GitHub repo secrets
configured: `DATABASE_URL`, `FRESHCONNECT_API_CLIENT`, `FRESHCONNECT_API_KEY`,
`GMAIL_USER`, `GMAIL_APP_PASSWORD`, `ALERT_EMAIL`.

**Acceptance criteria:**
- [ ] `scripts/daily_pull.py` runs all 6 ingests with the right windows.
- [ ] `.github/workflows/daily_pull.yml` runs at 10:00 UTC daily (03:00 PT).
- [ ] Credentials from GH secrets, never the repo.
- [ ] On failure, an email goes to the operator.
- [ ] A clean run produces a `success` row in `ops_job_runs`.

**Prompt for Claude Code:**

```text
Build the daily orchestrator.

scripts/daily_pull.py:

from datetime import date, timedelta
from subway_ops.calendar import previous_business_week, business_date_now

def main() -> int:
    today = business_date_now()
    yesterday = today - timedelta(days=1)
    last_week_start, last_week_end = previous_business_week(today)

    # Daily-grain: yesterday only
    ingest_daily_sales(yesterday, yesterday)
    ingest_paidouts(yesterday, yesterday)
    ingest_inventory_movement(yesterday, yesterday)
    ingest_timeclock(yesterday, yesterday)
    ingest_third_party_daily(yesterday, yesterday)

    # Weekly-grain: only on Wednesday, for the just-closed week
    if today.weekday() == 2:   # Wednesday
        ingest_controlsheet(last_week_end)
        ingest_wisr(last_week_end)

    return 0

if __name__ == "__main__":
    raise SystemExit(main())

Wrap everything inside track_job("daily_pull"). Failures bubble up as
non-zero exit codes.

.github/workflows/daily_pull.yml:

name: Daily pull
on:
  schedule:
    - cron: "0 10 * * *"   # 10:00 UTC = 03:00 PT (standard time)
  workflow_dispatch:

jobs:
  pull:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --frozen
      - run: uv run python scripts/daily_pull.py
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          FRESHCONNECT_API_CLIENT: ${{ secrets.FRESHCONNECT_API_CLIENT }}
          FRESHCONNECT_API_KEY: ${{ secrets.FRESHCONNECT_API_KEY }}
          APP_ENV: prod
      - name: Notify on failure
        if: failure()
        run: uv run python scripts/notify_failure.py "daily_pull"
        env:
          GMAIL_USER: ${{ secrets.GMAIL_USER }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
          ALERT_EMAIL: ${{ secrets.ALERT_EMAIL }}

Build scripts/notify_failure.py — sends a plain-text email via Gmail SMTP
including the job name, timestamp, and a link to the GitHub Actions run
URL (read from $GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID).

Document in CLAUDE.md: "Adding a new daily ingest: create the ingest
module, add it to daily_pull.py."
```

**Verification:**
```bash
# In GitHub UI: Actions → Daily pull → Run workflow.
# Then check the run logs and Supabase for new rows.
# Verify failure email by temporarily breaking the FreshConnect key secret,
# re-running, then restoring the key.
git add -A && git commit -m "Task 2.7: daily orchestrator and GitHub Actions cron"
```

**Estimated session time:** 60 min.

---

---

# Phase 3 — Marts & Backfill

---

## Task 3.1 — `mart_store_daily`

**What this accomplishes:** One row per store per business date with every
daily-grain KPI computed and stored. This is what powers the dashboard's
"current week" views and 30-day trend charts.

**Inputs / Prerequisites:** Phase 2 complete; at least one day of data in
staging.

**Acceptance criteria:** Migration 010 creates the mart. Refresh module
rebuilds it. Tested.

**Prompt for Claude Code:**

```text
Build mart_store_daily.

Migration 010_mart_store_daily.sql:

CREATE TABLE mart_store_daily (
    restaurant_number TEXT NOT NULL REFERENCES ref_stores(store_number),
    business_date DATE NOT NULL,
    -- from stg_daily_sales:
    net_sales NUMERIC(12,4),
    tax NUMERIC(12,4),
    transactions INTEGER,
    units INTEGER,
    hours_worked NUMERIC(8,2),
    sales_per_labor_hour NUMERIC(12,4) GENERATED ALWAYS AS
        (CASE WHEN hours_worked > 0 THEN net_sales / hours_worked ELSE NULL END) STORED,
    average_ticket NUMERIC(12,4) GENERATED ALWAYS AS
        (CASE WHEN transactions > 0 THEN net_sales / transactions ELSE NULL END) STORED,
    -- from stg_3p_daily:
    third_party_sales NUMERIC(12,4),
    third_party_transactions INTEGER,
    third_party_pct NUMERIC(8,4) GENERATED ALWAYS AS
        (CASE WHEN net_sales > 0 THEN third_party_sales / net_sales ELSE NULL END) STORED,
    -- from stg_inventory_movement_totals:
    daily_inventory_cost NUMERIC(12,4),
    daily_inventory_waste NUMERIC(12,4),
    -- from stg_cash_drops:
    cash_drop_count INTEGER,
    -- derived:
    food_cost_pct NUMERIC(8,4) GENERATED ALWAYS AS
        (CASE WHEN net_sales > 0 THEN daily_inventory_cost / net_sales ELSE NULL END) STORED,
    refreshed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (restaurant_number, business_date)
);

CREATE INDEX idx_mart_daily_date ON mart_store_daily (business_date);

Module src/subway_ops/transform/mart_store_daily.py:

def refresh(start: date | None = None, end: date | None = None) -> int:
    """Rebuilds mart_store_daily for the given date range.
    Default: refresh the last 14 days (catches late corrections).
    """

Implementation: a single INSERT … ON CONFLICT DO UPDATE statement that
reads from stg_daily_sales, stg_3p_daily, stg_inventory_movement_totals,
and a subquery counting stg_cash_drops grouped by (store, business_date).
Use a CTE per source for readability.

Wrap in track_job("refresh_mart_store_daily"). Return rows upserted.

Tests: seed synthetic rows in the staging tables; run refresh; assert
mart row has expected values, especially the GENERATED columns.
```

**Verification:** Standard pattern.

**Estimated session time:** 60 min.

---

## Task 3.2 — `mart_store_weekly`

**What this accomplishes:** One row per store per week_end_date, blending
ControlSheet, Wisr, and rolled-up daily metrics. KPIs flagged against your
22% / 28% store-level targets.

**Inputs / Prerequisites:** Tasks 2.2, 2.5, 3.1 complete.

**Acceptance criteria:** Migration 011. Refresh module. Tests.

**Prompt for Claude Code:**

```text
Build mart_store_weekly.

Migration 011_mart_store_weekly.sql. One row per (restaurant_number,
week_end_date). Columns:

- restaurant_number, week_end_date (Tuesday).
- week_start_date computed (the prior Wednesday).
- From stg_controlsheet_weekly: net_sales_total, transactions_total
  (sum across days where the controlsheet doesn't already total),
  units_total, hours_worked_total, cash_overshort_total,
  bread_overshort_total, deposit_in_bank_total, customer_count, factor,
  average_ticket, productivity.
- From stg_wisr_weekly: food_cost_actual_pct (= cost_of_goods_actual_pct
  — confirm whether the API returns whole-number percentages or fractional
  by inspecting the recorded fixture, treat consistently),
  food_cost_expected_pct, food_cost_diff_pct, adjusted_cost_of_goods_pct,
  total_inventory_value, distribution_cost_value.
- Labor: labor_cost_pct. If labor cost isn't directly available in
  ControlSheet, leave NULL with a TODO comment. We may add an estimate
  using hoursWorked * average wage in a later task.
- Targets and flags (move to config.py):
    TARGET_FOOD_COST_STORE = Decimal("0.22")
    TARGET_LABOR_COST_STORE = Decimal("0.28")
- is_food_cost_in_target BOOLEAN GENERATED ALWAYS AS
    (food_cost_actual_pct <= 0.22) STORED
- is_labor_cost_in_target BOOLEAN GENERATED ALWAYS AS
    (labor_cost_pct <= 0.28) STORED

Module src/subway_ops/transform/mart_store_weekly.py with
refresh(week_end: date | None = None). Default refreshes most recently
closed week.

Tests: synthetic data + assert KPI flags computed correctly.
```

**Verification:** Standard pattern. Commit: `Task 3.2: mart_store_weekly`.

**Estimated session time:** 60 min.

---

## Task 3.3 — `mart_field_manager_portfolio`

**What this accomplishes:** Rollup to field manager level (Maria, James,
Kevin) with sales-weighted KPIs against the portfolio-level targets
(20% / 25%).

**Inputs / Prerequisites:** Task 3.2 complete.

**Acceptance criteria:** Migration 012. Refresh module. Tests.

**Prompt for Claude Code:**

```text
Build mart_field_manager_portfolio.

One row per (field_manager_name, week_end_date). Columns:

- field_manager_name, week_end_date
- store_count, store_count_in_target_food, store_count_in_target_labor
- total_net_sales_weighted (sum of mart_store_weekly.net_sales_total)
- portfolio_food_cost_pct (sales-weighted average across the FM's stores)
- portfolio_labor_cost_pct (sales-weighted average)
- is_food_cost_in_portfolio_target BOOLEAN GENERATED ALWAYS AS
    (portfolio_food_cost_pct <= 0.20) STORED
- is_labor_cost_in_portfolio_target BOOLEAN GENERATED ALWAYS AS
    (portfolio_labor_cost_pct <= 0.25) STORED
- refreshed_at TIMESTAMPTZ DEFAULT now()
- PRIMARY KEY (field_manager_name, week_end_date)

Use sales-weighted averages, not simple averages, since stores differ in
volume. Specifically:

portfolio_food_cost_pct = SUM(store_food_cost_pct * store_net_sales)
                        / SUM(store_net_sales)

Add to config.py:
TARGET_FOOD_COST_PORTFOLIO = Decimal("0.20")
TARGET_LABOR_COST_PORTFOLIO = Decimal("0.25")

Refresh logic joins mart_store_weekly to ref_stores, groups by
field_manager_name.

Module src/subway_ops/transform/mart_field_manager_portfolio.py with
refresh(week_end: date | None = None).

Tests: synthetic stores with varying sales; assert weighted average
correctness.
```

**Verification:** Standard. Commit: `Task 3.3: mart_field_manager_portfolio`.

**Estimated session time:** 45 min.

---

## Task 3.4 — 12-month backfill script

**What this accomplishes:** Loads 12 months of history into staging,
respecting rate limits, fully resumable. On rate limit, exits cleanly and
prints instructions to resume tomorrow. Refreshes marts when staging is
done.

**Inputs / Prerequisites:** Tasks 2.7, 3.1–3.3 complete.

**Acceptance criteria:**
- [ ] `scripts/backfill.py` accepts `--start YYYY-MM-DD --end YYYY-MM-DD`.
- [ ] Resumable via `ops_backfill_progress`.
- [ ] On 429, exits cleanly with resume instructions.
- [ ] Refreshes marts after staging is populated.

**Prompt for Claude Code:**

```text
Build the backfill script.

Migration 013_backfill_progress.sql:

CREATE TABLE ops_backfill_progress (
    job_name     TEXT NOT NULL,
    endpoint     TEXT NOT NULL,
    window_start DATE NOT NULL,
    window_end   DATE NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (job_name, endpoint, window_start, window_end)
);

scripts/backfill.py:

1. Parse --start and --end. Default: end = today, start = end - 365 days.
2. For each endpoint, compute the list of (window_start, window_end)
   tuples respecting that endpoint's limits. Daily endpoints chunk by
   50 days, weekly endpoints chunk by 1 week, etc. ControlSheet and
   Wisr iterate week-by-week from the first Tuesday in range.
3. Skip windows already in ops_backfill_progress for that endpoint.
4. For each pending window:
   - Call the matching ingest function.
   - Record completion in ops_backfill_progress.
5. On RateLimitError: print summary of completed/pending per endpoint;
   exit 0 (resumable). Include the recommended resume time
   (after 17:00 PT today, when UTC midnight passes).
6. On full plan success: refresh mart_store_daily, mart_store_weekly,
   mart_field_manager_portfolio for the full backfill window. Print a
   summary: "Backfill complete. {N} windows loaded. Refreshed marts for
   {start} to {end}."

Add a status command: scripts/backfill.py --status shows completed /
remaining windows per endpoint as a table.

Important:
- The script is safe to interrupt (Ctrl-C); the next run resumes.
- Always wrap in track_job("backfill").
- Log each window completion so the operator can watch progress.
```

**Verification:**
```bash
# Run with a small window first to validate:
uv run python scripts/backfill.py --start 2025-04-01 --end 2025-04-15
uv run python scripts/backfill.py --status

# Then full 12-month run (may take days due to rate limits):
uv run python scripts/backfill.py
git add -A && git commit -m "Task 3.4: 12-month backfill"
```

**Estimated session time:** 90 min for the code; days of wall-clock time
for the full backfill to complete.

---

## Task 3.5 — Mart refresh job + schedule

**What this accomplishes:** Marts stay current throughout the day without
manual intervention. After this, the dashboard always shows numbers no
more than 4 hours stale.

**Inputs / Prerequisites:** Tasks 3.1–3.4 complete.

**Acceptance criteria:** Refresh script + cron entry.

**Prompt for Claude Code:**

```text
Build scripts/refresh_marts.py that refreshes the three marts for the
last 14 days (rolling window — late corrections in staging propagate).

scripts/refresh_marts.py:

from datetime import date, timedelta
from subway_ops.transform.mart_store_daily import refresh as refresh_daily
from subway_ops.transform.mart_store_weekly import refresh as refresh_weekly
from subway_ops.transform.mart_field_manager_portfolio import refresh as refresh_fm
from subway_ops.calendar import business_date_now, previous_business_week
from subway_ops.db.job_runs import track_job

def main() -> int:
    with track_job("refresh_marts"):
        today = business_date_now()
        start = today - timedelta(days=14)
        refresh_daily(start, today)
        # Refresh the last 2 closed weeks
        _, last_tue = previous_business_week(today)
        for offset in (0, 7):
            wk = last_tue - timedelta(days=offset)
            refresh_weekly(wk)
            refresh_fm(wk)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

.github/workflows/refresh_marts.yml: cron 0 */4 * * * (every 4 hours).
Same secrets and failure notification as daily_pull.yml.
```

**Verification:** Manually trigger workflow; check `ops_job_runs`.

**Estimated session time:** 30 min.

---

---

# Phase 4 — Dashboard

---

## Task 4.1 — Streamlit app skeleton + authentication

**What this accomplishes:** A multipage Streamlit app with login. Different
users see different stores based on their `assigned_stores` from `ref_users`.

**Inputs / Prerequisites:** Phase 3 complete.

**Acceptance criteria:** Login works; authenticated session shows different
stores per role.

**Prompt for Claude Code:**

```text
Build the Streamlit app skeleton.

Add streamlit and streamlit-authenticator to pyproject.toml.

Structure under src/subway_ops/dashboard/:

dashboard/
├── app.py                  # entry: login, sidebar, page routing
├── auth.py                 # streamlit-authenticator integration
├── data.py                 # cached DB query helpers
├── components/
│   ├── __init__.py         # shared color palette, constants
│   ├── kpi_card.py
│   ├── store_grid.py
│   └── filters.py
└── pages/
    ├── 1_owner_overview.py
    ├── 2_store_detail.py
    ├── 3_field_manager.py
    └── 4_reconciliation.py

Authentication via streamlit-authenticator:
- auth.py loads credentials from ref_users at session start.
- Builds the streamlit-authenticator config dict in-memory from rows
  (passwords already bcrypt-hashed at seed time in Task 0.3).
- After login, store user_role and assigned_stores in st.session_state.
- A helper visible_stores() returns the list of store_numbers the current
  user can see (assigned_stores, or all if NULL).

data.py:
- @st.cache_resource get_engine() returning the SQLAlchemy engine.
- @st.cache_data(ttl=300) get_weekly_overview(week_end, store_filter),
  get_store_daily(store_number, start, end), get_recon_status(week_end,
  store_filter), etc. — one helper per major dashboard query.

.streamlit/secrets.toml (gitignored):
database_url = "..."
auth_cookie_key = "..."     # random string for cookie signing

Pages:
- Owner role: all 4 pages, all stores.
- Field manager role: same 4 pages but data filtered to their cluster.
- readonly: same as field manager (read-only — no edits).

For this task, just placeholder content: each page shows
"Welcome {name}, role {role}, you can see stores: {list}".

Add a sidebar showing: user identity, role, "Sign out" button, and a
"Last data refresh" timestamp from MAX(refreshed_at) in mart_store_daily.
```

**Verification:**
```bash
uv run streamlit run src/subway_ops/dashboard/app.py
# Log in as owner; log in as a field manager; confirm filtered visibility.
git add -A && git commit -m "Task 4.1: Streamlit skeleton + auth"
```

**Estimated session time:** 60 min.

---

## Task 4.2 — Owner overview page (15-store grid)

**What this accomplishes:** Your at-a-glance view of all 15 stores with
current-week performance. Sortable, color-coded grid plus a 13-week trend.

**Inputs / Prerequisites:** Task 4.1 complete; marts populated.

**Acceptance criteria:** Sortable, filterable, KPI-colored grid; click into
a store opens the detail page.

**Prompt for Claude Code:**

```text
Build pages/1_owner_overview.py.

Layout:

Top: week selector. Default = most recently closed week. Toggle: "Current
week (in progress)" vs "Last closed week".

KPI summary cards (use components/kpi_card.py):
- Total net sales (week)
- Total transactions (week)
- Portfolio food cost % (sales-weighted)
- Portfolio labor cost % (sales-weighted)
- Stores in target (e.g. "12 / 15")
- Reconciliation status (e.g. "11 reconciled, 2 flagged, 2 unverified")

Main grid (use st.dataframe with column_config for chips/colors):
- One row per store visible to this user.
- Columns: store_number, store_name, field_manager, net_sales,
  transactions, food_cost_pct, labor_cost_pct, cash_overshort_total,
  recon_status (chip), recon_variance.
- Color rules in components/__init__.py:
    GREEN ≤ target, YELLOW within +2pp, RED otherwise.
    For food_cost_pct: green ≤ 0.22, yellow 0.22–0.24, red > 0.24.
    For labor_cost_pct: green ≤ 0.28, yellow 0.28–0.30, red > 0.30.
- Sortable by any column.
- Click a row: set st.session_state["selected_store"] = store_number,
  then st.switch_page("pages/2_store_detail.py").

Below the grid: trend chart (Altair line chart) of portfolio net_sales
by week for the last 13 weeks. Use altair, no plotly.

Use cached data helpers from data.py:

@st.cache_data(ttl=300)
def get_weekly_overview(week_end: date, store_filter: list[str] | None) -> pd.DataFrame:
    """Reads mart_store_weekly + mart_recon_weekly joined to ref_stores."""

@st.cache_data(ttl=300)
def get_portfolio_trend(weeks: int = 13, store_filter: list[str] | None = None) -> pd.DataFrame:
    """Net sales by week_end_date for the last N weeks."""

Respect visible_stores() everywhere — never query without applying the
store filter for non-owner roles.
```

**Verification:** Open in browser, click around. Commit:
`Task 4.2: owner overview page`.

**Estimated session time:** 90 min.

---

## Task 4.3 — Store detail drill-down page

**What this accomplishes:** A single store's full picture: daily trend,
weekly history, WISR inventory detail, cash drops.

**Inputs / Prerequisites:** Task 4.2 complete.

**Acceptance criteria:** Four tabs work, all charts render, filters
respect user role.

**Prompt for Claude Code:**

```text
Build pages/2_store_detail.py.

Top of page: store selector (selectbox filtered to visible_stores()).
If st.session_state["selected_store"] is set, default to that.

Tabs (st.tabs):

1. Daily trend — last 30 business days.
   - Line charts (Altair): net_sales, transactions, sales_per_labor_hour,
     food_cost_pct.
   - Each chart has a target reference line where applicable.
   - Source: mart_store_daily.

2. Weekly history — last 13 weeks.
   - Same KPIs rolled up weekly.
   - Show target lines (food cost 22%, labor cost 28%).
   - Source: mart_store_weekly.

3. Inventory detail (WISR) — week selector.
   - Table of stg_wisr_inventory_items for that store + selected week.
   - Sortable by value_difference DESC so biggest variances surface first.
   - Color value_difference column red for negative (used more than
     expected), green for positive.

4. Cash drops — date range selector (default: last business week).
   - Table from stg_cash_drops joined with ControlSheet
     deposit_in_bank to show drops alongside the daily deposit total.
   - Columns: business_date, drop_time, clerk_name, deposit_in_bank.

All charts: Altair, consistent color palette from components/__init__.py.

Cache all queries with @st.cache_data(ttl=300).
```

**Verification:** Browser test. Commit: `Task 4.3: store detail page`.

**Estimated session time:** 90 min.

---

## Task 4.4 — Field manager portfolio page

**What this accomplishes:** Field-manager-level view: their 5 stores
together vs portfolio targets, with side-by-side comparison.

**Inputs / Prerequisites:** Task 4.3 complete; `mart_field_manager_portfolio`
populated.

**Prompt for Claude Code:**

```text
Build pages/3_field_manager.py.

Accessible by owner (with dropdown to pick which FM) and field managers
(locked to their own name).

Layout:

Top: FM selector (owner only sees this; for field managers, lock to their name).

KPI cards: this FM's portfolio food cost %, labor cost %, total sales,
stores-in-target count. Compare against portfolio targets (20% / 25%) —
show "delta from target" as a tinted badge.

Side-by-side store comparison: 5-row mini-grid (or up-to-N rows
depending on the FM's cluster size). Columns: store, net_sales,
food_cost_pct (color), labor_cost_pct (color).

Trend chart (Altair): this FM's portfolio food cost % over the last 13
weeks, with a horizontal target line at 20%. Same for labor cost % at 25%
as a second chart.

Source: mart_field_manager_portfolio + mart_store_weekly.
```

**Verification:** Browser test. Commit: `Task 4.4: field manager page`.

**Estimated session time:** 60 min.

---

## Task 4.5 — Deploy to Streamlit Cloud (or Fly.io)

**What this accomplishes:** Dashboard reachable from a stable URL by all
5 users. Free tier on Streamlit Cloud is the default; Fly.io alternative
documented for private-URL preference.

**Inputs / Prerequisites:** Tasks 4.1–4.4 complete.

**Prompt for Claude Code:**

```text
Walk me through deploying to Streamlit Community Cloud step-by-step.
Also produce a Fly.io alternative as a fallback.

Outputs:

1. streamlit_app.py at repo root — shim that imports
   subway_ops.dashboard.app. Streamlit Cloud needs the entry at root.

2. requirements.txt at repo root generated via:
   uv export --frozen --no-dev > requirements.txt
   Document this in CLAUDE.md: regenerate after any pyproject.toml change.

3. docs/deployment_streamlit_cloud.md:
   - Sign in to share.streamlit.io with your GitHub account.
   - New app → main branch of subway-ops → entrypoint streamlit_app.py.
   - Paste secrets into the Streamlit Cloud UI (same values as
     .streamlit/secrets.toml — never commit the file).
   - Set app visibility to Public (in-app auth gates everything) or
     Private (only invited Streamlit users can view the URL — but invite
     management is annoying for 5 users; Public + in-app auth is simpler).
   - Bookmark the URL; add it as DASHBOARD_URL secret in GitHub Actions.

4. docs/deployment_flyio.md (alternative):
   - Install flyctl, fly auth login.
   - Dockerfile:

     FROM python:3.12-slim
     WORKDIR /app
     COPY requirements.txt .
     RUN pip install --no-cache-dir -r requirements.txt
     COPY . .
     EXPOSE 8501
     CMD ["streamlit", "run", "streamlit_app.py", \
          "--server.port=8501", "--server.address=0.0.0.0"]

   - fly launch (region: sjc), accept defaults (shared-cpu-1x, 256MB,
     ~$5/month).
   - fly secrets set DATABASE_URL=... etc.
   - fly deploy.
   - Get the *.fly.dev URL; bookmark; add as DASHBOARD_URL secret.

5. Update README.md with a "Deployment" section pointing to whichever
   doc was used.

Note: if you pick Fly.io, the system is no longer literally free —
$5/month — but the dashboard URL is unguessable.
```

**Verification:** App loads in browser; login works; data renders.

**Estimated session time:** 30 min (Streamlit) or 45 min (Fly.io).

---

## Task 4.6 — Polish: filters, exports, KPI thresholds

**What this accomplishes:** Dashboard becomes pleasant. State persists
across navigation; tables export to CSV; thresholds configurable without
code edits.

**Prompt for Claude Code:**

```text
Polish pass on the dashboard:

1. Persist filter state in st.session_state across pages. Selected week,
   selected store, status filter — all survive page navigation.

2. Add a "Download CSV" button (st.download_button) to every table on
   every page.

3. Move all KPI thresholds (food cost 22%, labor cost 28%, portfolio
   20%/25%, variance flagged $5, variance escalated $50) into config.py
   so changing them doesn't require a code edit. Reference them by name
   in every page.

4. Add a "Last refreshed" timestamp in the sidebar:
   SELECT MAX(refreshed_at) FROM mart_store_daily.
   Format as "12 minutes ago" using a small humanize helper.

5. Add a feedback widget at the bottom of every page:
   "Found a bug or have feedback? Email: {ALERT_EMAIL}"

6. Improve the chart styling: consistent color palette, formatted
   tooltips, axis labels in plain language ("Net sales ($)" not
   "net_sales").
```

**Verification:** Browser walkthrough. Commit: `Task 4.6: dashboard polish`.

**Estimated session time:** 60 min.

---

---

# Phase 5 — Reconciliation & Weekly Digest

---

## Task 5.1 — `mart_recon_weekly` + `ops_variance` table

**What this accomplishes:** The reconciliation mart that powers the
weekly review page. Status auto-computes from POS deposit vs operator-entered
actual bank deposit; defaults to "unverified" when no entry exists.

**Inputs / Prerequisites:** Phase 2.2 (ControlSheet) and Phase 3 complete.

**Prompt for Claude Code:**

```text
Build the reconciliation mart and the variance entry table.

Migration 014_recon.sql:

CREATE TABLE ops_variance_entries (
    restaurant_number TEXT NOT NULL REFERENCES ref_stores(store_number),
    week_end_date DATE NOT NULL,
    actual_bank_deposit NUMERIC(12,4) NOT NULL,
    entered_by TEXT NOT NULL REFERENCES ref_users(email),
    entered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    note TEXT,
    PRIMARY KEY (restaurant_number, week_end_date)
);

CREATE TABLE mart_recon_weekly (
    restaurant_number TEXT NOT NULL REFERENCES ref_stores(store_number),
    week_end_date DATE NOT NULL,
    pos_deposit_in_bank NUMERIC(12,4),
    actual_bank_deposit NUMERIC(12,4),
    variance NUMERIC(12,4) GENERATED ALWAYS AS
        (CASE WHEN actual_bank_deposit IS NOT NULL
              THEN pos_deposit_in_bank - actual_bank_deposit
              ELSE NULL END) STORED,
    status TEXT GENERATED ALWAYS AS (
        CASE
            WHEN actual_bank_deposit IS NULL THEN 'unverified'
            WHEN ABS(pos_deposit_in_bank - actual_bank_deposit) <= 5 THEN 'clean'
            WHEN ABS(pos_deposit_in_bank - actual_bank_deposit) <= 50 THEN 'flagged'
            ELSE 'escalated'
        END
    ) STORED,
    refreshed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (restaurant_number, week_end_date)
);

Note: pos_deposit_in_bank comes from
stg_controlsheet_weekly.cash_control_deposit_in_bank_total. Refresh
joins ControlSheet weekly to ops_variance_entries.

Module src/subway_ops/transform/mart_recon_weekly.py with
refresh(weeks_back: int = 8). Refreshes the last N weeks by default.

Update mart_store_weekly: add a recon_status column that joins from
mart_recon_weekly. Or: don't denormalize, and have the dashboard query
both.

Add the recon refresh to scripts/refresh_marts.py.

Tests: synthetic POS deposit + variance entry → assert correct status.
Cover all four status cases: unverified, clean, flagged, escalated.
```

**Verification:** Standard. Commit: `Task 5.1: mart_recon_weekly`.

**Estimated session time:** 75 min.

---

## Task 5.2 — Reconciliation review page (variance entry)

**What this accomplishes:** A page where the operator (or field manager)
reviews each store/week and enters the actual bank deposit only when it
differs from the POS-recorded amount. Audit-logged.

**Prompt for Claude Code:**

```text
Build pages/4_reconciliation.py.

Layout:

Filters at top:
- Week range selector (default: most-recently-closed week + 3 prior).
- Store filter (respects visible_stores()).
- Status filter (multiselect: unverified, clean, flagged, escalated).

Main table: one row per (store, week_end) from mart_recon_weekly joined
with ref_stores:
- Columns: store_number, store_name, week_end_date, pos_deposit,
  actual_deposit (EDITABLE), variance (display), status (chip),
  note (EDITABLE).
- Use st.data_editor with disabled=["store_number", "store_name",
  "week_end_date", "pos_deposit", "variance", "status"].
- Numeric type for actual_deposit; text for note.

On submit (single button "Save changes" below the table):
- Compute diff between current state and original data.
- For each changed row, write to ops_variance_entries via UPSERT.
- Wrap in a single transaction.
- The entered_by column gets the current user's email; entered_at via
  now() default.

After submit:
- Call refresh on mart_recon_weekly for affected weeks.
- Show a success toast with the count of rows updated.
- Re-render the table with fresh data.

For empty actual_deposit cells, treat as "no entry" (keep unverified
status). Allow blanking an existing entry (DELETE FROM ops_variance_entries
where actual_deposit is set to NULL in the editor — confirm via st.dialog
to avoid accidents).

Audit log: every insert/update to ops_variance_entries records user
email + timestamp (already in schema). No separate audit table needed.
```

**Verification:** Browser walkthrough: enter a variance, see status flip
to clean/flagged/escalated. Commit: `Task 5.2: reconciliation page`.

**Estimated session time:** 90 min.

---

## Task 5.3 — Weekly digest builder (HTML email body)

**What this accomplishes:** A function that produces a self-contained HTML
email summarizing the just-closed business week. Inline CSS, no JS, no
external images — renders in any email client.

**Prompt for Claude Code:**

```text
Build src/subway_ops/digest/builder.py with:

def build_digest(week_end: date) -> tuple[str, str]:
    """Returns (subject, html_body) for the weekly digest."""

Subject format:
"Subway weekly — week ending {Tue YYYY-MM-DD} — {n} flagged, {m} escalated"

HTML body sections (in order):

1. Header — title + date range (Wed YYYY-MM-DD to Tue YYYY-MM-DD).

2. Portfolio snapshot — total net sales, transactions, weighted food cost
   %, weighted labor cost %, vs prior week deltas (arrows + colored).

3. Targets dashboard — table:
   Metric | Current | Target | Status
   Each row: food cost %, labor cost %, store-level food cost target,
   store-level labor target. Color cells inline with style="background:..."

4. Reconciliation summary — counts by status, then a sub-table listing
   only escalated cases with: store, variance, status.

5. Field manager rollups — three tables (one per FM): their portfolio
   KPIs + a mini-grid of their stores.

6. Per-store table — all visible stores, same columns as the dashboard
   overview, color-coded.

7. Footer — "Open dashboard: {DASHBOARD_URL}" + a reply-to feedback
   address.

Style:
- Inline CSS only on every critical cell (heavy email clients strip
  <style> blocks).
- 600px-wide table layout for compatibility.
- Use a single <style> in <head> for typography (heavy clients drop it,
  inline backups handle critical cells).
- No external images. If you want logos, embed as base64 inline
  data:image/png;base64,... (optional — skip for v1).

Color tokens (also in components/__init__.py so the dashboard and
email match):
GREEN = "#22c55e"
YELLOW = "#eab308"
RED = "#ef4444"
NEUTRAL_BG = "#f9fafb"

Test in tests/test_digest_builder.py:
- Snapshot the rendered HTML against a fixture for a known week's data.
- Assert substring matches for: every store name, every status chip,
  the target percentages.
- Assert no <script> tags (security/email-compat).
- Assert all style attributes present on color-coded cells.
```

**Verification:**
```bash
uv run python -c "
from subway_ops.digest.builder import build_digest
from datetime import date
subj, body = build_digest(date(2025, 4, 22))
print(subj)
open('/tmp/digest.html', 'w').write(body)
"
# Open /tmp/digest.html in a browser to eyeball.
uv run pytest tests/test_digest_builder.py
git add -A && git commit -m "Task 5.3: weekly digest builder"
```

**Estimated session time:** 90 min.

---

## Task 5.4 — Wednesday digest sender + GitHub Actions cron

**What this accomplishes:** Email digest goes out every Wednesday morning
at 07:00 PT (06:00 PT during PDT) without you doing anything.

**Inputs / Prerequisites:** Tasks 5.1–5.3 complete; Gmail SMTP credentials
in GitHub secrets.

**Prompt for Claude Code:**

```text
Build the digest sender.

Migration 015_digest_log.sql:

CREATE TABLE ops_digest_log (
    week_end_date DATE PRIMARY KEY,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    recipient_count INTEGER NOT NULL,
    subject TEXT NOT NULL
);

scripts/send_weekly_digest.py:

1. Compute previous_business_week() → week_end (Tuesday).
2. Re-run mart_recon_weekly.refresh(week_end) and
   mart_store_weekly.refresh(week_end) for freshness.
3. If ops_digest_log already has a row for this week_end:
   print "Already sent {week_end} at {sent_at}", exit 0.
4. Call digest.builder.build_digest(week_end) → (subject, html_body).
5. Compute recipient list from ref_users where
   role IN ('owner','field_manager') AND is_active = true.
6. Send via Gmail SMTP using smtplib.SMTP_SSL("smtp.gmail.com", 465).
   Subject from builder; body as multipart/alternative with HTML and
   plain-text fallback (the plain-text is just the subject and a "View in
   browser: DASHBOARD_URL" line).
7. Record in ops_digest_log: (week_end, recipient_count, subject).
8. Print summary.

src/subway_ops/digest/sender.py: extract the SMTP send logic into a
reusable function send_email(to: list[str], subject: str, html: str,
text: str) -> None.

.github/workflows/weekly_digest.yml:

name: Weekly digest
on:
  schedule:
    - cron: "0 14 * * 3"   # 14:00 UTC Wednesday = 07:00 PT (PST)
                            # = 06:00 PT during PDT
  workflow_dispatch:
jobs:
  send:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --frozen
      - run: uv run python scripts/send_weekly_digest.py
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          FRESHCONNECT_API_CLIENT: ${{ secrets.FRESHCONNECT_API_CLIENT }}
          FRESHCONNECT_API_KEY: ${{ secrets.FRESHCONNECT_API_KEY }}
          GMAIL_USER: ${{ secrets.GMAIL_USER }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
          DASHBOARD_URL: ${{ secrets.DASHBOARD_URL }}
      - name: Notify on failure
        if: failure()
        run: uv run python scripts/notify_failure.py "weekly_digest"

Document in decisions.md: "DST drift on weekly_digest is accepted. Email
arrives between 06:00 and 07:00 PT depending on time of year. If exact
local time becomes important, replace the cron schedule with a worker
that self-schedules via business calendar."
```

**Verification:**
```bash
# Manually trigger via workflow_dispatch.
# Check inbox for the digest.
# Check ops_digest_log for the row.
# Re-trigger; confirm second run says "Already sent".
git add -A && git commit -m "Task 5.4: weekly digest sender + cron"
```

**Estimated session time:** 60 min.

---

---

# Phase 6 — University of Subway Pipeline

The uOS pipeline differs because input arrives via email, not API. Courses
change quarterly, so the parser stores course names as data, not as schema.

---

## Task 6.1 — Gmail API setup + token + tests

**What this accomplishes:** Read-only OAuth access to the Gmail inbox
containing uOS emails. After this, the system can list and read those
emails programmatically.

**Inputs / Prerequisites:** A Gmail account with a "UoS" label filtering
University of Subway emails.

**Prompt for Claude Code:**

```text
Set up Gmail API read-only access.

Outputs:

1. docs/gmail_setup.md — manual setup guide:
   - Go to console.cloud.google.com, create a new project.
   - Enable the Gmail API (APIs & Services → Library).
   - APIs & Services → Credentials → Create credentials → OAuth client ID.
     Type: Desktop application. Download the client_secret JSON.
   - Save the downloaded file as ~/.config/subway-ops/client_secret.json
     locally (do NOT commit).
   - Run scripts/gmail_get_token.py (see below) once to complete OAuth.
   - Base64-encode the resulting token.json:
       base64 -w0 token.json > token.b64
   - Add the contents of token.b64 as the GitHub Actions secret
     GMAIL_TOKEN_JSON_B64.
   - Set up a Gmail filter: From University of Subway → apply label "UoS",
     don't archive.

2. scripts/gmail_get_token.py — one-time local script:
   - Reads ~/.config/subway-ops/client_secret.json
   - Initiates OAuth flow via google_auth_oauthlib.flow.InstalledAppFlow
   - Scopes: https://www.googleapis.com/auth/gmail.readonly
   - Saves resulting credentials to ./token.json
   - Prints "Saved token.json. Base64-encode and add as GMAIL_TOKEN_JSON_B64."

3. src/subway_ops/uos/gmail_client.py:
   - Loads credentials from env: decodes GMAIL_TOKEN_JSON_B64 if present,
     else loads ./token.json locally.
   - Auto-refreshes the token if expired and re-saves it (writes back to
     ./token.json locally; in GitHub Actions it's ephemeral, refresh
     happens per run).
   - search(query: str, max_results: int = 50) -> list[Message]
   - get_message(msg_id: str) -> Message — fetches full payload including
     attachments.

4. tests/test_gmail_client.py — uses mocks for the Gmail API client
   (no live calls).

Add to pyproject.toml: google-api-python-client, google-auth-oauthlib,
google-auth-httplib2.
```

**Verification:**
```bash
# Locally:
uv run python scripts/gmail_get_token.py
# Browser opens, complete OAuth → token.json created.
uv run pytest tests/test_gmail_client.py
git add -A && git commit -m "Task 6.1: Gmail API setup"
```

**Estimated session time:** 60 min.

---

## Task 6.2 — uOS email parser + ingest

**What this accomplishes:** Parses the uOS training compliance email and
lands per-employee, per-course rows in staging. Schema-flexible — courses
change quarterly, but we don't change schema for that.

**Inputs / Prerequisites:** Task 6.1 complete. You'll need to drop a real
uOS email into `tests/fixtures/uos_sample_email.eml` for Claude Code to
infer structure.

**Prompt for Claude Code:**

```text
Before writing parsing logic, I need to provide a sample uOS email. I'll
save one as tests/fixtures/uos_sample_email.eml (raw .eml format) and the
attachment (if any) as tests/fixtures/uos_sample_attachment.pdf or .csv.

Based on what I provide, inspect the structure and build the parser.

Migration 016_uos.sql:

CREATE TABLE raw_uos_emails (
    id BIGSERIAL PRIMARY KEY,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    gmail_message_id TEXT UNIQUE NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    subject TEXT,
    attachment_count INTEGER,
    payload JSONB NOT NULL
);

CREATE TABLE stg_uos_compliance (
    restaurant_number TEXT NOT NULL REFERENCES ref_stores(store_number),
    report_date DATE NOT NULL,
    employee_name TEXT NOT NULL,
    course_name TEXT NOT NULL,
    completion_status TEXT NOT NULL,
        -- 'complete' | 'overdue' | 'pending'
    completed_at DATE,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (restaurant_number, report_date, employee_name, course_name)
);

CREATE INDEX idx_stg_uos_store_date ON stg_uos_compliance (restaurant_number, report_date);

Module src/subway_ops/uos/parser.py:
- Detect format from MIME type: PDF attachment, HTML body, or CSV
  attachment.
- For PDF: use pypdf or pdfplumber to extract tables.
- For HTML body: BeautifulSoup or lxml to parse the table.
- For CSV: pandas.read_csv.
- Extract per-store, per-employee, per-course rows.
- Map status strings flexibly:
    'Complete' / 'Completed' / '✓' → 'complete'
    'Overdue' / 'Past Due' / 'Expired' → 'overdue'
    'Pending' / 'Not Started' / 'In Progress' → 'pending'
- Be lenient on rows that don't match — log unrecognized rows to
  ops_job_runs.metadata as JSON, don't crash.

Module src/subway_ops/uos/ingest.py:

def ingest_recent(days: int = 7) -> int:
    """Pull new UoS emails from Gmail and parse into stg_uos_compliance.

    Wraps in track_job("ingest_uos").
    Query: label:UoS newer_than:{days}d
    Skips messages already in raw_uos_emails (gmail_message_id UNIQUE).
    Returns rows upserted.
    """

Add a uos_pull workflow .github/workflows/uos_pull.yml:
- Cron: 11:00 UTC daily (04:00 PT, 1 hour after daily_pull).
- Runs scripts/uos_pull.py which calls ingest_recent().
- Pass GMAIL_TOKEN_JSON_B64 from secrets.

Update daily_pull.py to NOT include uOS (it has its own workflow because
the token rotation needs occasional intervention).

Add pypdf or pdfplumber and beautifulsoup4 to dependencies.
```

**Verification:**
```bash
# Drop the sample email first:
cp ~/Downloads/uos_report.eml tests/fixtures/uos_sample_email.eml

# Then have Claude Code build the parser.
uv run pytest tests/test_uos_parser.py
uv run python -c "
from subway_ops.uos.ingest import ingest_recent
print(ingest_recent(days=30))
"
git add -A && git commit -m "Task 6.2: uOS email parser + ingest"
```

**Estimated session time:** 90 min (after fixture is in place).

---

## Task 6.3 — Compliance widget in dashboard

**What this accomplishes:** Training compliance % shows up as a column on
the owner overview, a tab on the store detail, and a section in the
weekly digest.

**Prompt for Claude Code:**

```text
Add training compliance views.

1. Data helper in dashboard/data.py:

@st.cache_data(ttl=300)
def get_compliance_summary(report_date: date, store_filter: list[str] | None) -> pd.DataFrame:
    """Per-store compliance %: complete cells / total cells from
    stg_uos_compliance for the most recent report_date on or before
    the given date.
    """

@st.cache_data(ttl=300)
def get_store_compliance_detail(store_number: str, report_date: date) -> pd.DataFrame:
    """Per-employee, per-course detail for a store + report date."""

2. Update pages/1_owner_overview.py:
   - Add "Training %" column to the store grid.
   - Color: GREEN ≥ 90%, YELLOW 80–90, RED < 80.

3. Update pages/2_store_detail.py:
   - Add a "Training" tab.
   - Top: weekly trend of compliance % over the last 13 weeks (Altair
     line chart).
   - Below: per-employee compliance table for the latest report_date.
   - Below: list of overdue items sorted by days-overdue desc.

4. Update digest builder (src/subway_ops/digest/builder.py):
   - Add a "Training compliance" section after the per-store table.
   - Highlight stores below 90% with a red row.
   - Skip the section if no uOS data exists for the week.

5. Tests in tests/test_digest_builder.py: add a scenario with synthetic
   compliance data, assert the section renders.
```

**Verification:** Browser walkthrough. Commit: `Task 6.3: compliance widget`.

**Estimated session time:** 45 min.

---

---

# Phase 7 — Hardening & Operate

---

## Task 7.1 — Test coverage pass + CI green

**What this accomplishes:** Every module has tests; CI runs them on every
PR. After this, you'll know within 2 minutes if any change breaks anything.

**Prompt for Claude Code:**

```text
Audit and improve test coverage.

Run uv run pytest --cov=src/subway_ops --cov-report=term-missing and
identify any module under 80% coverage. For each, add tests focused on:

- Edge cases (empty inputs, malformed responses, dates at week boundaries).
- Unhappy path (parse failures, rate limits, auth failures).
- Idempotency (re-running ingest produces no duplicates).

Set up GitHub Actions CI workflow .github/workflows/ci.yml:

name: CI
on:
  pull_request:
  push:
    branches: [main]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --frozen
      - run: uv run ruff check .
      - run: uv run mypy src/
      - run: uv run pytest --cov=src/subway_ops --cov-fail-under=75

Fail if any of: ruff, mypy, pytest coverage < 75%.

Add a status badge to README.md.
```

**Verification:**
```bash
uv run pytest --cov=src/subway_ops --cov-report=term-missing
# Push to a branch, open PR, verify CI runs and passes.
git add -A && git commit -m "Task 7.1: test coverage + CI"
```

**Estimated session time:** 90 min.

---

## Task 7.2 — Observability: structured logs + ops_job_runs surfaced

**What this accomplishes:** When something breaks at 3am, you can see what
happened. Job history visible in the dashboard. One-click rerun for failed
jobs.

**Prompt for Claude Code:**

```text
Add observability.

1. Adopt structlog throughout:
   - Replace remaining print() and stdlib logging calls.
   - Configure JSON output in prod (APP_ENV=prod), pretty output in dev.
   - Default keys: timestamp, level, event, plus contextual keys passed
     via .bind().

2. New dashboard page pages/5_system_status.py (owner-only):
   - List of recent ops_job_runs (last 50): job_name, started_at,
     duration_seconds, status, rows_written, error_text snippet.
   - Color-coded status column.
   - Filter by job_name and status.
   - Auto-refresh every 60 seconds (st.fragment with run_every).
   - For failed jobs: a "Re-run" button that opens the matching GitHub
     Actions workflow_dispatch URL in a new tab. (Don't try to trigger
     via API — manual is simpler and sufficient.)

3. Add to dashboard/auth.py a check: if user_role != 'owner', the system
   status page is hidden from the sidebar.
```

**Verification:** Browser walkthrough; trigger a failure to see it appear.

**Estimated session time:** 60 min.

---

## Task 7.3 — Runbook for every recurring failure mode

**What this accomplishes:** A document you (or anyone) can hand to a
successor in two years and they can operate the system without re-deriving
the design.

**Prompt for Claude Code:**

```text
Write docs/runbook.md covering every recurring failure mode.

For each scenario, structure as:
- Symptom (what you see)
- Cause (most likely)
- Diagnosis (commands to confirm)
- Fix (specific steps)

Scenarios to cover:

1. FreshConnect 401 (key revoked or rotated)
2. FreshConnect 429 (daily rate limit hit during a job)
3. FreshConnect 5xx persistent (Subway-side outage)
4. Daily pull failed in GitHub Actions
5. Weekly digest didn't arrive Wednesday morning
6. Dashboard shows "Connection refused" or hangs on load
7. Dashboard auth failing for a known user
8. New store onboarded — what to do (edit seed/stores.csv, re-seed)
9. Store closed / decommissioned — set is_active=false in ref_stores
10. Field manager rotated — what to do
11. Supabase free tier paused (90-day inactivity — shouldn't happen but
    document the recovery)
12. Gmail token expired (uOS pipeline broken)
13. uOS email format changed (parser broke)
14. Subway changed an API response shape (Pydantic strict mode caught it)
15. New quarter — uOS course list changed (parser tolerates this; no
    action needed)
16. Streamlit Cloud app cold-started and timed out

Each section: 50–150 words, with the actual commands.

Also write docs/operations_calendar.md listing all scheduled events:
- Daily pull: 10:00 UTC (03:00 PT)
- Refresh marts: every 4 hours
- uOS pull: 11:00 UTC (04:00 PT)
- Weekly digest: 14:00 UTC Wednesday (07:00 PT, drifts to 06:00 PT in PDT)
- Backfill status check: monthly on the 1st (manual)
- Audit reconciliation: quarterly (manual)
- FreshConnect credential rotation: annual (manual, regenerating
  invalidates the previous key, so coordinate with anyone else using it)
```

**Verification:** Read the runbook; pick three scenarios at random and
verify the commands actually work.

**Estimated session time:** 60 min.

---

## Task 7.4 — Backfill verification + audit reconciliation

**What this accomplishes:** Spot-check 12 months of history against LiveIQ's
own reports. Catch any silent data gaps before the system is declared
production-ready.

**Prompt for Claude Code:**

```text
Build scripts/audit_backfill.py.

The script produces an audit report for the last 12 months:

1. Print 5 randomly-sampled (store, week_end_date) combinations with:
   - stg_controlsheet_weekly.net_sales_total for that store/week
   - URL where the operator can open the LiveIQ ControlSheet report for
     manual cross-check (build it from the LiveIQ pattern; if the URL
     isn't deterministic, just print "Open LiveIQ → Reporting →
     ControlSheet for store {n}, week {date}").

   Operator opens LiveIQ in one window and the script output in another;
   eyeball the numbers match.

2. Print summary statistics for the audit window:
   - Number of (store × business_date) cells in mart_store_daily.
   - Expected count: active stores × days. Any deficit flagged with the
     specific (store, date) gaps.
   - Number of (store × week_end_date) cells in mart_store_weekly.
   - Expected: active stores × weeks. Same gap analysis.
   - Days with zero sales (likely store closures or data gaps;
     cross-reference ref_stores.opening_date and is_active).

3. Output to docs/audit_<YYYY-MM-DD>.md so the audit is preserved as a
   document.

After running, capture any genuine issues in decisions.md and resolve
before declaring Phase 7 complete. Re-run the audit until it's clean.
```

**Verification:**
```bash
uv run python scripts/audit_backfill.py
cat docs/audit_*.md
# Cross-check 5 samples in LiveIQ.
git add -A && git commit -m "Task 7.4: backfill audit"
```

**Estimated session time:** 60 min for the script; multiple hours for the
manual cross-checks.

---

---

## What Comes After Task 7.4

When all 37 tasks are complete, the system moves from build mode to operate
mode. Maintenance is documented in `docs/runbook.md`.

Future extensions (Phase 8+):

- **Transaction-detail analytics** — PLU mix shifts, discount usage by
  employee, void patterns. Use `TransactionDetails` endpoint via
  `scripts/backfill_deep.py`.
- **Anomaly detection** — statistical outlier alerts on daily KPIs.
- **SubVentory parity check** — compare a week of SubVentory reports
  against InventoryMovement + Wisr; ingest SubVentory only if gaps exist.
- **System API** — expose system data via a thin FastAPI layer so the
  trading operation can pull operational cash-flow signals when sizing
  positions.
- **Mentor / lender view** — read-only with a non-PII redaction layer.
- **Dubai-entity deployment** — if the operation relocates, re-host with
  data residency outside the US.

---

---

# PART III — APPENDICES

---

## Appendix A — `CLAUDE.md` (full text)

The literal contents of `CLAUDE.md` for the repo. Task 0.2 pastes this
verbatim.

```markdown
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
  `track_job(name)` context manager.
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
```

---

## Appendix B — Environment Variables

Required across all environments:

| Variable | Used by | Source |
|---|---|---|
| `DATABASE_URL` | All Python | Supabase connection string |
| `FRESHCONNECT_API_CLIENT` | `freshconnect/client.py` | LiveIQ FreshConnect |
| `FRESHCONNECT_API_KEY` | `freshconnect/client.py` | LiveIQ FreshConnect |
| `GMAIL_USER` | `digest/sender.py`, `notify_failure.py` | Your Gmail account |
| `GMAIL_APP_PASSWORD` | Same | Google → Security → App Passwords |
| `GMAIL_TOKEN_JSON_B64` | `uos/gmail_client.py` | OAuth flow, base64-encoded |
| `ALERT_EMAIL` | `notify_failure.py` | Where failure emails go |
| `DASHBOARD_URL` | `digest/builder.py` | Streamlit Cloud URL |
| `APP_ENV` | `config.py` | `dev` locally, `prod` in CI |

Stored in three places (matching values):
- `.env` (local dev, gitignored)
- GitHub Actions secrets (for cron jobs)
- Streamlit Cloud secrets (for dashboard)

---

## Appendix C — Common Pitfalls

**API typo: `resturantNumber`.** The Fresh Connect API uses both
`restaurantNumber` and `resturantNumber` (the latter is a typo) in different
responses. Pydantic models must accept both via aliases.

**weekEndDate confusion.** The ControlSheet sample shows
`"weekEndDate": "2025-04-14T00:00:00"` at the envelope level but
`"weekEndDate": "2025-04-15T00:00:00"` inside the data array. April 14 was a
Monday, April 15 a Tuesday. The inner one is the actual business week-end.
Treat envelope-level as the request echo, inner-level as the data.

**Streamlit Cloud cold start.** Free-tier Streamlit Cloud apps pause after
inactivity and take 10–30 seconds to wake. Don't link to it from emails as
if it's an instant-load page; manage expectations in digest copy.

**Supabase 90-day pause.** Free-tier Supabase projects pause after 90 days
of no API activity. Our daily pull job hits the database every day, so this
won't trigger. But document why a sudden silence breaks everything.

**DST and the cron schedule.** Cron times are UTC. The 14:00 UTC Wednesday
digest arrives at 07:00 PT during PST (Nov–Mar) and 06:00 PT during PDT
(Mar–Nov). Document in `decisions.md`. If you need exact local time, switch
to a worker that self-schedules via `business_date_now` instead of cron.

**Rate limit reset time.** Per the FreshConnect docs, the daily limit
resets at midnight UTC — 16:00 or 17:00 PT depending on DST. A "retry
tomorrow morning" at 03:00 PT might still be the same UTC day. Wait until
after 17:00 PT, or trigger retries via `workflow_dispatch` manually.

**Decimal vs float.** Pydantic v2 coerces `"10.23"` cleanly to `Decimal` but
loses precision via `float`. Every money field is `Decimal`. No exceptions.

**Pydantic `extra="forbid"` strictness.** When Subway adds a field, our
parser fails loudly — by design. Fix is to update the model and add a test
fixture. Don't relax `extra` to `allow` to silence it.

**ControlSheet column count.** Yes, `stg_controlsheet_weekly` will have
~120 columns. This is intentional. Postgres handles it. The dashboard
queries only what it needs.

**GitHub Actions cron drift.** GitHub explicitly notes scheduled workflows
can be delayed during high load — usually by seconds, occasionally by 10+
minutes. The Wednesday digest scheduled for 14:00 UTC may actually fire at
14:10 UTC. Not a problem for our use case; flag it if precise delivery time
becomes important.

**Rate limit numbers are unknown.** The docs don't state the daily call
limit. Discover it empirically (Task 1.3 discovery script will probe).
Until known, the backfill plan assumes conservatively ~200 calls/day per
credential.

---

## Appendix D — Hosting Alternatives

The default deployment puts the Streamlit app on Streamlit Community Cloud
(free). The URL is reachable from anywhere; access is gated by the in-app
auth from `streamlit-authenticator`. This is fine for most operators.

**If you'd rather the URL itself be private**, the alternative is a
$5/month Fly.io VM. Setup outline:

1. Install `flyctl` and `fly auth login`.
2. In repo root: `fly launch` — chooses a region (sjc / sea), provisions
   the smallest VM (shared-cpu-1x, 256 MB), generates `fly.toml`.
3. Dockerfile for Streamlit:
   ```dockerfile
   FROM python:3.12-slim
   WORKDIR /app
   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt
   COPY . .
   EXPOSE 8501
   CMD ["streamlit", "run", "streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
   ```
4. Set secrets via `fly secrets set DATABASE_URL=...` etc.
5. Configure Fly.io's IP allow-list (if you have static IPs) or rely on
   in-app auth as the only access gate.

Cost: ~$5/month for the VM. Trade-off: you give up Streamlit Cloud's
zero-ops convenience, gain a private URL and faster cold-starts.

A third option is **self-hosted on the operator's office or home network**
via Tailscale + a small Mac mini or Linux box. Cost: hardware + electricity.
Trade-off: maximum control, lowest recurring cost, highest operational
burden. Not recommended unless you already operate other home-network
services.

---

## Appendix E — Glossary

- **Fresh Connect** — Subway's franchisee data API exposing LiveIQ data.
- **LiveIQ** — Subway's POS/operations platform (the source system).
- **WISR** — Weekly Inventory & Sales Report; Subway's per-store weekly
  food-cost analysis.
- **PLU** — Price Look-Up code; identifies a specific menu item.
- **uOS** — University of Subway; Subway's required training platform.
- **business date** — A Subway business day (02:00–01:59 local time). The
  `date` field on Fresh Connect daily endpoints is already business-aligned.
- **week_end_date** — The Tuesday that ends a Subway business week. The
  Fresh Connect API uses this consistently as a parameter and field.
- **FM** — Field manager. Three on the operation: Maria, James, Kevin.
- **MUO** — Multi-unit operator. A franchisee running multiple stores.
- **IPC** — Independent Purchasing Cooperative; Subway's franchisee-owned
  supply chain entity.
- **mart** — A denormalized, query-optimized table built by transforming
  staging tables. Read-heavy, refresh-on-schedule.
- **staging** — A typed, deduplicated layer between raw payloads and marts.
- **idempotent ingest** — An ingest that can be safely re-run without
  duplicating data, because it uses ON CONFLICT DO UPDATE on a natural key.
- **track_job** — Context manager that wraps every ingest/refresh, recording
  start time, duration, status, and error in `ops_job_runs`.

---

## End of Playbook
