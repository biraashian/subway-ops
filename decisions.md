# Architectural decisions

Append-only log of significant design choices. Each entry: context,
decision, consequences. Newest at the bottom.

---

## 2026-05-11 — Language and stack

**Context:** Operator preference for Python; need free-tier-only hosting;
need declarative dashboards.

**Decision:** Python 3.12, Streamlit, Supabase Postgres, GitHub Actions
for orchestration.

**Consequences:** Locked into Python ecosystem; Streamlit's auth
limitations accepted; daily-batch architecture rather than real-time.

---

## 2026-05-11 — Business calendar

**Context:** Subway operates on a non-midnight day boundary and a
non-Monday week boundary. Every downstream KPI rolls up by business
date or business week, so the definition has to be unambiguous and
codified in one place.

**Decision:** Business day is 02:00–01:59 local (America/Los_Angeles for
all 15 stores). Business week is Wednesday through Tuesday. The Fresh
Connect API's `date` field is already business-date-aligned and its
`weekEndDate` is always a Tuesday; both are trusted and not re-derived.

**Consequences:** All calendar logic flows through `subway_ops.calendar`.
Any time we compute "today" or "this week" for reporting, we do it via
those helpers, never via `datetime.date.today()`. If a future store opens
outside America/Los_Angeles, the timezone assumption must be revisited.

---

## 2026-05-11 — Bank reconciliation model

**Context:** 15 stores deposit to multiple banks; building per-bank CSV
parsers exceeds the value of the variance signal at our current scale.

**Decision:** We do not ingest bank-issued deposit confirmations. The
dashboard surfaces the POS-recorded `depositInBank` from ControlSheet. A
variance entry form exists for operators to record actual bank-deposited
amounts only when they differ from the POS-recorded amount.

**Consequences:** We catch over/short via human-in-the-loop, not
automation. Acceptable for v1; revisit if variance frequency grows or if
we onboard a single banking partner that makes automated reconciliation
cheap.

---

## 2026-05-12 — Database layer: SQLAlchemy engine + psycopg v3 driver

**Context:** Task 0.5 needed a single canonical way to talk to Postgres
from Python. The existing `seed_reference.py` used psycopg directly; the
playbook prescribes a SQLAlchemy engine with raw SQL via `text()`. Two
small choices fall out of that prescription.

**Decision:**
- One process-wide SQLAlchemy engine, built lazily by `get_engine()`,
  with `pool_pre_ping=True` to survive Supabase idle disconnects. Most
  queries go through `execute_sql(sql, params)` (eager fetch, parameter-
  bound `text()`); ORM `Session` is offered but not required.
- `get_engine()` rewrites `postgresql://` and `postgres://` URLs to
  `postgresql+psycopg://` so SQLAlchemy uses psycopg v3 (the binary we
  pin) instead of psycopg2 (not installed). Supabase hands us the bare
  scheme by default, so without this rewrite every fresh checkout would
  break on the first DB call.
- Migration runner lives at `src/subway_ops/db/migrate.py` with a thin
  CLI wrapper in `scripts/migrate.py`. Migrations are recorded with a
  SHA-256 checksum in `ops_migrations`; a mismatched checksum aborts the
  run loudly.

**Consequences:** All future ingest / mart / dashboard code uses the
same engine and `execute_sql` helper — no ad-hoc psycopg connections.
The old `_schema_migrations` table from the bootstrap seed script is
abandoned; we never query it again, and migration 001 is idempotent so
the first run of the new runner re-records it under `ops_migrations`
without side effects.

---

## 2026-05-12 — Model drift caught by Task 1.3 discovery

**Context:** Task 1.3 ran the discovery script against the live FreshConnect
API for store 4092 with `business_date = 2026-05-11` and
`weekEndDate = 2026-05-05`. Two of fifteen endpoints failed Pydantic
validation; the rest (including the giant `controlsheet` and `wisr`
envelopes) parsed cleanly.

**Decision:** Treat the live response as authoritative whenever it diverges
from the JSON sample in `APIUrlsDocumentation.pdf`. The doc's field-name
table generally matched live; the embedded JSON samples were the ones out
of date.

- `DailyTimeclock.data[]`: the doc sample uses `hours` / `totalAdj` /
  `totalBeforeAdj`; live API and the doc's own field-name table use
  `hoursBeforeAdj` / `hoursAfterAdj` / `adjAmount`. Switched
  `TimeclockEntry` to the live names — no aliasing of the doc-sample keys
  because they never appear in production.
- `TransactionDetails.data[].tenders[]`: doc sample uses `cardLastFour`;
  live API uses `cardLast4` and emits `null` for non-card tenders.
  `Tender.card_last_four` now accepts both spellings via `AliasChoices`
  and is `Optional[str]`.

**Consequences:** Models track the live API rather than the PDF samples.
If FreshConnect ever publishes corrected sample JSON we'll likely see
parsing errors from the new shape — at which point we re-run the
discovery script (15 calls, ~30 seconds) and reconcile. Recorded
fixtures live at `tests/fixtures/recorded/` (gitignored) and
`tests/test_recorded_fixtures.py` re-parses them whenever they exist so
drift is caught locally before it hits ingest.

---

## 2026-05-13 — Dashboard auth: streamlit-authenticator + ref_users

**Context:** Phase 4's dashboard needs login, per-role visibility, and a
sign-out flow. Task 0.3 already seeded `ref_users` with bcrypt-hashed
passwords, so the storage layer is in place.

**Decision:** Use `streamlit-authenticator` v0.3+ rather than rolling our
own session/cookie code. The library handles bcrypt verification and
cookie-signed sessions; we pass `auto_hash=False` because `ref_users`
already stores hashed passwords, and feed it credentials built from a
live `SELECT` at session start. Cookie signing key comes from
`.streamlit/secrets.toml` in local dev and from the
`AUTH_COOKIE_KEY` env var (Streamlit Cloud / CI secrets) in prod.

Visibility: `auth.visible_stores(user, all_stores)` returns the full
roster for the `owner` role or for any user whose `assigned_stores` list
is NULL (the seed allows this as an admin override), otherwise filters
to the cluster. Pages read `st.session_state["assigned_stores"]` rather
than re-querying.

**Consequences:** Streamlit + streamlit-authenticator added to runtime
deps (no dev-only ceiling — the dashboard ships to Streamlit Cloud).
Page files under `src/subway_ops/dashboard/pages/` start with a digit
per Streamlit's nav-order convention; ruff's `N999` is silenced for
that directory via `per-file-ignores`. If we ever swap auth (SSO,
SAML, etc.) the surface is small: replace `make_authenticator()` and
the session-state shape in `_bootstrap_session`.

## 2026-05-13 — Weekly digest cron: DST drift is accepted

**Context:** The weekly digest fires from a GitHub Actions cron at
`0 14 * * 3` (14:00 UTC every Wednesday). GHA crons are pinned to UTC
with no built-in calendar awareness, so the wall-clock arrival time
in America/Los_Angeles shifts between **07:00 PT during PST** and
**06:00 PT during PDT**.

**Decision:** Accept the one-hour drift. The digest is a leisurely
weekly read, not a time-critical alert; operators don't care whether
it lands at 06:00 or 07:00 local. The Wednesday placement (right after
the Subway business week closes Tuesday night at 01:59 local) is the
load-bearing part of the schedule.

**Consequences:** No worker-based self-scheduler today. If exact
local-time delivery ever becomes important (e.g., the digest gets
tied to a specific opening-shift handoff window), replace the GHA
cron with a worker that wakes daily and self-schedules via
`subway_ops.calendar`. The idempotency guard in
`scripts/send_weekly_digest.py` (`ops_digest_log` PK on `week_end`)
already protects against double-sends if a worker and the cron ever
run concurrently during a migration.
