"""Rolling mart refresh.

Rebuilds the three Phase-3 marts so late corrections from staging
propagate without the operator having to think about it. Run on a 4-hour
cron via ``.github/workflows/refresh_marts.yml`` — that cadence is the
SLA the dashboard advertises.

Scope:
- ``mart_store_daily``: refresh the trailing 14 business days. The mart's
  own default lookback is the same, but pinning it here makes the cron
  intent explicit and the ``ops_job_runs`` row easier to read.
- ``mart_store_weekly`` + ``mart_field_manager_portfolio``: refresh the
  most-recently closed business week AND the one before it. Two weeks is
  enough to absorb the typical late-correction window without burning
  cycles on already-stable history.

The whole script wraps in ``track_job("refresh_marts")`` so every cron
firing leaves an audit trail. Failures bubble up so the workflow's
``notify_failure`` step kicks in.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from datetime import date, timedelta

import structlog

from subway_ops.calendar import business_date_now, previous_business_week
from subway_ops.db.job_runs import track_job
from subway_ops.transform import (
    mart_field_manager_portfolio,
    mart_recon_weekly,
    mart_store_daily,
    mart_store_weekly,
)

JOB_NAME = "refresh_marts"
DAILY_LOOKBACK_DAYS = 14
# Number of recent closed weeks to refresh weekly + FM rollups for.
WEEKLY_LOOKBACK_WEEKS = 2
# How many weeks of the reconciliation mart to rebuild on each cron tick.
# Wider than WEEKLY_LOOKBACK_WEEKS because operators sometimes enter
# variances days or weeks late.
RECON_LOOKBACK_WEEKS = 8

log = structlog.get_logger(__name__)


def _recent_week_ends(today: date, n: int) -> list[date]:
    """Return the ``n`` most-recent closed Tuesday week-ends, newest first."""
    _, last_tue = previous_business_week(today)
    return [last_tue - timedelta(days=7 * i) for i in range(n)]


def run_refresh(
    *,
    today: date,
    refresh_daily: Callable[..., int] = mart_store_daily.refresh,
    refresh_weekly: Callable[[date], int] = mart_store_weekly.refresh,
    refresh_fm: Callable[[date], int] = mart_field_manager_portfolio.refresh,
    refresh_recon: Callable[..., int] = mart_recon_weekly.refresh,
) -> dict[str, int]:
    """Refresh every mart. Mockable callables make this unit-testable."""
    start = today - timedelta(days=DAILY_LOOKBACK_DAYS)
    log.info(
        "refresh_marts_plan",
        today=str(today),
        daily_start=str(start),
        daily_end=str(today),
    )
    daily_rows = refresh_daily(start=start, end=today)

    weekly_total = 0
    fm_total = 0
    for wk in _recent_week_ends(today, WEEKLY_LOOKBACK_WEEKS):
        weekly_total += refresh_weekly(wk)
        fm_total += refresh_fm(wk)

    recon_rows = refresh_recon(weeks_back=RECON_LOOKBACK_WEEKS)

    return {
        "mart_store_daily": daily_rows,
        "mart_store_weekly": weekly_total,
        "mart_field_manager_portfolio": fm_total,
        "mart_recon_weekly": recon_rows,
    }


def main() -> int:
    structlog.configure(processors=[structlog.dev.ConsoleRenderer()])
    today = business_date_now()
    with track_job(JOB_NAME) as meta:
        result = run_refresh(today=today)
        meta.update({"today": today.isoformat(), "per_mart_rows": result})
        meta["rows_written"] = sum(result.values())
    return 0


if __name__ == "__main__":
    sys.exit(main())
