"""12-month backfill orchestrator.

Loads up to a year of history into staging, one endpoint window at a time,
checkpointing each successfully-completed window in ``ops_backfill_progress``
so the script can be interrupted (Ctrl-C, daily rate-limit, network blip)
and trivially resumed.

Defaults:
- ``--end`` = today
- ``--start`` = ``--end`` minus 365 days

Window sizes per endpoint match the documented per-call caps so the ingest
modules never have to re-batch dates internally:

- daily endpoints: chunked by their day-cap (50 days for daily_sales /
  inventory_movement, 31 for paidouts, 30 for timeclock + third_party_daily)
- weekly endpoints: one window per Tuesday in range (controlsheet, wisr)

When every window is recorded, the script refreshes the three Phase 3
marts for the full backfill range so the dashboard immediately sees the
new history.

CLI:

    uv run python scripts/backfill.py                       # last 365 days
    uv run python scripts/backfill.py --start 2025-04-01 --end 2025-04-15
    uv run python scripts/backfill.py --status              # progress only
    uv run python scripts/backfill.py --no-refresh          # skip mart rebuild

On 429 (FreshConnect daily quota exhausted) the script prints completed /
remaining counts per endpoint and a recommended resume time, then exits
with code 0 — it succeeded at making progress, just not finishing.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

import structlog
from sqlalchemy import text

from subway_ops.db.connection import get_engine
from subway_ops.db.job_runs import track_job
from subway_ops.freshconnect.client import RateLimitError
from subway_ops.ingest import (
    controlsheet,
    daily_sales,
    inventory_movement,
    paidouts,
    third_party_daily,
    timeclock,
    wisr,
)
from subway_ops.transform import (
    mart_field_manager_portfolio,
    mart_store_daily,
    mart_store_weekly,
)

JOB_NAME = "backfill"
TUESDAY = 1  # date.weekday() index for Tuesday

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Endpoint registry
# ---------------------------------------------------------------------------


EndpointKind = Literal["daily", "weekly"]

DailyIngest = Callable[[date, date], int]
WeeklyIngest = Callable[[date], int]


@dataclass(frozen=True)
class EndpointDef:
    name: str
    kind: EndpointKind
    max_days: int | None  # daily only; ignored for weekly
    ingest_daily: DailyIngest | None = None
    ingest_weekly: WeeklyIngest | None = None


def _default_endpoints() -> list[EndpointDef]:
    return [
        EndpointDef("daily_sales",        "daily",  50, ingest_daily=daily_sales.ingest),
        EndpointDef("paidouts",           "daily",  31, ingest_daily=paidouts.ingest),
        EndpointDef("inventory_movement", "daily",  50, ingest_daily=inventory_movement.ingest),
        EndpointDef("timeclock",          "daily",  30, ingest_daily=timeclock.ingest),
        EndpointDef("third_party_daily",  "daily",  30, ingest_daily=third_party_daily.ingest),
        EndpointDef("controlsheet",       "weekly", None, ingest_weekly=controlsheet.ingest),
        EndpointDef("wisr",               "weekly", None, ingest_weekly=wisr.ingest),
    ]


# ---------------------------------------------------------------------------
# Window planning
# ---------------------------------------------------------------------------


def daily_windows(start: date, end: date, max_days: int) -> list[tuple[date, date]]:
    """Split ``[start, end]`` (inclusive) into chunks of at most ``max_days``."""
    if end < start:
        raise ValueError(f"end ({end}) precedes start ({start})")
    out: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        win_end = min(cursor + timedelta(days=max_days - 1), end)
        out.append((cursor, win_end))
        cursor = win_end + timedelta(days=1)
    return out


def tuesdays_in_range(start: date, end: date) -> list[date]:
    """Every Tuesday whose date falls in ``[start, end]`` (inclusive)."""
    if end < start:
        raise ValueError(f"end ({end}) precedes start ({start})")
    delta = (TUESDAY - start.weekday()) % 7
    cursor = start + timedelta(days=delta)
    out: list[date] = []
    while cursor <= end:
        out.append(cursor)
        cursor += timedelta(days=7)
    return out


def plan_windows(ep: EndpointDef, start: date, end: date) -> list[tuple[date, date]]:
    """Full set of ``(window_start, window_end)`` tuples for an endpoint."""
    if ep.kind == "daily":
        assert ep.max_days is not None
        return daily_windows(start, end, ep.max_days)
    return [(d, d) for d in tuesdays_in_range(start, end)]


# ---------------------------------------------------------------------------
# Progress tracking
# ---------------------------------------------------------------------------


def _completed_windows(endpoint: str) -> set[tuple[date, date]]:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT window_start, window_end FROM ops_backfill_progress "
                "WHERE job_name = :job AND endpoint = :ep"
            ),
            {"job": JOB_NAME, "ep": endpoint},
        ).all()
    return {(r[0], r[1]) for r in rows}


def _record_completion(endpoint: str, window_start: date, window_end: date) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO ops_backfill_progress "
                "(job_name, endpoint, window_start, window_end) "
                "VALUES (:job, :ep, :s, :e) "
                "ON CONFLICT DO NOTHING"
            ),
            {"job": JOB_NAME, "ep": endpoint, "s": window_start, "e": window_end},
        )


# ---------------------------------------------------------------------------
# Status reporting
# ---------------------------------------------------------------------------


def status_table(start: date, end: date) -> str:
    """Plain-text completed / remaining table per endpoint."""
    endpoints = _default_endpoints()
    name_width = max(len(e.name) for e in endpoints)
    lines = [
        f"{'endpoint'.ljust(name_width)}  windows  done  remaining",
        f"{'-' * name_width}  -------  ----  ---------",
    ]
    for ep in endpoints:
        planned = plan_windows(ep, start, end)
        done = _completed_windows(ep.name)
        completed = sum(1 for w in planned if w in done)
        lines.append(
            f"{ep.name.ljust(name_width)}  "
            f"{len(planned):7d}  {completed:4d}  {len(planned) - completed:9d}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Mart refresh after staging completes
# ---------------------------------------------------------------------------


def _refresh_marts_for_range(start: date, end: date) -> dict[str, int]:
    """Rebuild every Phase 3 mart for the just-loaded window."""
    log.info("backfill_refreshing_marts", start=str(start), end=str(end))
    daily_rows = mart_store_daily.refresh(start=start, end=end)

    weekly_total = 0
    fm_total = 0
    for tue in tuesdays_in_range(start, end):
        weekly_total += mart_store_weekly.refresh(week_end=tue)
        fm_total += mart_field_manager_portfolio.refresh(week_end=tue)

    return {
        "mart_store_daily": daily_rows,
        "mart_store_weekly": weekly_total,
        "mart_field_manager_portfolio": fm_total,
    }


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------


def _run_endpoint(ep: EndpointDef, pending: list[tuple[date, date]]) -> int:
    """Run all pending windows for one endpoint. Returns count completed.

    ``RateLimitError`` is allowed to propagate — the caller decides what
    to do (typically: exit cleanly so the next run picks up here).
    """
    completed = 0
    for win_start, win_end in pending:
        log.info(
            "backfill_window_start",
            endpoint=ep.name,
            window_start=str(win_start),
            window_end=str(win_end),
        )
        if ep.kind == "daily":
            assert ep.ingest_daily is not None
            ep.ingest_daily(win_start, win_end)
        else:
            assert ep.ingest_weekly is not None
            ep.ingest_weekly(win_end)
        _record_completion(ep.name, win_start, win_end)
        completed += 1
        log.info(
            "backfill_window_done",
            endpoint=ep.name,
            window_start=str(win_start),
            window_end=str(win_end),
        )
    return completed


def _resume_message(today: date) -> str:
    return (
        "Daily rate limit hit. FreshConnect quota resets at 00:00 UTC "
        "(17:00 PT / 18:00 PDT). Re-run the same command after the reset. "
        f"Today (UTC date): {today.isoformat()}."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--start", type=date.fromisoformat,
        help="Backfill window start (YYYY-MM-DD). Default: end - 365 days.",
    )
    parser.add_argument(
        "--end", type=date.fromisoformat,
        help="Backfill window end (YYYY-MM-DD). Default: today.",
    )
    parser.add_argument(
        "--status", action="store_true",
        help="Print completed/remaining windows per endpoint and exit.",
    )
    parser.add_argument(
        "--no-refresh", action="store_true",
        help="Skip rebuilding the marts after staging completes.",
    )
    args = parser.parse_args(argv)

    structlog.configure(processors=[structlog.dev.ConsoleRenderer()])

    end = args.end or date.today()
    start = args.start or (end - timedelta(days=365))
    if end < start:
        sys.stderr.write(f"--end ({end}) precedes --start ({start}).\n")
        return 2

    endpoints = _default_endpoints()

    if args.status:
        print(status_table(start, end))
        return 0

    log.info("backfill_plan", start=str(start), end=str(end))

    grand_completed = 0
    rate_limited = False

    with track_job(JOB_NAME) as meta:
        meta["start"] = start.isoformat()
        meta["end"] = end.isoformat()
        per_endpoint: dict[str, int] = {}

        for ep in endpoints:
            planned = plan_windows(ep, start, end)
            done = _completed_windows(ep.name)
            pending = [w for w in planned if w not in done]
            log.info(
                "backfill_endpoint",
                endpoint=ep.name,
                planned=len(planned),
                already_done=len(planned) - len(pending),
                pending=len(pending),
            )
            try:
                completed = _run_endpoint(ep, pending)
            except RateLimitError:
                rate_limited = True
                log.warning("backfill_rate_limited", endpoint=ep.name)
                # Recompute after the partial run so the metadata reflects
                # whatever we DID get through.
                per_endpoint[ep.name] = len(_completed_windows(ep.name))
                break
            per_endpoint[ep.name] = completed
            grand_completed += completed

        meta["rate_limited"] = rate_limited
        meta["per_endpoint_windows_completed"] = per_endpoint
        meta["rows_written"] = grand_completed

        if rate_limited:
            sys.stderr.write(_resume_message(date.today()) + "\n")
            sys.stderr.write(status_table(start, end) + "\n")
            return 0

        if not args.no_refresh:
            mart_counts = _refresh_marts_for_range(start, end)
            meta["mart_rows"] = mart_counts
            print(
                "Backfill complete. "
                f"{grand_completed} windows loaded. "
                f"Refreshed marts for {start} to {end}: "
                f"daily={mart_counts['mart_store_daily']}, "
                f"weekly={mart_counts['mart_store_weekly']}, "
                f"fm_portfolio={mart_counts['mart_field_manager_portfolio']}."
            )
        else:
            print(
                f"Backfill staging complete: {grand_completed} windows loaded. "
                f"Mart refresh skipped (--no-refresh)."
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
