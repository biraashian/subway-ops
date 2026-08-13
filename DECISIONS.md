# Decisions

Append-only. `/bench` appends here; `/sweep` diffs live state against it.

Two sections. **Inherited** are the Burst v0.2 harness decisions carried in
from the Verity build — they govern *how* we work and are in force here except
where noted. **Subway Ops** are this institution's own decisions, D-016 onward,
continuing the same number space because the inherited ones are not superseded.
Below both sits the original dated log from the pre-Burst build, kept verbatim
as the record of why the data layer looks the way it does.

---

## Inherited from Burst v0.2 (Verity era 2)

| ID | Decision | Status here |
|---|---|---|
| D-001 | Spec-driven build as one stack inside Claude Code | **In force** |
| D-002 | `/close` is founder-commanded and atomic | **In force** |
| D-003 | The gate-enforced per-task journal is the system of record | **In force**, amended by D-023 |
| D-004 | Red post-merge → revert first, never fix-forward | **In force** |
| D-005 | WIP limit of 3 in "built, awaiting audit" | **In force** |
| D-006 | `/next` is the policy evaluator, run at every session open | **In force** |
| D-007 | The spec is the organizing unit; specs get their own ID space and lifecycle | **In force** (no CT stream ever existed here) |
| D-008 | The board is the single pane; runway floor of 3 | **In force** |
| D-009 | A dependency-ordered source queue feeds `/spec` | **In force**, as `codex/12-PROMPTS/` |
| D-010 | Greenfield entry; no adopt-and-audit | **Bent** — see D-016 |
| D-011 | Blue-green cutover; legacy is a read-only harvest corpus | **Void** (no cutover). The harvest-don't-copy rule applies to `legacy/` |
| D-012 | Eight environments on two axes | **Void** — Verity-specific |
| D-013 | Critical-path pull-forward of four components | **Void** — Verity-specific |
| D-014 | Pipeline mechanics: serial merge queue, V&V split, R-503 | **In force** |
| D-015 | v1 built completely; v2 quarantined | **Void** — Verity-specific |

---

## Subway Ops decisions

## D-016 — D-010 is bent: the data layer is retro-specced, not rebuilt
- **When:** 2026-08-11 (founder call).
- **Reasoning:** D-010 rules out adopt-and-audit because it produces "fake-done:
  green checkmarks over unvetted decisions." That reasoning targets *unspecced
  layers sitting under specced ones*. The subway data layer is not unvetted in
  that sense: 490 passing tests, ruff and mypy green, 15 endpoints verified
  against the live API in a recorded discovery pass, 19 applied migrations, and
  15 months of ingested history. It lacks **specs**, not **verification**. This
  domain is also an order of magnitude simpler than the one Burst was built for.
- **Guard against fake-done:** retro-spec ACs are written from the codex and
  from observed behavior. Wherever existing code and the spec disagree, that is
  a **bench item** — never a silent spec amendment to match the code.
- **Ruled out:** full greenfield per RUNBOOK-CUTOVER (rebuilds 15 verified
  endpoints and 19 migrations for no proportionate gain).
- **Reopen if:** three or more retro-specs produce bench items that reveal the
  layer's design was actually wrong — then that layer graduates to greenfield.

## D-017 — Codex first: no new spec without a design authority above it
- **When:** 2026-08-11 (founder call).
- **Reasoning:** the read-upward rule needs something above `specs/`. The
  existing `SUBWAY_OPS_BUILD_PLAYBOOK.md` only covers the original reporting
  scope and is shaped as a build guide, not an authority. The new domain —
  what a territory is, what a manager owns, how a bonus computes, what an
  orientation must legally record — exists only in the founder's head.
- **Ruled out:** extending the playbook (wrong shape); letting specs be the top
  layer for new areas (weakens read-upward exactly where the domain is least
  defined, which is where drift comes from).
- **Reopen if:** never for era 1 of this system.

## D-018 — Discord is the single staff channel; scheduling is in scope
- **When:** 2026-08-11 (founder call).
- **Reasoning:** staff comms are currently split across three channels; the
  founder wants one, carrying communication, schedule, and real-time updates.
  Scheduling was not in the original scope and is the highest-leverage addition
  because it closes the labor loop: a report says last week was over budget, a
  schedule checked against budget says Saturday is over while it is still
  Wednesday.
- **Ruled out:** WhatsApp (weak for hosting guides, video, and searchable
  content; per-conversation cost; outbound rate limits); staying split.
- **Consequences:** the org is not on Discord yet, so rollout is a real change-
  management task, piloted on one territory before going wide.

## D-019 — A new mobile-first web app; Streamlit retires
- **When:** 2026-08-11 (founder call).
- **Reasoning:** crew need a personal page — shifts, KPI, certificates,
  training, photo upload — that opens on a phone in front of a health
  inspector. Streamlit cannot do that: auth is a CSV of password hashes, there
  is no mobile layout, and file upload is clumsy. Stack is FastAPI + Jinja2 +
  HTMX, server-rendered, so the entire existing Python data layer is reused with
  no second toolchain. Deployed on Fly.io, where the Dockerfile already points.
- **Ruled out:** keeping Streamlit and adding a second crew app (two codebases,
  two logins, contradicts the single-place goal); Discord-only for crew (no page
  to show an inspector).
- **Consequences:** Streamlit runs until the new app reaches parity, then goes.
  `ref_users.role` grows `store_manager`, `office`, `crew`.

## D-020 — Monarch is bank truth
- **When:** 2026-08-11 (founder call).
- **Reasoning:** Monarch already aggregates the accounts, so deposits and
  settlements reconcile against it rather than against a second aggregation we
  would have to build and maintain.
- **Consequences:** Monarch has no official public API, so this is a scheduled
  **export import**, not a live feed. That import is a first-class ingest with
  its own `raw_`/`stg_` pair and `track_job` wrapper.
- **Reopen if:** Monarch ships an API, or the export cadence proves too coarse.

## D-021 — Capture is photo + AI extraction + human confirm; never auto-post
- **When:** 2026-08-11 (founder call).
- **Reasoning:** the existing cash-drop spreadsheet fails on ease of use, and
  data entry is the friction that stops reconciliation happening at all. A
  manager photographs the receipt; a vision model proposes amount, date, and
  store; a person confirms before anything posts.
- **Non-negotiable:** the model never writes to a staging table directly. Both
  the source image and the raw model output are retained for audit, so any
  posted number can be traced back to the pixels it came from.
- **Ruled out:** manual entry (same friction as today); statement-import-only
  (no digital source exists for cash drops).

## D-022 — Payroll is a locked report, not an integration
- **When:** 2026-08-11 (founder call).
- **Reasoning:** the timecard custody chain is office adjusts → founder
  approves → payroll. After approval the system emits an approved, immutable
  hours report and office staff key it into payroll.
- **Consequences:** zero payroll integration to build or maintain, at the cost
  of a re-keying step after approval. The report must therefore be laid out for
  transcription, and the approved rows must be immutable so the keyed figures
  can always be traced back.
- **Reopen if:** re-keying errors show up, or the provider offers a usable API.

## D-023 — The journal lives in-repo; the gate ignores it (amends D-003)
- **When:** 2026-08-11.
- **Reasoning:** Burst keeps `journal/` in a sibling repo specifically so
  `assert_worktree_clean` cannot see the uncommitted entry written moments
  before the gate runs. Subway has no Zone C and no secrecy split, and one
  clone carrying the full record is worth more here than a separate repo.
- **Decision:** `journal/T-####.md` is in-repo and committed. `verify.sh`'s
  worktree-clean assertion excludes `journal/` and `test_logs/`; nothing else
  is excluded, so the check still catches the case it was written for — an
  uncommitted edit to the gate script riding along through a checkout.
  `test_logs/` is repo-local and gitignored, since it is regenerable machine
  output.
- **Ruled out:** a sibling journal repo (two clones to keep in sync for a
  solo operator); gitignoring the journal (unversioned; defeats the point).

---


## D-024 — Schema drift is declared, not merely detected (was B-0022)
- **Decision:** a task that intends to change the schema declares its expected
  drift in `.drift/expected/T-####.txt`. The gate passes when observed drift
  matches the declaration exactly, and fails on undeclared drift **or** on a
  declaration that no longer matches. Recorded 2026-08-13.
- **Reasoning:** the check as written exits 1 on any drift, so no migration
  task could ever reach a green pre-merge — it blocked T-0003 on the first
  task that touched a migration. The check's own message already said drift
  "must be INTENDED"; it simply had no way to record that a human agreed.
- **Ruled out:** tracing drift to migrations on the branch (automatic, but
  blind to an ALTER a migration makes by accident — the case most worth
  catching); demoting drift to a warning at pre-merge (removes the review
  surface exactly where review happens).
- **Consequences:** the declaration is a reviewable artifact in the diff. A
  stale declaration reds the gate, so it cannot rot silently.
- **Reopen if:** declarations become copy-paste noise rather than a read.

## D-025 — Tests run against a containerised Postgres, never production (was B-0001)
- **Decision:** DB-backed tests run against Postgres in a container, with
  migrations applied per session. `DATABASE_URL` no longer points at Supabase
  during a test run. Recorded 2026-08-13.
- **Reasoning:** the tests need Postgres, not Supabase. Two real defects came
  from the current arrangement — a test that hard-deleted a live store's
  history on every run for three months, and DB-backed tests writing junk rows
  into `ops_job_runs` that surface on the system status page.
- **Ruled out:** a second Supabase project (a second cloud dependency, and a
  bug in isolation still lands on production infra); schema-per-run inside the
  existing database (same objection, cheaper).
- **Consequences:** the synthetic-store and derived-date conventions in
  codex 13 stay in force — they are cheap and they are the last line if the
  container is ever bypassed.
- **Reopen if:** container startup dominates the gate's runtime.

## D-026 — The coverage floor holds at 75 until Streamlit retires (was B-0004)
- **Decision:** the gate's coverage floor stays at 75%. Raise to 80% once the
  Streamlit pages are retired under D-019. Recorded 2026-08-13.
- **Reasoning:** measured 77–78% today; the whole gap is Streamlit page
  modules at 21–43%, and those pages are being replaced. Covering them now is
  work with a short half-life.
- **Reopen if:** D-019's app reaches parity and the pages are deleted — raise
  to 80 against what remains, in the same task that deletes them.

## D-027 — The repo is formatted once, in a commit of its own (was B-0005)
- **Decision:** one `refactor` task runs `ruff format .` across the repo,
  commits the reformat alone with no behavioral change, and re-enables the
  `ruff format --check` line in `scripts/verify.sh` in the same commit.
  Recorded 2026-08-13.
- **Reasoning:** 68 files would change, ~58 of them pre-existing. Formatting
  incrementally leaves the gate line disabled for months while drift persists.
  The diff is mechanical and `git diff -w` proves it changed nothing else.
- **Reopen if:** never; after this the gate keeps it true.

## Pre-Burst build log (verbatim)

The original dated entries from the pre-Burst build. Kept as-is: they record
why the data layer, calendar, and reconciliation model look the way they do,
and the codex harvests from them.

---

## 2026-05-13 — uOS pipeline deferred to Phase 8

Context: University of Subway training reports are delivered via Schoox
(no-reply@schoox.com). Email bodies are notifications only — they
contain report metadata and a "Download Report" button linking to
https://app.schoox.com/file/download.php?id=... which requires an
authenticated Schoox session. No table data or CSV attachment is
embedded in the email itself.

Decision: Disable the uOS_pull cron. Mark the compliance widget in the
dashboard as "Data unavailable — see runbook." Re-engage in Phase 8
with one of three paths:
  1. Configure Schoox scheduled-report delivery to attach the file
     (free, depends on whether the franchisee plan exposes this option)
  2. Manual download workflow: human drops files into uos-inbox/, a
     separate ingest reads from there
  3. Schoox API integration (requires IT/vendor coordination)

Consequences: The 28 parser unit tests still pass (they validate the
parser against synthetic fixtures). The parser code is preserved for
future re-engagement. The uOS workflow still exists for manual
workflow_dispatch but no longer runs on schedule. Compliance tracking
is a manual eyeball process via Schoox login until then.


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

## 2026-05-13 — Phase 7 audit finding: 12-month backfill still pending

**Context:** Task 7.4 ran `scripts/audit_backfill.py` against the live
Supabase database and the first audit report
(`docs/audit_2026-05-13.md`) shows:

- Daily-mart coverage: **111 / 4,704** cells (4,593 missing).
- Weekly-mart coverage: **27 / 681** cells (654 missing).
- 14 active stores × 365 days = 4,704 expected, but only the
  smoke-test window `2026-05-05`..`2026-05-12` actually ingested in
  Phase 3.

**Decision:** This is a **legitimate audit finding**, not a script
bug. The Phase 3 task notes (`SUBWAY_OPS_TASKS.md` §3.4) state the
12-month backfill is "smoke-tested" only and warn that a full run
"takes days of wall-clock" due to FreshConnect's daily rate-limit
window. We ship Phase 7 with the audit script and report in place;
the actual full backfill is a manual operational task.

**Consequences:** Before declaring the system production-ready,
run `uv run python scripts/backfill.py --start "$(date -v-365d
+%Y-%m-%d)"` and let it resume across multiple days as 429s push it
forward; re-run `audit_backfill.py` and confirm the daily/weekly
coverage tables go green. Until then, dashboard pages render
correctly for the populated window only — operators should not draw
historical conclusions from current data. Also noted: the playbook's
"`stg_controlsheet_weekly.net_sales_total`" reference is stale —
the actual column is `net_sales` (no `_total` suffix; the wide-table
DDL generator omits the suffix for top-level metrics that are
already weekly aggregates). The audit script and rendered markdown
both reference the correct column name.
