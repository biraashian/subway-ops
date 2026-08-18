"""Ingest pipeline for the FreshConnect ``InventoryMovement`` endpoint.

The endpoint returns one entry per (store, business date) with two
parallel arrays: ``items`` (per-line inventory ingredients with delivery,
transfer, total cost, and waste) and ``totals`` (a small set of named
rollups such as ``"UNITS COST"``). Both arrays flow into their own stg
tables keyed on natural composites.
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
from subway_ops.freshconnect.models import (
    InventoryMovementDay,
    InventoryMovementResponse,
)

MAX_STORES_PER_CALL = 20
MAX_DAYS_PER_CALL = 50
JOB_NAME = "ingest_inventory_movement"

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
# DB helpers
# ---------------------------------------------------------------------------


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
                "INSERT INTO raw_inventory_movement (start_date, end_date, payload) "
                "VALUES (:s, :e, CAST(:p AS JSONB))"
            ),
            {"s": start, "e": end, "p": json.dumps(payload)},
        )


# ---------------------------------------------------------------------------
# Row flatteners
# ---------------------------------------------------------------------------


def _day_to_item_rows(day: InventoryMovementDay) -> list[dict[str, Any]]:
    bd = day.date.date()
    rows: list[dict[str, Any]] = []
    for it in day.items:
        rows.append(
            {
                "restaurant_number": day.store,
                "business_date": bd,
                "item_category": it.item,
                "inventory_item": it.inventory_item,
                "unit_of_measure": it.unit_of_measure,
                "unit_cost": it.unit_cost,
                "delivery": it.delivery,
                "transfer": it.transfer,
                "total_cost": it.total_cost,
                "waste": it.waste,
                "waste_value": it.waste_value,
            }
        )
    return rows


def _day_to_total_rows(day: InventoryMovementDay) -> list[dict[str, Any]]:
    bd = day.date.date()
    return [
        {
            "restaurant_number": day.store,
            "business_date": bd,
            "metric_name": t.name,
            "total_cost": t.total_cost,
            "waste_value": t.waste_value,
        }
        for t in day.totals
    ]


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
    """Ingest InventoryMovement for ``[start, end]`` inclusive.

    Returns total staging rows written across ``stg_inventory_movement`` +
    ``stg_inventory_movement_totals``.
    """
    if store_numbers is None:
        store_numbers = _active_store_numbers()
    if not store_numbers:
        log.warning("ingest_inventory_movement_no_stores")
        return 0

    batches = plan_batches(store_numbers, start, end)
    log.info(
        "ingest_inventory_movement_plan",
        store_count=len(store_numbers),
        window_count=len(batches),
        start=str(start),
        end=str(end),
    )

    total_items = 0
    total_totals = 0
    owns_client = client is None

    with track_job(JOB_NAME) as meta:
        meta["start"] = start.isoformat()
        meta["end"] = end.isoformat()
        meta["store_count"] = len(store_numbers)
        meta["batch_count"] = len(batches)

        c = client or FreshConnectClient()
        try:
            for stores, win_start, win_end in batches:
                payload = c.get_inventory_movement(stores, win_start, win_end)
                _store_raw(win_start, win_end, payload)
                parsed = InventoryMovementResponse.model_validate(payload)

                item_rows: list[dict[str, Any]] = []
                total_rows: list[dict[str, Any]] = []
                for day in parsed.data:
                    item_rows.extend(_day_to_item_rows(day))
                    total_rows.extend(_day_to_total_rows(day))

                item_rows = _dedupe(
                    item_rows,
                    ("restaurant_number", "business_date", "inventory_item"),
                )
                total_rows = _dedupe(
                    total_rows,
                    ("restaurant_number", "business_date", "metric_name"),
                )

                items_written = upsert_rows(
                    "stg_inventory_movement",
                    item_rows,
                    key_cols=["restaurant_number", "business_date", "inventory_item"],
                )
                totals_written = upsert_rows(
                    "stg_inventory_movement_totals",
                    total_rows,
                    key_cols=["restaurant_number", "business_date", "metric_name"],
                )
                total_items += items_written
                total_totals += totals_written
                log.info(
                    "ingest_inventory_movement_batch_done",
                    stores=stores,
                    start=str(win_start),
                    end=str(win_end),
                    items=items_written,
                    totals=totals_written,
                )
        finally:
            if owns_client:
                c.close()

        meta["item_rows"] = total_items
        meta["total_rows"] = total_totals
        meta["rows_written"] = total_items + total_totals

    return total_items + total_totals
