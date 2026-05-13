"""Daily ingest orchestrator.

Runs every Phase 2 ingest with the right window for "today":

- Five daily-grain endpoints (sales summary, paid outs / no sales,
  inventory movement, timeclock, third-party daily) ingest yesterday's
  business date.
- Two weekly-grain endpoints (ControlSheet, Wisr) ingest the previous
  business week's Tuesday-end — but only when today is Wednesday, so the
  week has actually closed.

Everything runs inside an outer ``track_job("daily_pull")`` context. Each
inner ingest also opens its own ``track_job`` row, giving us per-endpoint
diagnostics in ``ops_job_runs``. Failures bubble up as a non-zero exit code
so the GitHub Actions workflow can fire ``notify_failure.py``.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import structlog

from subway_ops.calendar import business_date_now, previous_business_week
from subway_ops.db.job_runs import track_job
from subway_ops.ingest import (
    controlsheet,
    daily_sales,
    inventory_movement,
    paidouts,
    third_party_daily,
    timeclock,
    wisr,
)

JOB_NAME = "daily_pull"
WEDNESDAY = 2

log = structlog.get_logger(__name__)

# Daily ingests accept (start, end). Weekly ingests accept (week_end).
DailyIngest = Callable[[date, date], int]
WeeklyIngest = Callable[[date], int]


def _default_daily_ingests() -> dict[str, DailyIngest]:
    return {
        "daily_sales": daily_sales.ingest,
        "paidouts": paidouts.ingest,
        "inventory_movement": inventory_movement.ingest,
        "timeclock": timeclock.ingest,
        "third_party_daily": third_party_daily.ingest,
    }


def _default_weekly_ingests() -> dict[str, WeeklyIngest]:
    return {
        "controlsheet": controlsheet.ingest,
        "wisr": wisr.ingest,
    }


def run_daily_pull(
    *,
    today: date,
    daily_ingests: dict[str, DailyIngest] | None = None,
    weekly_ingests: dict[str, WeeklyIngest] | None = None,
) -> dict[str, Any]:
    """Run the orchestrator for the given ``today`` business date.

    Tests pass mocked ``daily_ingests`` / ``weekly_ingests`` dicts. Production
    uses the defaults wired to ``subway_ops.ingest.*``.

    Returns a metadata dict with per-ingest row counts; the caller adds it
    to its surrounding ``track_job`` row.
    """
    daily_ingests = daily_ingests or _default_daily_ingests()
    weekly_ingests = weekly_ingests or _default_weekly_ingests()

    yesterday = today - timedelta(days=1)
    _, last_week_end = previous_business_week(today)
    is_wednesday = today.weekday() == WEDNESDAY

    log.info(
        "daily_pull_start",
        today=str(today),
        yesterday=str(yesterday),
        last_week_end=str(last_week_end),
        is_wednesday=is_wednesday,
    )

    per_ingest: dict[str, int] = {}
    total = 0

    for name, fn in daily_ingests.items():
        log.info("daily_pull_ingest_start", ingest=name, window=str(yesterday))
        rows = fn(yesterday, yesterday)
        per_ingest[name] = rows
        total += rows
        log.info("daily_pull_ingest_done", ingest=name, rows=rows)

    if is_wednesday:
        for name, wfn in weekly_ingests.items():
            log.info("daily_pull_ingest_start", ingest=name, window=str(last_week_end))
            rows = wfn(last_week_end)
            per_ingest[name] = rows
            total += rows
            log.info("daily_pull_ingest_done", ingest=name, rows=rows)

    return {
        "today": today.isoformat(),
        "yesterday": yesterday.isoformat(),
        "last_week_end": last_week_end.isoformat(),
        "is_wednesday": is_wednesday,
        "per_ingest_rows": per_ingest,
        "total_rows": total,
    }


def main() -> int:
    structlog.configure(processors=[structlog.dev.ConsoleRenderer()])
    today = business_date_now()
    with track_job(JOB_NAME) as meta:
        result = run_daily_pull(today=today)
        meta.update(result)
        meta["rows_written"] = result["total_rows"]
    return 0


if __name__ == "__main__":
    sys.exit(main())
