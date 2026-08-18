"""Ingest pipeline for the FreshConnect ``DailyTimeclock`` endpoint.

One row per shift (clock-in / clock-out) per clerk per store. The
``business_date`` column comes from ``clockIn`` via the 02:00 cutoff so
overnight shifts roll up correctly.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

import structlog
from sqlalchemy import text

from subway_ops.calendar import STORE_TZ, dt_to_business_date
from subway_ops.db.connection import get_engine
from subway_ops.db.job_runs import track_job
from subway_ops.db.upsert import upsert_rows
from subway_ops.freshconnect.client import FreshConnectClient
from subway_ops.freshconnect.models import DailyTimeclockResponse

MAX_STORES_PER_CALL = 10
MAX_DAYS_PER_CALL = 30
JOB_NAME = "ingest_timeclock"

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Batching
# ---------------------------------------------------------------------------


def _chunk(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _date_windows(start: date, end: date, max_days: int) -> list[tuple[date, date]]:
    if end < start:
        raise ValueError(f"end ({end}) precedes start ({start})")
    windows: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        window_end = min(cursor + timedelta(days=max_days - 1), end)
        windows.append((cursor, window_end))
        cursor = window_end + timedelta(days=1)
    return windows


def plan_batches(
    store_numbers: list[str], start: date, end: date
) -> list[tuple[list[str], date, date]]:
    triples: list[tuple[list[str], date, date]] = []
    for chunk in _chunk(store_numbers, MAX_STORES_PER_CALL):
        for win_start, win_end in _date_windows(start, end, MAX_DAYS_PER_CALL):
            triples.append((chunk, win_start, win_end))
    return triples


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _business_date(naive_dt: Any) -> date:
    return dt_to_business_date(naive_dt.replace(tzinfo=STORE_TZ))


def _active_store_numbers() -> list[str]:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT store_number FROM ref_stores WHERE is_active = true ORDER BY store_number")
        ).all()
    return [str(r[0]) for r in rows]


def _store_raw(start: date, end: date, payload: Any) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO raw_timeclock (start_date, end_date, payload) "
                "VALUES (:s, :e, CAST(:p AS JSONB))"
            ),
            {"s": start, "e": end, "p": json.dumps(payload)},
        )


def _entry_to_row(entry: Any) -> dict[str, Any]:
    return {
        "restaurant_number": entry.restaurant_number,
        "clerk_id": entry.clerk_id,
        "clock_in": entry.clock_in,
        "clock_out": entry.clock_out,
        "business_date": _business_date(entry.clock_in),
        "employee_name": entry.employee_name,
        "hours_before_adj": entry.hours_before_adj,
        "hours_after_adj": entry.hours_after_adj,
        "adj_amount": entry.adj_amount,
    }


def _dedupe(rows: list[dict[str, Any]], key: tuple[str, ...]) -> list[dict[str, Any]]:
    seen: dict[tuple[Any, ...], dict[str, Any]] = {}
    for r in rows:
        seen[tuple(r[c] for c in key)] = r
    return list(seen.values())


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def ingest(
    start: date,
    end: date,
    store_numbers: list[str] | None = None,
    *,
    client: FreshConnectClient | None = None,
) -> int:
    """Ingest DailyTimeclock entries for ``[start, end]`` inclusive."""
    if store_numbers is None:
        store_numbers = _active_store_numbers()
    if not store_numbers:
        log.warning("ingest_timeclock_no_stores")
        return 0

    batches = plan_batches(store_numbers, start, end)
    log.info(
        "ingest_timeclock_plan",
        store_count=len(store_numbers),
        window_count=len(batches),
        start=str(start),
        end=str(end),
    )

    total = 0
    owns_client = client is None

    with track_job(JOB_NAME) as meta:
        meta["start"] = start.isoformat()
        meta["end"] = end.isoformat()
        meta["store_count"] = len(store_numbers)
        meta["batch_count"] = len(batches)

        c = client or FreshConnectClient()
        try:
            for stores, win_start, win_end in batches:
                payload = c.get_daily_timeclock(stores, win_start, win_end)
                _store_raw(win_start, win_end, payload)
                parsed = DailyTimeclockResponse.model_validate(payload)
                rows = [_entry_to_row(e) for e in parsed.data]
                rows = _dedupe(rows, ("restaurant_number", "clerk_id", "clock_in"))
                written = upsert_rows(
                    "stg_timeclock",
                    rows,
                    key_cols=["restaurant_number", "clerk_id", "clock_in"],
                )
                total += written
                log.info(
                    "ingest_timeclock_batch_done",
                    stores=stores,
                    start=str(win_start),
                    end=str(win_end),
                    rows=written,
                )
        finally:
            if owns_client:
                c.close()

        meta["rows_written"] = total

    return total
