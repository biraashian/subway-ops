"""Ingest pipeline for the FreshConnect ``PaidOutsAndNoSales`` endpoint.

The endpoint returns two parallel arrays — one row per no-sale POS event
(``cash in`` / ``cash drop`` / ``no sale`` / etc.) and one row per
paid-out cash event. They flow into ``stg_no_sales`` and ``stg_paid_outs``
respectively; the ``stg_cash_drops`` view filters ``no_sale_type =
'cash drop'`` for the reconciliation flow.

Each event's ``business_date`` is derived from ``event_time`` by attaching
``America/Los_Angeles`` and applying the 02:00 cutoff via
``subway_ops.calendar.dt_to_business_date``.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import text

from subway_ops.calendar import STORE_TZ, dt_to_business_date
from subway_ops.db.connection import get_engine
from subway_ops.db.job_runs import track_job
from subway_ops.db.upsert import upsert_rows
from subway_ops.freshconnect.client import FreshConnectClient
from subway_ops.freshconnect.models import PaidOutsAndNoSalesResponse

MAX_STORES_PER_CALL = 20
MAX_DAYS_PER_CALL = 31
JOB_NAME = "ingest_paidouts_no_sales"

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
    for store_chunk in _chunk(store_numbers, MAX_STORES_PER_CALL):
        for win_start, win_end in _date_windows(start, end, MAX_DAYS_PER_CALL):
            triples.append((store_chunk, win_start, win_end))
    return triples


# ---------------------------------------------------------------------------
# Store resolution + raw persistence
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


def _store_raw(start: date, end: date, payload: Any) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO raw_paidouts_no_sales (start_date, end_date, payload) "
                "VALUES (:s, :e, CAST(:p AS JSONB))"
            ),
            {"s": start, "e": end, "p": json.dumps(payload)},
        )


# ---------------------------------------------------------------------------
# Event → stg row
# ---------------------------------------------------------------------------


def _business_date(event_time: datetime) -> date:
    """Compute the business date for a naive event_time.

    The API emits naive datetimes; we treat them as store-local time (all
    franchise stores share America/Los_Angeles) before applying the 02:00
    cutoff. Switch this when the operator opens a store outside LA.
    """
    aware = event_time.replace(tzinfo=STORE_TZ)
    return dt_to_business_date(aware)


def _no_sale_to_stg(event: Any) -> dict[str, Any]:
    return {
        "restaurant_number": event.restaurant_number,
        "event_time": event.time,
        "business_date": _business_date(event.time),
        "clerk_id": event.clerk_id,
        "clerk_name": event.clerk_name,
        "no_sale_type": event.no_sale_type,
        "reason_type": event.reason_type,
        "reason": event.reason,
    }


def _paid_out_to_stg(event: Any) -> dict[str, Any]:
    return {
        "restaurant_number": event.restaurant_number,
        "event_time": event.time,
        "business_date": _business_date(event.time),
        "clerk_id": event.clerk_id,
        "clerk_name": event.clerk_name,
        "amount": event.amount,
        "reason": event.reason,
        "comment": event.comment,
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
    """Ingest PaidOutsAndNoSales events for ``[start, end]`` inclusive.

    Returns the total number of staging rows written across
    ``stg_no_sales`` + ``stg_paid_outs``.
    """
    if store_numbers is None:
        store_numbers = _active_store_numbers()
    if not store_numbers:
        log.warning("ingest_paidouts_no_stores")
        return 0

    batches = plan_batches(store_numbers, start, end)
    log.info(
        "ingest_paidouts_plan",
        store_count=len(store_numbers),
        window_count=len(batches),
        start=str(start),
        end=str(end),
    )

    total_no_sales = 0
    total_paid_outs = 0
    owns_client = client is None

    with track_job(JOB_NAME) as meta:
        meta["start"] = start.isoformat()
        meta["end"] = end.isoformat()
        meta["store_count"] = len(store_numbers)
        meta["batch_count"] = len(batches)

        c = client or FreshConnectClient()
        try:
            for stores, win_start, win_end in batches:
                payload = c.get_paidouts_and_no_sales(stores, win_start, win_end)
                _store_raw(win_start, win_end, payload)
                parsed = PaidOutsAndNoSalesResponse.model_validate(payload)

                no_sale_rows = [_no_sale_to_stg(e) for e in parsed.data.no_sales]
                paid_out_rows = [_paid_out_to_stg(e) for e in parsed.data.paid_outs]

                # Deduplicate within the batch so multi-event payloads
                # sharing the same PK collapse cleanly. ON CONFLICT alone
                # rejects duplicates in the same INSERT.
                no_sale_rows = _dedupe(
                    no_sale_rows,
                    ("restaurant_number", "event_time", "clerk_id", "no_sale_type"),
                )
                paid_out_rows = _dedupe(
                    paid_out_rows,
                    (
                        "restaurant_number",
                        "event_time",
                        "clerk_id",
                        "amount",
                        "reason",
                    ),
                )

                ns_written = upsert_rows(
                    "stg_no_sales",
                    no_sale_rows,
                    key_cols=[
                        "restaurant_number",
                        "event_time",
                        "clerk_id",
                        "no_sale_type",
                    ],
                )
                po_written = upsert_rows(
                    "stg_paid_outs",
                    paid_out_rows,
                    key_cols=[
                        "restaurant_number",
                        "event_time",
                        "clerk_id",
                        "amount",
                        "reason",
                    ],
                )
                total_no_sales += ns_written
                total_paid_outs += po_written
                log.info(
                    "ingest_paidouts_batch_done",
                    stores=stores,
                    start=str(win_start),
                    end=str(win_end),
                    no_sales=ns_written,
                    paid_outs=po_written,
                )
        finally:
            if owns_client:
                c.close()

        meta["no_sales_rows"] = total_no_sales
        meta["paid_outs_rows"] = total_paid_outs
        meta["rows_written"] = total_no_sales + total_paid_outs

    return total_no_sales + total_paid_outs


def _dedupe(rows: list[dict[str, Any]], key: tuple[str, ...]) -> list[dict[str, Any]]:
    """Last-write-wins dedupe by ``key`` so a single batch can be upserted."""
    seen: dict[tuple[Any, ...], dict[str, Any]] = {}
    for r in rows:
        k = tuple(_normalize_for_key(r[c]) for c in key)
        seen[k] = r
    return list(seen.values())


def _normalize_for_key(value: Any) -> Any:
    """Decimal values that compare equal but differ in scale still hash the same."""
    if isinstance(value, Decimal):
        return value.normalize()
    return value
