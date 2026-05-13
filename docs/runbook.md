# Operations runbook

Every recurring failure mode this system has. Symptom → cause →
diagnosis → fix. Run the diagnosis commands as listed; they assume you
are at the repo root with `.env` configured (or the equivalent env
vars exported) and `uv` on the path.

When you find a new failure mode in the wild, add it here. The
playbook calls out the 16 below as table stakes.

---

## 1. FreshConnect returns 401 (key revoked or rotated)

**Symptom.** A daily-pull, backfill, or discovery run fails with
`subway_ops.freshconnect.client.AuthError: FreshConnect 401
Unauthorized`. GitHub Actions shows the workflow red.

**Cause.** Either the `FRESHCONNECT_API_KEY` was rotated by Subway and
the new value never made it into our env, or the key was administratively
revoked.

**Diagnosis.**

```bash
uv run python -c "from subway_ops.config import settings; print(repr(settings.freshconnect_api_key[:8]))"
# Confirm the local key matches what's in the Subway portal.
uv run python -c "from subway_ops.freshconnect.client import FreshConnectClient; FreshConnectClient().get('/Restaurants')"
# A successful call lists restaurants; AuthError reproduces the failure.
```

**Fix.** Regenerate the key in the LiveIQ admin portal, update **both**
your local `.env` (`FRESHCONNECT_API_KEY=...`) **and** the
`FRESHCONNECT_API_KEY` GitHub Actions secret (Settings → Secrets →
Actions). Re-trigger the failed workflow via `workflow_dispatch` —
no backfill needed because every ingest is idempotent on its natural key.

---

## 2. FreshConnect returns 429 (daily rate limit hit)

**Symptom.** A long-running job (usually `backfill`) exits non-zero with
`RateLimitError: FreshConnect 429`. The orchestrator catches this and
prints the resume command.

**Cause.** FreshConnect's per-day request budget is finite. Big
backfills + a daily pull on the same calendar day can exhaust it.

**Diagnosis.**

```bash
uv run python scripts/backfill.py --status
# Per-endpoint "done / remaining" counts confirm where the run stopped.
```

**Fix.** Wait for the quota window to roll (midnight UTC), then resume
with the same command:

```bash
uv run python scripts/backfill.py
```

The script reads `ops_backfill_progress` and skips windows already
recorded, so it picks up exactly where the 429 stopped.

---

## 3. FreshConnect persistent 5xx (Subway-side outage)

**Symptom.** Every endpoint fails with `ServerError: FreshConnect 5xx`.
Tenacity has already retried; the error is final. Multiple unrelated
ingests fail in the same run.

**Cause.** Upstream incident at LiveIQ. Subway doesn't post a status
page; the only confirmation is consistency across endpoints.

**Diagnosis.**

```bash
uv run python -c "from subway_ops.freshconnect.client import FreshConnectClient; FreshConnectClient().get('/Restaurants')"
# Still 5xx → upstream is down. 200 → transient blip, not this scenario.
```

**Fix.** Wait. The daily-pull workflow runs at 10:00 UTC; if a one-off
outage missed it, re-trigger via `workflow_dispatch` once the
`/Restaurants` smoke call comes back 200. Every ingest is idempotent;
re-running for the same day produces zero duplicate rows.

---

## 4. Daily pull failed in GitHub Actions

**Symptom.** Email from `notify_failure.py` titled "Job 'daily_pull'
failed". GitHub Actions tab shows the red workflow run.

**Cause.** Anything from sections 1–3, or an ingest-specific schema
drift (rare — Pydantic `extra="forbid"` catches it loud).

**Diagnosis.**

```bash
# Click the run URL in the failure email, or:
gh run list --workflow daily_pull.yml --limit 3
gh run view <run-id> --log-failed
# Then, against the live DB:
uv run python -c "from subway_ops.db.connection import execute_sql; [print(r) for r in execute_sql(\"SELECT job_name, status, error_text FROM ops_job_runs WHERE started_at > now() - interval '1 day' ORDER BY started_at DESC LIMIT 5\")]"
```

**Fix.** Address the underlying error from §1/§2/§3 or fix the schema
drift, then re-trigger the workflow. The `ops_job_runs` row will flip
from `failed` to `success` on the next run.

---

## 5. Weekly digest didn't arrive Wednesday morning

**Symptom.** Wednesday rolls past 07:00 PT and the owner's inbox has
nothing. The owner pings.

**Cause.** Three common ones: cron didn't fire (rare on GHA), the
script ran but `ops_digest_log` already had a row for that `week_end`
(idempotency guard short-circuited), or SMTP failed.

**Diagnosis.**

```bash
gh run list --workflow weekly_digest.yml --limit 3
uv run python -c "from subway_ops.db.connection import execute_sql; [print(r) for r in execute_sql('SELECT * FROM ops_digest_log ORDER BY week_end_date DESC LIMIT 3')]"
uv run python -c "from subway_ops.db.connection import execute_sql; [print(r) for r in execute_sql(\"SELECT job_name, status, error_text, metadata FROM ops_job_runs WHERE job_name = 'send_weekly_digest' ORDER BY started_at DESC LIMIT 3\")]"
```

**Fix.** If the log says `already_sent`, the digest did go out earlier
— check the owner's spam folder. If SMTP errored, fix the credential
(GMAIL_APP_PASSWORD) and re-trigger via `workflow_dispatch`. If
nothing was sent and the log row is missing, delete any stale
`ops_digest_log` row for the week (rare) and trigger
`workflow_dispatch`.

---

## 6. Dashboard "Connection refused" or hangs on load

**Symptom.** Streamlit URL returns an error page, or spins on a white
screen for >30 s.

**Cause.** Streamlit Cloud cold start (the app sleeps after inactivity),
DB connection blocked (Supabase paused — see §11), or a deploy hung.

**Diagnosis.**

```bash
# From Streamlit Cloud's app dashboard, click "Logs". Look for:
#   - "ScriptRunner exited" → restart from the UI
#   - "OperationalError: could not connect to server" → DB issue
# Or from your laptop:
uv run python -c "from subway_ops.db.connection import execute_sql; print(execute_sql('SELECT 1')[0])"
```

**Fix.** Streamlit cold start: refresh once and wait 20 s. Persistent:
"Reboot app" in the Streamlit Cloud admin. DB error: jump to §11.

---

## 7. Dashboard auth failing for a known user

**Symptom.** A user types correct credentials and gets "Username/password
is incorrect" or stays stuck on the login form.

**Cause.** Either `is_active=false` on their `ref_users` row, the
bcrypt hash got corrupted during seed import, or the cookie signing
key rotated (logs everyone out at once).

**Diagnosis.**

```bash
uv run python -c "from subway_ops.db.connection import execute_sql; [print(r) for r in execute_sql(\"SELECT email, role, is_active, length(password_hash) FROM ref_users WHERE email = 'user@example.com'\")]"
# Expect: is_active=True, hash length ~60.
```

**Fix.** If `is_active=false`, flip it to `true`. If the hash looks
corrupt, regenerate the row by editing `seed/users.csv` and re-running
`uv run python scripts/seed_reference.py`. Cookie-key rotation: ask
everyone to log in once; nothing else needed.

---

## 8. New store onboarded

**Symptom.** Owner says "we just took over store 12345."

**Fix.**

1. Append a row to `seed/stores.csv` with `store_number, store_name,
   city, state, field_manager_name, timezone, opening_date_estimate`.
2. If the new store joins an existing FM's cluster, append the
   `store_number` to that FM's `store_numbers_csv` in
   `seed/field_managers.csv`.
3. Run `uv run python scripts/seed_reference.py`. Upserts are
   idempotent.
4. Kick off a one-shot backfill so history shows up immediately:

   ```bash
   uv run python scripts/backfill.py --start "$(date -v-365d +%Y-%m-%d)" --end "$(date +%Y-%m-%d)"
   ```

5. Verify the store appears on the owner overview within 5 minutes (the
   mart refresh ttl).

---

## 9. Store closed / decommissioned

**Symptom.** A store is no longer operated by this franchisee.

**Fix.** Flip `is_active=false` on the `ref_stores` row — don't delete:

```bash
uv run python -c "from subway_ops.db.connection import execute_sql; execute_sql(\"UPDATE ref_stores SET is_active = false WHERE store_number = '12345'\")"
```

Historical mart rows and ingests keep working (they just stop adding
new data because `daily_pull` only iterates `is_active=true` stores).
Field managers' `visible_stores()` will drop the closed store from
their grid. If the store is in a user's `assigned_stores` array, edit
`seed/users.csv` and re-seed.

---

## 10. Field manager rotated

**Symptom.** A field manager hands off their cluster to a new one.

**Fix.**

1. Edit `seed/field_managers.csv`: either add the new FM and reassign
   `store_numbers_csv`, or update the existing row's `email` if it's
   the same person at a new address.
2. Edit `seed/users.csv` similarly so the dashboard login matches.
3. Run `uv run python scripts/seed_reference.py`.
4. Confirm `ref_stores.field_manager_name` is correct for the cluster:

   ```bash
   uv run python -c "from subway_ops.db.connection import execute_sql; [print(r) for r in execute_sql(\"SELECT store_number, field_manager_name FROM ref_stores WHERE field_manager_name IN ('OldFM', 'NewFM') ORDER BY store_number\")]"
   ```

---

## 11. Supabase free tier paused (90-day inactivity)

**Symptom.** Every DB-touching script fails with a "project is paused"
error from Supabase. Dashboard shows §6 symptoms.

**Cause.** Supabase free tier auto-pauses projects with no client
activity for 90 days. This system pings constantly when the cron is
healthy, so the trigger is usually: the cron broke for a different
reason (§1–§3), nobody noticed, and 90 days passed.

**Diagnosis.** Open the Supabase dashboard; the project banner reads
"This project is paused".

**Fix.** Click "Restore project" in Supabase. Wait ~5 minutes. Run
`uv run python scripts/migrate.py` to verify connectivity; it should
report "Applied 0 migrations, skipped N". Then re-trigger
`daily_pull.yml` and `refresh_marts.yml` via `workflow_dispatch` to
catch up on missed history.

---

## 12. Gmail token expired (uOS pipeline broken)

**Symptom.** `uos_pull` workflow fails with `RuntimeError: Gmail
credentials are invalid and cannot be refreshed`.

**Cause.** Google revoked the OAuth refresh token. Common causes:
inactive for >6 months (apps in Testing-mode consent screen), the test
user list changed, or the operator revoked access in their account.

**Diagnosis.**

```bash
gh run view <run-id> --log-failed
# Confirm the traceback ends in gmail_client.py with the "re-run gmail_get_token.py" message.
```

**Fix.** Re-run the local OAuth flow:

```bash
uv run python scripts/gmail_get_token.py
base64 -i token.json -o token.b64   # macOS; on Linux use `base64 -w0 token.json > token.b64`
```

Paste the new `token.b64` contents into the `GMAIL_TOKEN_JSON_B64`
GitHub Actions secret. Re-trigger `uos_pull.yml`. See
[`docs/gmail_setup.md`](gmail_setup.md) for the full walkthrough.

---

## 13. uOS email format changed (parser broke)

**Symptom.** `uos_pull` succeeds but `stg_uos_compliance` shows
zero new rows for the latest report, and `ops_job_runs.metadata`
contains a populated `unparsed_sample`.

**Cause.** Subway changed column headers, status wording, or
attachment shape on the uOS report. The parser is lenient (logs +
skips unrecognised rows) — so the job won't fail, but no data lands.

**Diagnosis.**

```bash
uv run python -c "from subway_ops.db.connection import execute_sql; [print(r) for r in execute_sql(\"SELECT metadata->'unparsed_sample' FROM ops_job_runs WHERE job_name = 'ingest_uos' ORDER BY started_at DESC LIMIT 1\")]"
```

Read the sample. The `reason` field tells you which field couldn't
map.

**Fix.** Save a real `.eml` of the new format to
`tests/fixtures/uos/sample_report.eml`. Update one of three locations
in `src/subway_ops/uos/parser.py` as appropriate:

- `_HEADER_TOKENS` — substring tokens used to map column names to
  canonical fields.
- `_STORE_NUMBER_RE` — the digit-run regex if franchise numbers got a
  new width.
- `_COMPLETE_SYNONYMS` / `_OVERDUE_SYNONYMS` / `_PENDING_SYNONYMS` —
  add new status wording.

Add a unit test using the new fixture, ship, re-trigger.

---

## 14. Subway changed an API response shape

**Symptom.** A specific endpoint's ingest fails with
`pydantic.ValidationError: extra fields not permitted` (or `field
required`).

**Cause.** Subway added or renamed a field. Every Pydantic model uses
`extra="forbid"` deliberately so silent drift can't poison staging.

**Diagnosis.**

```bash
uv run python scripts/discovery.py --store 4092
# This refetches every endpoint and re-records fixtures. Failed parses
# show up at the end of the run.
ls tests/fixtures/recorded/
# Open the failing endpoint's JSON and diff against subway_ops/freshconnect/models.py.
```

**Fix.** Edit the relevant model in `subway_ops/freshconnect/models.py`
to add the field (defaulting to `Optional` is usually safest), regen
any downstream flatten code if needed (controlsheet / wisr DDL emitters
print to stdout), apply the new migration if columns changed, run the
relevant unit test, re-trigger the failed workflow. Document the drift
in `decisions.md` with the date.

---

## 15. New quarter — uOS course list changed

**Symptom.** None. New course names appear in `stg_uos_compliance`.

**Cause.** Subway rolls course catalogues quarterly. The schema stores
`course_name` as `TEXT`, not an enum, precisely so this is a non-event.

**Fix.** Nothing. Confirm new courses are landing:

```bash
uv run python -c "from subway_ops.db.connection import execute_sql; [print(r) for r in execute_sql('SELECT course_name, COUNT(*) FROM stg_uos_compliance WHERE ingested_at > now() - interval \\'7 days\\' GROUP BY course_name ORDER BY 1')]"
```

If a course should be excluded from the compliance % (e.g.,
non-required orientation), filter it in the dashboard data layer —
not at ingest time.

---

## 16. Streamlit Cloud app cold-started and timed out

**Symptom.** First visit after a long idle period hangs for 20-40 s
then shows "App ran out of memory" or a blank page; a refresh fixes
it.

**Cause.** Streamlit Cloud sleeps apps after inactivity. The cold
start has to import every module (incl. `pandas`/`pyarrow`); first
request can time out if the import phase plus the first DB call run
over the platform's threshold.

**Diagnosis.** App logs show the script run completing successfully
after the timeout — the issue is initialization latency, not a real
crash.

**Fix.** Short-term: refresh the page. Medium-term: keep the app warm
with an external uptime ping (e.g., a GitHub Actions cron that
`curl`s the dashboard URL every 6 h). Long-term: move to
[`docs/deployment_flyio.md`](deployment_flyio.md) (no idle sleep,
~$5/month).

---

## See also

- [`operations_calendar.md`](operations_calendar.md) — when every
  scheduled job runs.
- [`gmail_setup.md`](gmail_setup.md) — full OAuth setup walkthrough.
- [`deployment_streamlit_cloud.md`](deployment_streamlit_cloud.md) /
  [`deployment_flyio.md`](deployment_flyio.md) — host-specific notes.
- The owner-only **System status** page in the dashboard surfaces
  the latest 50 `ops_job_runs` rows with a one-click Re-run link
  to GitHub Actions.
