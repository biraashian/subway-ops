"""Ingest pipeline for the FreshConnect ``ThirdPartyDailySalesSummary`` endpoint.

One row per store per day for the totals (``stg_3p_daily``) plus a row per
provider channel under that day (``stg_3p_daily_provider``).
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
from subway_ops.freshconnect.models import ThirdPartyDailySalesSummaryResponse

MAX_STORES_PER_CALL = 20
MAX_DAYS_PER_CALL = 30
JOB_NAME = "ingest_third_party_daily"

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
                "INSERT INTO raw_third_party_daily (start_date, end_date, payload) "
                "VALUES (:s, :e, CAST(:p AS JSONB))"
            ),
            {"s": start, "e": end, "p": json.dumps(payload)},
        )


def _row_to_daily(row: Any) -> dict[str, Any]:
    return {
        "restaurant_number": row.restaurant_number,
        "business_date": row.date.date(),
        "total_sales": row.total_sales,
        "total_net_sales": row.total_net_sales,
        "total_transactions": row.total_transactions,
    }


def _row_to_provider_rows(row: Any) -> list[dict[str, Any]]:
    return [
        {
            "restaurant_number": row.restaurant_number,
            "business_date": row.date.date(),
            "provider": p.provider,
            "transactions": p.transactions,
            "net_sales": p.net_sales,
            "sales": p.sales,
        }
        for p in row.providers
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
    """Ingest ThirdPartyDailySalesSummary rows for ``[start, end]`` inclusive."""
    if store_numbers is None:
        store_numbers = _active_store_numbers()
    if not store_numbers:
        log.warning("ingest_third_party_daily_no_stores")
        return 0

    batches = plan_batches(store_numbers, start, end)
    log.info(
        "ingest_third_party_daily_plan",
        store_count=len(store_numbers),
        window_count=len(batches),
        start=str(start),
        end=str(end),
    )

    total_daily = 0
    total_providers = 0
    owns_client = client is None

    with track_job(JOB_NAME) as meta:
        meta["start"] = start.isoformat()
        meta["end"] = end.isoformat()
        meta["store_count"] = len(store_numbers)
        meta["batch_count"] = len(batches)

        c = client or FreshConnectClient()
        try:
            for stores, win_start, win_end in batches:
                payload = c.get_third_party_daily(stores, win_start, win_end)
                _store_raw(win_start, win_end, payload)
                parsed = ThirdPartyDailySalesSummaryResponse.model_validate(payload)

                daily_rows: list[dict[str, Any]] = []
                provider_rows: list[dict[str, Any]] = []
                for row in parsed.data:
                    daily_rows.append(_row_to_daily(row))
                    provider_rows.extend(_row_to_provider_rows(row))

                daily_rows = _dedupe(daily_rows, ("restaurant_number", "business_date"))
                provider_rows = _dedupe(
                    provider_rows,
                    ("restaurant_number", "business_date", "provider"),
                )

                daily_written = upsert_rows(
                    "stg_3p_daily",
                    daily_rows,
                    key_cols=["restaurant_number", "business_date"],
                )
                provider_written = upsert_rows(
                    "stg_3p_daily_provider",
                    provider_rows,
                    key_cols=["restaurant_number", "business_date", "provider"],
                )
                total_daily += daily_written
                total_providers += provider_written
                log.info(
                    "ingest_third_party_daily_batch_done",
                    stores=stores,
                    start=str(win_start),
                    end=str(win_end),
                    daily_rows=daily_written,
                    provider_rows=provider_written,
                )
        finally:
            if owns_client:
                c.close()

        meta["daily_rows"] = total_daily
        meta["provider_rows"] = total_providers
        meta["rows_written"] = total_daily + total_providers

    return total_daily + total_providers
