"""Refresh logic for ``mart_field_manager_portfolio``.

Joins ``mart_store_weekly`` to ``ref_stores`` and groups by
``field_manager_name``. Aggregates are sales-weighted — a $1.2M store
moves the portfolio metric more than a $0.5M one — and the per-target
store counts come from the upstream GENERATED flags on
``mart_store_weekly``.

The refresh is one ``INSERT … ON CONFLICT DO UPDATE`` keyed on
``(field_manager_name, week_end_date)``, wrapped in
``track_job("refresh_mart_field_manager_portfolio")``.
"""

from __future__ import annotations

from datetime import date

import structlog
from sqlalchemy import text

from subway_ops.calendar import previous_business_week
from subway_ops.db.connection import get_engine
from subway_ops.db.job_runs import track_job

JOB_NAME = "refresh_mart_field_manager_portfolio"

log = structlog.get_logger(__name__)


# Sales-weighted averages: the numerator and denominator both filter out
# rows where the source pct is NULL, so a missing pct never drags the
# weighted average toward zero. ``NULLIF(..., 0)`` short-circuits the
# division when no store contributed any weight (e.g. brand-new FM with
# zero closed weeks of data).
_REFRESH_SQL = """
WITH src AS (
    SELECT s.field_manager_name,
           w.week_end_date,
           w.restaurant_number,
           w.net_sales_total,
           w.food_cost_actual_pct,
           w.labor_cost_pct,
           w.is_food_cost_in_target,
           w.is_labor_cost_in_target
    FROM mart_store_weekly w
    JOIN ref_stores s ON s.store_number = w.restaurant_number
    WHERE w.week_end_date = :week_end
      AND s.field_manager_name IS NOT NULL
)
INSERT INTO mart_field_manager_portfolio (
    field_manager_name, week_end_date,
    store_count, store_count_in_target_food, store_count_in_target_labor,
    total_net_sales_weighted,
    portfolio_food_cost_pct,
    portfolio_labor_cost_pct
)
SELECT
    field_manager_name,
    week_end_date,
    COUNT(*)::int AS store_count,
    COALESCE(
        SUM(CASE WHEN is_food_cost_in_target THEN 1 ELSE 0 END),
        0
    )::int AS store_count_in_target_food,
    COALESCE(
        SUM(CASE WHEN is_labor_cost_in_target THEN 1 ELSE 0 END),
        0
    )::int AS store_count_in_target_labor,
    SUM(net_sales_total) AS total_net_sales_weighted,
    SUM(food_cost_actual_pct * net_sales_total)
      / NULLIF(SUM(CASE WHEN food_cost_actual_pct IS NOT NULL
                        THEN net_sales_total END), 0)
        AS portfolio_food_cost_pct,
    SUM(labor_cost_pct * net_sales_total)
      / NULLIF(SUM(CASE WHEN labor_cost_pct IS NOT NULL
                        THEN net_sales_total END), 0)
        AS portfolio_labor_cost_pct
FROM src
GROUP BY field_manager_name, week_end_date
ON CONFLICT (field_manager_name, week_end_date) DO UPDATE SET
    store_count                  = EXCLUDED.store_count,
    store_count_in_target_food   = EXCLUDED.store_count_in_target_food,
    store_count_in_target_labor  = EXCLUDED.store_count_in_target_labor,
    total_net_sales_weighted     = EXCLUDED.total_net_sales_weighted,
    portfolio_food_cost_pct      = EXCLUDED.portfolio_food_cost_pct,
    portfolio_labor_cost_pct     = EXCLUDED.portfolio_labor_cost_pct,
    refreshed_at                 = now()
"""


def refresh(week_end: date | None = None) -> int:
    """Rebuild ``mart_field_manager_portfolio`` for a single Tuesday week-end.

    Defaults to the most-recently closed business week. Returns the number
    of FM rows touched.
    """
    if week_end is None:
        _, week_end = previous_business_week()

    log.info("refresh_mart_fm_portfolio_plan", week_end=str(week_end))

    engine = get_engine()
    with track_job(JOB_NAME) as meta:
        meta["week_end"] = week_end.isoformat()
        with engine.begin() as conn:
            result = conn.execute(text(_REFRESH_SQL), {"week_end": week_end})
            rows = result.rowcount
        log.info("refresh_mart_fm_portfolio_done", rows=rows)
        meta["rows_written"] = rows

    return rows
