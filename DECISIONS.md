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

## D-028 — A drift declaration asserts accounting, not causation (amends D-024, was B-0024)
- **Decision:** `.drift/expected/T-####.txt` asserts *"every schema difference
  between the baseline and the live database at gate time is accounted for, and
  here is what each one is"* — **not** "this task caused these changes".
  Recorded 2026-08-13, ratifying what T-0010 built and B-0024 challenged.
- **Reasoning:** the accounting reading is the one that still catches the case
  the gate exists for. An unexplained table fails whether or not the current
  task created it, and "a table appeared and nobody knows whose it is" is more
  alarming than "this task added a table", not less. Causation leaves a task
  that inherits a predecessor's applied-but-unmerged migration with nothing
  honest to write.
- **How this arose, recorded because the process matters more than the answer:**
  T-0010 hit the ambiguity mid-build and resolved it by rewriting
  `.drift/expected/README.md`, then documented the change in its journal as
  "I changed the definition rather than the declaration". That is Rule 1 —
  FLAG, DON'T FILL — violated and then described in the first person. The
  `/audit` fork caught it; the builder did not. The answer here is the same one
  the build reached, which is exactly why the route it took still matters: a
  correct guess is still a defect.

### The predecessor rule (the part D-024 was missing)

1. A task declares the drift **observed at its own gate run**, whatever caused it.
2. Drift inherited from a predecessor whose migration is applied but whose task
   is unmerged is declared with an **attributing comment** naming that task.
3. Once the predecessor merges and post-merge rotates the baseline, the inherited
   line is no longer observed. The inheriting task's declaration must then be
   **retired** — and the staleness check enforces this rather than obstructing
   it: a declaration left carrying a merged predecessor's line reds the gate
   until someone removes it.
4. **Merge order follows dependency order** wherever it can. Under a clean queue
   the originating task merges first, its table enters the baseline, and the
   later task observes nothing and declares nothing. Inheritance is the
   exception case, not the normal one.

- **Consequences:** for the specific T-0003 / T-0010 tangle, T-0010 merges first
  because it is the enabler — T-0003 cannot reach a green gate without it. Its
  declaration correctly accounts for `ops_worklist_items` with attribution. When
  T-0003 then resumes, the baseline already carries its table, so it observes no
  drift and declares nothing; its migration file, CHECKSUMS entry and journal
  carry the record instead. That is a one-time artifact of T-0003 having halted,
  and the audit is right that the reviewable artifact lands on the wrong task
  this once. Rule 4 makes the inheriting task's declaration part of its
  DELIVERABLES.
- **Reopen if:** inheritance stops being exceptional. If tasks routinely inherit
  drift, the cause is builds applying migrations to a shared database — fix
  that at the root via D-025 rather than elaborating this rule.

## D-029 — `dismissed` suppresses a re-raise; `resolved` does not (was B-0025)
- **Decision:** `ops_worklist_items` suppresses a new item for the same
  `(kind, subject_ref)` while an existing one is `open`, `in_progress` **or
  `dismissed`**. `resolved` does not suppress. Dismissal is durable and is undone
  only by an explicit reopen. Decided 2026-08-13.
- **Reasoning:** every producer of worklist items is a sweep — it runs each cycle
  and re-asserts everything it still believes. Under the built behavior
  (`dismissed` inert) office dismisses an `employee_incomplete` item and T-0009's
  next sweep re-raises it, so dismissal accomplishes nothing for the only kind of
  producer this table has. A control that the system silently undoes is worse
  than no control: it teaches the operator that the worklist does not listen, and
  the worklist's entire value is that a human's attention is respected.
  `resolved` is the opposite case — the problem was fixed, and a recurrence is
  genuinely new work that should surface.
- **Accepted cost, stated plainly:** a real new occurrence of a dismissed problem
  stays invisible until someone reopens the item. That is a live failure mode,
  not a theoretical one, and it is preferred to a dismiss button that does
  nothing. The reopen path is SPEC-APP-001's to build.
- **How this arose:** T-0003 chose `LIVE_STATES = ("open", "in_progress")` at
  build time and encoded it in a partial unique index. No document defined
  `dismissed`'s meaning, so this was Rule 1 — FLAG, DON'T FILL — violated by
  omission rather than by argument: the 353-line journal never mentions the state
  at all. The `/audit` fork reproduced the consequence against the delivered
  code. A defensible choice made silently is still a defect, and silence makes it
  harder to catch than a bad choice made loudly.
- **Consequences:** the index predicate in `020_worklist.sql` and `LIVE_STATES`
  in `db/worklist.py` both change to three states, and a test asserting that a
  dismissed subject stays quiet joins T-0003's required list. Codex 02 now states
  which states suppress, so no future producer has to re-derive it.
- **Reopen if:** a producer appears whose subjects genuinely recur as new
  incidents rather than as the same standing problem — a per-shift exception, say,
  rather than a per-person completeness gap. Durable dismissal is right for
  standing problems and wrong for recurring events, and the second kind would
  want a cool-off window (B-0025 option C) rather than this rule.

## D-030 — The worklist records when resolution happened, not who did it (was B-0026)
- **Decision:** `ops_worklist_items` carries `resolved_at TIMESTAMPTZ`, which
  codex 02's shape now names explicitly. It does **not** carry `resolved_by`, and
  `resolve_item` takes no actor parameter. Decided 2026-08-13.
- **Reasoning:** `resolved_at` is entailed by the state itself — an item that
  reached a terminal state without a time is a record that something happened but
  not when, which no operational table should produce. An actor is a different
  claim. Nothing in this system can populate one today: there is no worklist
  screen, no producer passes it, and every row written would leave it NULL. A
  nullable actor column filled by nobody is worse than an absent one, because it
  reads as evidence that attribution was tracked when it never was.
- **How this arose:** T-0003 shipped both columns plus an undeclared
  `resolved_by` parameter, past a shape its own NOTES called complete ("codex 02
  already defines the shape completely, so this is not invention"). The journal
  is scrupulous about exactly this failure mode elsewhere — it records catching
  and rejecting an invented `ref_roles` FK because "the reasonable-looking option
  is the dangerous one" — and never mentions these two columns. Gold-plating past
  the spec is RED at audit even when the extra code is good, and the finding here
  is the silence more than the columns.
- **Consequences:** `resolved_by` is dropped from the migration, from
  `resolve_item`'s signature and from `test_resolve_records_who_and_when`, which
  narrows to timing. Codex 02's stated shape gains the resolution time, so the
  closed list is true again.
- **Reopen if:** SPEC-APP-001 builds the worklist screen. A human clicking
  "resolve" is a real actor with a real identity (D-018 gives every one of them a
  Discord account), and at that point the column has a producer and earns its
  place. It arrives then, in that spec, as a new migration.

## D-031 — Real-time is a budget with one occupant (was B-0013)
- **Decision:** shift reminders are real-time. Yesterday's numbers, schedule
  publication, overtime notifications, task assignment, bonus standings,
  reconciliation exceptions and certificate expiry all run on a cadence. Any new
  notification is cadence by default; promoting one to real-time is a founder
  decision recorded in codex 11, not a spec-level choice. Decided 2026-08-13,
  closing question 11.1 from the B-0006 interview.
- **Reasoning:** a shift reminder is the only message on the list whose value
  expires and whose recipient has not yet acted. Every other kind reports
  something already past — per codex 08 even overtime is detection rather than
  prediction — and delivering it hours sooner changes nobody's behavior. The
  binding constraint was never technology but volume: a system pushing eight
  kinds of message in real time trains everyone to mute the channel, and a muted
  channel is worse than no channel because it looks like communication while
  carrying none. Framing real-time as a spent budget makes the next promotion an
  explicit trade rather than an accumulation.
- **Consequences:** codex 11's routing table is written and `blocked_by: B-0013`
  is lifted. The chapter stays **draft** on B-0028 — "cadence" is not yet a
  number, and SPEC-COM cannot write an acceptance criterion against "batched"
  without knowing which kinds go daily, which weekly, and at what local hour.
- **Recorded interpretation, flagged rather than assumed:** B-0013 carried no
  lettered options; the founder answered "A". Taken to mean the single marked
  recommendation — shift reminders real-time, everything else cadence — because
  nothing else in the item was labelled. Say so if that reads wrong; it is one
  line to correct here and in codex 11.
- **Reopen if:** the Discord pilot in Lauren's territory shows crew missing
  time-critical information that is not a shift reminder. The pilot exists to
  find exactly that, and the budget can be spent a second time on evidence.

## D-032 — Append-only binds at merge, not at application (was B-0027)
- **Decision:** a migration that has been applied to the shared database but has
  **not been merged to `main`** may be edited in place, on its own branch, by the
  task that owns it. A migration that has reached `main` is frozen absolutely and
  forever; a change to it is a new file, with no exception and no size threshold.
  Decided 2026-08-13.
- **The boundary, stated so it cannot be stretched:** the test is `main`, not
  "applied somewhere", not "already run", not "it would be tidier". If
  `git log main -- <migration>` returns anything, the file is closed. The
  permission granted here covers exactly one situation — a task correcting its
  own unmerged migration before that migration has ever been seen by the
  integration branch.
- **Reasoning:** the rule's own stated purpose, in
  `check_migrations_append_only.py`, is that "a fresh environment built from the
  migrations diverges from production" — the harm is a migration set that no
  longer replays to the schema that exists. A fresh environment replays `main`.
  Editing an unmerged file and re-applying it satisfies that purpose exactly.
  Option B satisfies the rule's letter and defeats its purpose in the other
  direction: `main` would carry a fix-up migration correcting a table introduced
  two files earlier on the same unmerged branch — history honest about the
  process and misleading about the design, permanently, for every future reader
  trying to understand why the worklist index looks the way it does.
- **Conditions the editing task must meet, all three:**
  1. **Measure before dropping.** Confirm and record the row count of every
     affected object. T-0003 qualifies because `ops_worklist_items` holds 0 rows
     and has no producer; a table with rows in it is not covered by this decision
     and goes back to the bench.
  2. **Re-apply, so the live schema agrees with the edited file.** The whole
     justification is that the migration set describes the schema that exists.
     Leaving the shared database on the old shape would invert it.
  3. **Regenerate `CHECKSUMS.txt`** via `--update`, and say in the journal which
     migration was edited and why.
- **The hole this exposes, recorded rather than left implicit:**
  `write_manifest` regenerates the manifest unconditionally from disk, so
  `--update` blesses an edit to *any* migration, including a merged one. Today
  the append-only invariant catches only the person who edits and forgets to run
  the documented command. This decision makes in-place editing a routine build
  step, which turns an honor-system gap into a load-bearing one. **T-0013** fixes
  it: the check compares against the manifest as it exists on `main`, so an
  unmerged migration is free to change and a merged one cannot. Raised here
  rather than folded into T-0003, because a task must not harden the check that
  polices it — the same reasoning that produced the T-0003 halt in the first place.
- **Consequences:** T-0003's rework edits `020_worklist.sql` in place, drops and
  re-creates the live table, and re-runs `--update`. No `021`. The drift gate
  (D-024, D-028) is the backstop: if the re-apply is incomplete, the pre-merge
  snapshot disagrees with the baseline and reds.
- **Reopen if:** it never needs reopening — D-025/T-0011 retires it. Once builds
  run against a containerised Postgres, an unmerged migration is never applied to
  anything shared, the two readings of "applied" stop coming apart, and this
  decision becomes a dead letter describing a situation that can no longer occur.
  That is the intended end state, not a regret.

## D-033 — A worktree convenience artifact is never a commit (was B-0031)
- **Decision:** the symlinks that make a `[P]` worktree usable are **ignored, not
  tracked**. `.gitignore`'s rule becomes `tests/fixtures/recorded` without the
  trailing slash, so it matches the symlink as well as the directory, and
  `forge/T-0005` drops the committed link before it can merge. Decided
  2026-08-17 (B-0031 → B then A).
- **Reasoning:** the link's target is relative and only resolves from inside
  `.claude/worktrees/T-####/tests/fixtures/`. Merged to `main` it resolves five
  levels above `tests/fixtures/` — the filesystem root — and **replaces the real
  fixtures directory with a dangling link, exiting 0**. The 15 recorded fixtures
  are gitignored, so git's index cannot see them and nothing conflicts. `main`
  would go from `568 passed, 6 skipped` to roughly 33 tests silently skipped,
  with no signal anywhere. Proven by the audit against a throwaway clone, not
  argued.
- **How this arose, recorded because the incentive is the real finding:** the
  symlink became a commit because pre-merge Run 1 failed `git status: NOT CLEAN`,
  and committing an untracked file is the shortest path to turning that check
  green. The gate enforces worktree **cleanliness** but not deliverable
  **scope**, so "commit the stray file" is the path of least resistance out of a
  red status for every future `[P]` task. The builder took it. The trailing slash
  in the ignore rule is what left the link untracked rather than ignored, so the
  one-character fix removes the temptation rather than relying on discipline.
- **Not adopted, and deliberately still open:** B-0031's option D — teaching the
  gate to assert the diff touches only DELIVERABLES plus ON_COMPLETION paths — is
  the general fix for this class and was **not** taken. Recorded here so that the
  next scope escape is understood as a known-uncovered case rather than a
  surprise. It wants its own task when someone chooses to pay for the task-file
  parser.
- **Consequences:** T-0005 → queued for rework. `.gitignore` is added to its
  DELIVERABLES so the fix is licensed; the fix re-enters through build → audit →
  close, not from the bench.
- **Reopen if:** a worktree ever needs an artifact that genuinely belongs in
  version control — then it is a real file, tracked normally, and this decision
  does not apply to it.

## D-034 — `[P]` worktree setup carries the gitignored artifacts (was B-0030)
- **Decision:** creating a worktree for a `[P]` task also links the artifacts the
  suite needs and git does not carry — today `.env` and
  `tests/fixtures/recorded/`. Setup does it; the builder never hand-rolls it.
  Decided 2026-08-17 (B-0030 → C).
- **Reasoning:** a worktree gets tracked files and nothing else, and every
  gitignored dependency is therefore absent. Measured on the first `[P]` task to
  actually use one:

  ```
  worktree, as created      :  465 passed, 109 skipped   ← adhoc: all checks passed
  + .env symlinked          :  535 passed,  39 skipped   ← adhoc: all checks passed
  + fixtures/recorded too   :  568 passed,   6 skipped   ← matches main
  ```

  103 tests were not running, including all of T-0003's and T-0004's — the two
  tasks that had just merged — and the inner loop reported green throughout.
- **The part worth keeping:** fixing the first cause looked like the fix. The
  green tick survived 33 still-absent tests, and only the coverage floor (D-026,
  75%) caught the remainder, because coverage is the one check a suite that
  quietly stopped running cannot satisfy. Any check that reports "pass" without
  saying what it skipped will do this again with the third gitignored artifact
  somebody adds.
- **Scope:** this is the cause-removal half only. B-0030's option B — printing the
  skip count in adhoc's summary — was recommended alongside and **not** adopted,
  so the general "a skip can present as a pass" hole stays open by choice. Task
  **T-0014**.
- **Consequences:** pre-merge was never foolable here — the schema snapshot fails
  hard on an unset `DATABASE_URL` with "a drift check that passes without reading
  a database has verified nothing" — so nothing bad reached a merge. The exposure
  was to the inner loop, which is where a build actually spends its time.

## D-035 — The schema snapshot covers constraints and indexes, not just shape (was B-0029)
- **Decision:** `scripts/schema_snapshot.py` captures CHECK, UNIQUE, foreign key,
  primary key, NOT NULL and index definitions in addition to tables and columns.
  Decided 2026-08-17 (B-0029 → A). Task **T-0015**.
- **Reasoning:** migration `021_people.sql` dropped and recreated
  `ref_users_role_check`, widening who may hold an account on the admin surface
  from three roles to six, and the drift check reported four changes — all new
  tables — with the ALTER unmentioned. An access-control constraint changed and
  the gate had nothing to say. The same blindness covers dropping a uniqueness
  guarantee or removing a foreign key on an existing table.
- **Why this is the second time:** B-0022 chose option A over option B
  *specifically* because option B "cannot see an ALTER that a migration makes by
  accident, which is precisely the case worth catching". Option A was adopted to
  preserve that property and does not have it either — for a different reason at
  a different layer. The declared-drift mechanism (D-024, D-028) is sound; what
  it is declared *over* was narrower than the review it exists to support. Worth
  recording that the property was named, protected by an explicit choice, and
  still lost.
- **Accepted cost:** the first run after this lands reports every existing
  constraint and index as "added", and the baseline rotation that absorbs it is a
  one-time large diff. That diff is worth reading once rather than never.

## D-036 — A week is costed shift by shift, not at one rate (was B-0032)
- **Decision:** `cost_week` resolves the wage rate **per shift**, at the rate in
  force on that shift's own `business_date`, and takes the regular/overtime
  split on the person's summed weekly hours afterwards. Decided 2026-08-17
  (B-0032 → A). SPEC-PPL-001 → v1.3.0.
- **Reasoning:** the spec defined rate resolution for a *date* (AC-012) and never
  said which date represents a *week*. The build filled that silently with
  `week_finish`, which pays every pre-raise hour at the post-raise rate. Measured
  on a live probe — a raise effective mid-week, 10h before and 10h after:

  ```
  cost_week dollars : 600.00000000   (20h all at the new $30)
  correct           : 400            (10h × $10 + 10h × $30)
  DELTA             : +200, the week overstated by 50%
  ```

  It is the one number this whole spec exists to produce, it feeds
  `mart_store_weekly.labor_cost_pct`, and `is_costed` was `True` throughout, so
  nothing downstream would have questioned it.
- **Which rate the premium multiplies — derived, not newly decided.** Q-007
  (B-0020, already folded into this spec) defines the overtime hours as "the
  hours after the 40th, wherever worked, **ordered by `clock_in`**". That
  ordering identifies which shifts contain the premium hours; this decision then
  prices those shifts at their own rates. NG-007 still fences out the *store
  allocation* of the premium — only Q-007's ordering is used here, not its
  attribution, and `CON-005` still returns a per-person weekly figure.
- **Consequence for `clock_in`:** ordering shifts now matters to a dollar figure,
  and `stg_timeclock.clock_in` is a naive `TIMESTAMP` (B-0019, decided → migrate
  before Phase C). Within a single business week the ordering is unambiguous, so
  this is safe today; B-0019's migration remains the fix and its timing is
  unchanged.
- **How this arose:** the builder wrote `rate_in_force(employee_id, week_finish)`
  without registering that a choice was being made, and the test that appears to
  cover it (`test_rate_is_resolved_for_the_week_not_today`) records its wage
  *before* the week opens, so `week_start` and `week_finish` agree and the choice
  cannot fail. A gap can hide behind a passing test that never distinguishes the
  two candidate answers.
- **Options not taken:** pinning to `week_start` (B) is wrong in the
  non-overstating direction; ratifying `week_finish` (C) is wrong in the
  overstating one; refusing to cost such a week (D) is never wrong but abstains
  exactly when a payroll question is most likely to be asked.

## D-037 — Two accessors: an unguarded resolver and a guarded read (was B-0033)
- **Decision:** `rate_in_force` remains exactly as CON-002 specifies — unguarded,
  internal, used by marts and by `cost_week`. A new **CON-006
  `read_wage(employee_id, on, *, actor_role) -> Decimal | None`** is the guarded
  human-facing accessor, raising `PermissionError` for any role other than
  `office` or `owner`. AC-013 and INV-006 now name `read_wage` and `record_wage`
  as the guarded entry points. Decided 2026-08-17 (B-0033 → C).
- **Reasoning:** AC-013 and INV-006 both describe a *read*, and CON-002's
  signature carries no role, so the contract forbade the shape the AC required —
  a contradiction inside a single REQ. Splitting the two uses resolves it without
  pushing a role parameter into every mart that has no human actor to name.
- **`cost_week`'s side channel, answered rather than deferred:** `cost_week`
  stays unguarded. A caller holding both `dollars` and `regular_hours` recovers
  the rate by division — verified, `600.00000000 / 20.0000 = 30.0000` — so a
  guard there would be theatre. INV-006 is amended to state what is actually
  true: the library's guarded accessor is `read_wage`, and a human-facing surface
  must either go through it or enforce the role itself. An invariant that
  promises more than it delivers is worse than one scoped honestly.
- **How this arose, and why it is recorded as process rather than as a slip:**
  the builder resolved the identical contradiction in **opposite directions in
  the same file** — adding an unspecified `actor_role` to `record_wage` while
  declining to add one to `rate_in_force` — noticed the inconsistency, wrote it
  up in `journal/T-0007.md`, and then decided it rather than benching it. Rule 1
  makes an ambiguous spec a bench item regardless of how confident the builder
  is. Writing the reasoning down is necessary and is not a substitute for asking.
- **Reopen if:** a surface appears that needs the rate but is neither a mart nor
  a human read — then the two-entry-point split is the wrong shape and A
  (`actor_role` everywhere) becomes the honest answer.

## D-038 — `is_costed = True` means the rate is known (was B-0034)
- **Decision:** a business week with **no shifts** still resolves a rate, at
  `week_finish`. If none is in force, `dollars = None` and `is_costed = False`,
  exactly as for any other uncosted week. Decided 2026-08-17 (B-0034 → B).
  CON-005 amended; SPEC-PPL-001 → v1.4.0.
- **Reasoning:** `cost_week` consulted the wage table only for dates that had
  shifts, so an empty week never looked and fell through to the costed branch —
  returning `Decimal("0")` with `is_costed = True` for a person with no wage row
  at all, and for `employee_id 999999999`, which does not exist. That is the
  `Decimal("0")`-on-a-missing-rate the task's own FORBIDDEN_ACTIONS forbid.
- **What the flag now means, stated because that is the whole decision:**
  `is_costed = True` asserts *the rate is known*. It does not mean "nothing
  contradicted us". A consumer aggregating across people (T-0009's AC-019 count)
  can therefore read the flag as a claim about knowledge rather than about
  arithmetic.
- **Accepted cost:** the figure abstains on a week whose answer — $0 — is
  arithmetically knowable, because zero hours cost zero at any rate. Option A
  (ratify the truthful zero) was defensible for exactly that reason and was not
  taken: a caller cannot distinguish a real zero from an unpriceable one unless
  the flag means something specific, and the flag is the only channel that
  distinction has.
- **How this arose — the same shape twice in one task.** Like D-036, this was an
  undefined case filled silently, and like D-036 the covering test
  (`test_a_week_with_no_shifts_costs_zero_when_a_rate_exists`) records a wage
  first, so the two candidate answers cannot differ inside it. Two independent
  instances of the same blind spot in one build is a pattern worth naming: a
  test that establishes the happy precondition before exercising the branch can
  never discriminate between the answers.

## D-039 — Tests seed their own stores; they never point at a real one (was B-0035)
- **Decision:** DB-backed fixtures create synthetic stores (`T-PPL-1`,
  `T-PPL-2`, `is_active = false`) and drop them, rather than reading real store
  numbers out of `ref_stores`. Decided 2026-08-17 (B-0035 → A). This restates,
  rather than changes, `codex/13-BUILD/CONVENTIONS.md` — "Never point a test at a
  real store number" — and records that the convention was being broken.
- **Reasoning:** `tests/test_people_cost.py` took the two lowest real store
  numbers (10393 and 17967, both active) and inserted up to 35 hours of
  `stg_timeclock` punches against them inside the current business week.
  Teardown worked and left zero residue; the exposure is the crash window,
  because teardown is a fixture finalizer and a killed run leaves phantom punches
  on two live stores with no owner and no alarm. That is the precise incident
  codex 13 was written after — `test_mart_recon_weekly.py` hard-deleting a real
  store's history on every run for three months.
- **Scope:** T-0007's rework fixes its own file, since it cannot merge otherwise.
  The rest of the repo is **T-0016**, including T-0004's merged tests, which read
  real store numbers to satisfy a foreign key. That use writes nothing to
  staging and is much less dangerous — but the convention has no "read-only"
  exemption, and a rule with an undocumented exception is a rule nobody can
  apply.
- **Reopen if:** never, on its own terms. D-025/T-0011 makes it moot by giving
  the suite its own database, at which point this is harmless belt-and-braces.

## D-040 — Test namespaces are per run, not per file (was B-0036)
- **Decision:** every DB-backed test file mixes a **per-session token** into its
  namespace marker, and teardown is scoped to that token. Decided 2026-08-17
  (B-0036 → A). Task **T-0016**, together with D-039 — both change the same
  files, and separating them would only manufacture a merge conflict.
- **Reasoning:** markers like `MARK = "t0007-wages-selftest"` and
  `KIND = "t0003_selftest"` identify the *file*, not the *run*, and teardown
  deletes everything carrying the marker. Two concurrent runs therefore wipe each
  other's fixtures mid-test. Reproduced deterministically:

  ```
  two runs of tests/test_people_wages.py started together
    run A : 3 failed, 21 passed, 2 errors
    run B : 4 failed, 19 passed, 4 errors
  the same file run serially
            25 passed
  ```

- **How it surfaced:** a pre-merge run of `9583f0f` exited 1 while `/audit`'s run
  of the *same commit* exited 0, because the two overlapped. The audit recorded
  the symptom as "a wage row vanishing mid-test — unexplained".
- **Why this is worth a decision rather than a shrug:** `/audit` re-runs the gate
  by design, so the gate can contradict itself for reasons unrelated to the code.
  A gate that goes red at random teaches everyone to re-run and shrug, which is
  how a real failure eventually gets waved through. The failure mode is the
  gate's credibility, not the tests.
- **Not adopted:** B (a lockfile serialising the gate) — it slows the gate in
  exactly the situation where two things are trying to make progress.
- **Reopen if:** it never needs reopening — **C is the real fix.** T-0011's
  containerised Postgres (D-025) removes the shared resource entirely, and this
  decision becomes dead weight describing a hazard that can no longer occur.
