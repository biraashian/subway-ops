# Operations calendar

Every scheduled event in this system. Times are wall-clock; the cron
expressions are UTC because that's what GitHub Actions enforces.

When DST kicks in, the wall-clock time in PT shifts by one hour for
each entry — the cron stays in UTC. We've accepted that drift
explicitly (see `decisions.md`, entry dated 2026-05-13).

## Automated schedule

| Job | Workflow | Cron (UTC) | Wall-clock (PT, PST → PDT) | Source of truth |
|---|---|---|---|---|
| Daily pull | `daily_pull.yml` | `0 10 * * *` | 03:00 → 02:00 | `.github/workflows/daily_pull.yml` |
| uOS pull | `uos_pull.yml` | `0 11 * * *` | 04:00 → 03:00 | `.github/workflows/uos_pull.yml` |
| Refresh marts | `refresh_marts.yml` | `0 */4 * * *` | every 4 hours | `.github/workflows/refresh_marts.yml` |
| Weekly digest | `weekly_digest.yml` | `0 14 * * 3` | Wed 07:00 → 06:00 | `.github/workflows/weekly_digest.yml` |
| CI | `ci.yml` | (PR + push to main) | n/a | `.github/workflows/ci.yml` |

**Ordering invariants.** Daily pull (10:00) runs an hour before uOS
pull (11:00) so any uOS row referencing a brand-new store sees the
ref tables already up to date. The first mart refresh of the day
(`0 */4 *`) is at 00:00 UTC; the next is at 04:00, then 08:00, then
**12:00** — landing two hours after the daily pull so the mart
materialises fresh data, then again at 16:00 / 20:00.

**Failure plumbing.** Each scheduled workflow ends in a
`notify_failure` step that emails `ALERT_EMAIL` when the prior step
fails, with a link back to the workflow run.

## Manual cadence

| Task | Frequency | Owner | Trigger |
|---|---|---|---|
| Backfill status check | Monthly, on the 1st | Owner | `uv run python scripts/backfill.py --status` |
| Audit reconciliation | Quarterly | Owner | `uv run python scripts/audit_backfill.py` (Task 7.4) |
| FreshConnect credential rotation | Annual | Owner | LiveIQ admin portal; coordinate with anyone else holding the key — regenerating invalidates the previous one |
| Gmail OAuth re-consent | When `uos_pull` 401s (see runbook §12) | Owner | `uv run python scripts/gmail_get_token.py` |
| Supabase backup verification | Quarterly | Owner | Spot-check a row count in the Supabase admin's "Backups" tab |
| Streamlit Cloud cold-start check | Monthly | Owner | `curl -I "$DASHBOARD_URL"` — should return 200 |
| Add / remove store | As needed | Owner | Edit `seed/stores.csv` + `seed/field_managers.csv`, run `scripts/seed_reference.py` (runbook §8 / §9) |
| Add / remove dashboard user | As needed | Owner | Edit `seed/users.csv`, run `scripts/seed_reference.py` |

## What an operator does each Wednesday

1. **07:00 PT (or 06:00 PT during PDT)** — owner gets the weekly
   digest in inbox.
2. Skim portfolio snapshot, recon escalations, training compliance.
3. Open the dashboard for any store flagged red.
4. Click into **System status** if anything looks stale (the page
   auto-refreshes every 60 s and surfaces the latest 50
   `ops_job_runs`).

If the digest didn't arrive: runbook §5.

## What an operator does each month-start

1. `uv run python scripts/backfill.py --status` — verify every
   endpoint shows full coverage for the prior month.
2. Open the **System status** dashboard page; sort by `status =
   'failed'`. Any failure that wasn't acted on at the time is a gap.
3. Skim the Streamlit Cloud "App analytics" panel; cold-start
   timeouts spike when traffic is sparse (runbook §16).

## What an operator does each quarter

1. Run `scripts/audit_backfill.py` (Task 7.4 — manual cross-check
   against LiveIQ's own reports).
2. Verify Supabase backup retention is healthy.
3. Refresh the recorded FreshConnect fixtures so model tests stay
   anchored to live API shape:

   ```bash
   uv run python scripts/discovery.py
   ```

   Commit the regenerated `docs/api_field_coverage.md` if it
   changed.

## See also

- [`runbook.md`](runbook.md) — failure-mode response procedures.
- [`SUBWAY_OPS_BUILD_PLAYBOOK.md`](../SUBWAY_OPS_BUILD_PLAYBOOK.md)
  — full task history, including the rationale for each schedule
  choice.
