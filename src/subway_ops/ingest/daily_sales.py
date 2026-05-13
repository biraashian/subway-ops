"""Ingest pipeline for the FreshConnect ``DailySalesSummary`` endpoint.

This module is the canonical template that every other ingest in Phase 2
follows: resolve the store list, batch into windows that respect the
documented per-call limits, hit the API, persist the raw envelope to
``raw_*``, parse via the Pydantic model, and UPSERT typed rows into
``stg_*`` keyed on a natural composite. Re-running for the same window is
a no-op.

Public surface:

    ingest(start, end, store_numbers=None) -> int
        Returns the number of staging rows written.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

import structlog
from sqlalchemy import text

from subway_ops.db.connection import get_engine
from subway_ops.db.job_runs import track_job
from subway_ops.db.upsert import upsert_rows
from subway_ops.freshconnect.client import FreshConnectClient
from subway_ops.freshconnect.models import DailySalesSummaryResponse

# Documented endpoint limits — keep in sync with the FreshConnect client.
MAX_STORES_PER_CALL = 20
MAX_DAYS_PER_CALL = 50

JOB_NAME = "ingest_daily_sales"

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Batching
# ---------------------------------------------------------------------------


def _chunk(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _date_windows(start: date, end: date, max_days: int) -> list[tuple[date, date]]:
    """Split ``[start, end]`` (inclusive) into sub-windows of at most ``max_days``."""
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
    store_numbers: list[str],
    start: date,
    end: date,
) -> list[tuple[list[str], date, date]]:
    """Return ``(stores, start, end)`` triples respecting per-call limits."""
    triples: list[tuple[list[str], date, date]] = []
    for store_chunk in _chunk(store_numbers, MAX_STORES_PER_CALL):
        for win_start, win_end in _date_windows(start, end, MAX_DAYS_PER_CALL):
            triples.append((store_chunk, win_start, win_end))
    return triples


# ---------------------------------------------------------------------------
# Store resolution
# ---------------------------------------------------------------------------


def _active_store_numbers() -> list[str]:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT store_number FROM ref_stores "
                "WHERE is_active = true ORDER BY store_number"
            )
        ).all()
    return [str(r[0]) for r in rows]


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def _store_raw(start: date, end: date, payload: Any) -> None:
    """Write one envelope to ``raw_daily_sales``."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO raw_daily_sales (start_date, end_date, payload) "
                "VALUES (:start, :end, CAST(:payload AS JSONB))"
            ),
            {"start": start, "end": end, "payload": json.dumps(payload)},
        )


def _to_stg_row(row: Any) -> dict[str, Any]:
    """Map a parsed ``DailySalesRow`` to its ``stg_daily_sales`` shape."""
    return {
        "restaurant_number": row.restaurant_number,
        "business_date": row.date.date(),
        "net_sales": row.net_sales,
        "tax": row.tax,
        "units": row.units,
        "transactions": row.transactions,
        "cash_card_total": row.cash_card_total,
        "third_party_sales": row.third_party_sales,
        "third_party_transactions": row.third_party_transactions,
        "hours_worked": row.hours_worked,
    }


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
    """Ingest DailySalesSummary rows for ``[start, end]`` inclusive.

    Args:
        start, end: Business-date range (inclusive). Calendar logic lives in
            ``subway_ops.calendar``; this function trusts the caller to pass
            already-resolved business dates.
        store_numbers: Specific stores to query. ``None`` means every active
            store in ``ref_stores``.
        client: Optional pre-built FreshConnect client (mainly for tests).
            When omitted a fresh client is built from settings.

    Returns:
        The number of rows written to ``stg_daily_sales``.

    Wraps execution in ``track_job(JOB_NAME)`` so the ``ops_job_runs`` table
    sees every invocation.
    """
    if store_numbers is None:
        store_numbers = _active_store_numbers()
    if not store_numbers:
        log.warning("ingest_daily_sales_no_stores")
        return 0

    batches = plan_batches(store_numbers, start, end)
    log.info(
        "ingest_daily_sales_plan",
        store_count=len(store_numbers),
        window_count=len(batches),
        start=str(start),
        end=str(end),
    )

    total_rows = 0
    owns_client = client is None

    with track_job(JOB_NAME) as meta:
        meta["start"] = start.isoformat()
        meta["end"] = end.isoformat()
        meta["store_count"] = len(store_numbers)
        meta["batch_count"] = len(batches)

        c = client or FreshConnectClient()
        try:
            for stores, win_start, win_end in batches:
                payload = c.get_daily_sales_summary(stores, win_start, win_end)
                _store_raw(win_start, win_end, payload)
                parsed = DailySalesSummaryResponse.model_validate(payload)
                stg_rows = [_to_stg_row(r) for r in parsed.data]
                written = upsert_rows(
                    "stg_daily_sales",
                    stg_rows,
                    key_cols=["restaurant_number", "business_date"],
                )
                total_rows += written
                log.info(
                    "ingest_daily_sales_batch_done",
                    stores=stores,
                    start=str(win_start),
                    end=str(win_end),
                    rows=written,
                )
        finally:
            if owns_client:
                c.close()

        meta["rows_written"] = total_rows

    return total_rows
