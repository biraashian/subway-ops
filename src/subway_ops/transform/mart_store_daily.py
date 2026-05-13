"""Refresh logic for ``mart_store_daily``.

Builds one row per (store, business_date) from four staging sources:
``stg_daily_sales``, ``stg_3p_daily``, ``stg_inventory_movement_totals``
(filtered to the ``COST OF GOODS COST`` metric — that's the daily food-cost
total surfaced upstream), and the ``stg_cash_drops`` view. Rate-style KPIs
(``sales_per_labor_hour``, ``average_ticket``, ``third_party_pct``,
``food_cost_pct``) are GENERATED columns on the mart, so we never compute
them in Python.

The refresh is idempotent — one ``INSERT … ON CONFLICT DO UPDATE`` keyed
on ``(restaurant_number, business_date)`` — and wrapped in
``track_job("refresh_mart_store_daily")``.
"""

from __future__ import annotations

from datetime import date, timedelta

import structlog
from sqlalchemy import text

from subway_ops.db.connection import get_engine
from subway_ops.db.job_runs import track_job

JOB_NAME = "refresh_mart_store_daily"
# Daily metric in stg_inventory_movement_totals that gives us the daily COGS.
INVENTORY_METRIC = "COST OF GOODS COST"
# Refresh window — wide enough to catch late corrections, narrow enough to
# stay fast. The dashboard only shows the current week + 30-day trend.
DEFAULT_LOOKBACK_DAYS = 14

log = structlog.get_logger(__name__)


_REFRESH_SQL = """
WITH ds AS (
    SELECT restaurant_number, business_date,
           net_sales, tax, transactions, units, hours_worked
    FROM stg_daily_sales
    WHERE business_date BETWEEN :start AND :end
),
tp AS (
    SELECT restaurant_number, business_date,
           total_net_sales AS third_party_sales,
           total_transactions AS third_party_transactions
    FROM stg_3p_daily
    WHERE business_date BETWEEN :start AND :end
),
inv AS (
    SELECT restaurant_number, business_date,
           total_cost AS daily_inventory_cost,
           waste_value AS daily_inventory_waste
    FROM stg_inventory_movement_totals
    WHERE business_date BETWEEN :start AND :end
      AND metric_name = :inventory_metric
),
cd AS (
    SELECT restaurant_number, business_date,
           COUNT(*)::int AS cash_drop_count
    FROM stg_cash_drops
    WHERE business_date BETWEEN :start AND :end
    GROUP BY restaurant_number, business_date
),
keys AS (
    SELECT restaurant_number, business_date FROM ds
    UNION
    SELECT restaurant_number, business_date FROM tp
    UNION
    SELECT restaurant_number, business_date FROM inv
    UNION
    SELECT restaurant_number, business_date FROM cd
)
INSERT INTO mart_store_daily (
    restaurant_number, business_date,
    net_sales, tax, transactions, units, hours_worked,
    third_party_sales, third_party_transactions,
    daily_inventory_cost, daily_inventory_waste,
    cash_drop_count
)
SELECT k.restaurant_number, k.business_date,
       ds.net_sales, ds.tax, ds.transactions, ds.units, ds.hours_worked,
       tp.third_party_sales, tp.third_party_transactions,
       inv.daily_inventory_cost, inv.daily_inventory_waste,
       COALESCE(cd.cash_drop_count, 0)
FROM keys k
LEFT JOIN ds  USING (restaurant_number, business_date)
LEFT JOIN tp  USING (restaurant_number, business_date)
LEFT JOIN inv USING (restaurant_number, business_date)
LEFT JOIN cd  USING (restaurant_number, business_date)
ON CONFLICT (restaurant_number, business_date) DO UPDATE SET
    net_sales                = EXCLUDED.net_sales,
    tax                      = EXCLUDED.tax,
    transactions             = EXCLUDED.transactions,
    units                    = EXCLUDED.units,
    hours_worked             = EXCLUDED.hours_worked,
    third_party_sales        = EXCLUDED.third_party_sales,
    third_party_transactions = EXCLUDED.third_party_transactions,
    daily_inventory_cost     = EXCLUDED.daily_inventory_cost,
    daily_inventory_waste    = EXCLUDED.daily_inventory_waste,
    cash_drop_count          = EXCLUDED.cash_drop_count,
    refreshed_at             = now()
"""


def refresh(start: date | None = None, end: date | None = None) -> int:
    """Rebuild ``mart_store_daily`` for ``[start, end]`` inclusive.

    When both endpoints are omitted, the window is the last
    ``DEFAULT_LOOKBACK_DAYS`` ending today's UTC date — enough to absorb
    late corrections from the ingest layer without rewriting the whole
    history every run. Either bound may be omitted independently.

    Returns the number of mart rows touched (inserted + updated).
    """
    if end is None:
        end = date.today()
    if start is None:
        start = end - timedelta(days=DEFAULT_LOOKBACK_DAYS - 1)
    if end < start:
        raise ValueError(f"end ({end}) precedes start ({start})")

    log.info("refresh_mart_store_daily_plan", start=str(start), end=str(end))

    engine = get_engine()
    with track_job(JOB_NAME) as meta:
        meta["start"] = start.isoformat()
        meta["end"] = end.isoformat()

        with engine.begin() as conn:
            result = conn.execute(
                text(_REFRESH_SQL),
                {"start": start, "end": end, "inventory_metric": INVENTORY_METRIC},
            )
            rows = result.rowcount

        log.info("refresh_mart_store_daily_done", rows=rows)
        meta["rows_written"] = rows

    return rows
