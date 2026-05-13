"""Refresh logic for ``mart_store_weekly``.

One row per (store, week_end_date Tuesday). Joins the wide
``stg_controlsheet_weekly`` with ``stg_wisr_weekly``. Percentages from the
WISR endpoint are emitted as whole-number percents (e.g. ``27.23`` for
27.23%); we divide by 100 before storing so the mart's fractional targets
(``TARGET_FOOD_COST_STORE = 0.22``) work directly and the GENERATED flag
columns compare naturally.

The refresh is idempotent — one ``INSERT … ON CONFLICT DO UPDATE`` keyed
on ``(restaurant_number, week_end_date)`` — and wrapped in
``track_job("refresh_mart_store_weekly")``.

Default behaviour: when ``week_end`` is omitted, refresh the most-recently
closed business week (per ``subway_ops.calendar.previous_business_week``).
"""

from __future__ import annotations

from datetime import date

import structlog
from sqlalchemy import text

from subway_ops.calendar import previous_business_week
from subway_ops.db.connection import get_engine
from subway_ops.db.job_runs import track_job

JOB_NAME = "refresh_mart_store_weekly"

log = structlog.get_logger(__name__)


# ``cs`` rows come from the wide stg_controlsheet_weekly, where every field
# already has a per-day or footer ``_total`` / ``_average`` column. ``w`` rows
# come from stg_wisr_weekly. We divide WISR's whole-number percentages by
# 100 to land fractional values in the mart.
_REFRESH_SQL = """
INSERT INTO mart_store_weekly (
    restaurant_number, week_end_date,
    net_sales_total, transactions_total, units_total, hours_worked_total,
    cash_overshort_total, bread_overshort_total, deposit_in_bank_total,
    customer_count, factor, average_ticket, productivity,
    food_cost_actual_pct, food_cost_expected_pct, food_cost_diff_pct,
    adjusted_cost_of_goods_pct,
    total_inventory_value, distribution_cost_value,
    labor_cost_pct
)
SELECT
    cs.restaurant_number,
    cs.week_end_date,
    cs.net_sales,
    txn.transactions_total,
    cs.unit_itemization_total_units_total::int,
    cs.labor_hours_worked_total,
    cs.cash_control_over_short_total,
    cs.bread_bread_over_short_total,
    cs.cash_control_deposit_in_bank_total,
    cs.customer_count,
    cs.factor,
    cs.metrics_average_ticket_total,
    cs.productivity,
    w.ics_cost_of_goods_actual_percentage     / 100,
    w.ics_cost_of_goods_expected_percentage   / 100,
    w.ics_cost_of_goods_percentage_diff       / 100,
    w.acg_adjusted_cost_of_goods_percentage   / 100,
    w.total_inventory_value,
    w.dc_distribution_costs_value_used,
    NULL  -- labor_cost_pct: deferred until a wage source lands
FROM stg_controlsheet_weekly cs
LEFT JOIN stg_wisr_weekly w
       ON w.restaurant_number = cs.restaurant_number
      AND w.week_end_date     = cs.week_end_date
LEFT JOIN (
    SELECT restaurant_number,
           DATE(:week_end_date) AS week_end_date,
           SUM(transactions)::int AS transactions_total
    FROM stg_daily_sales
    WHERE business_date BETWEEN (DATE(:week_end_date) - INTERVAL '6 days')
                            AND DATE(:week_end_date)
    GROUP BY restaurant_number
) txn
       ON txn.restaurant_number = cs.restaurant_number
      AND txn.week_end_date     = cs.week_end_date
WHERE cs.week_end_date = :week_end_date
ON CONFLICT (restaurant_number, week_end_date) DO UPDATE SET
    net_sales_total            = EXCLUDED.net_sales_total,
    transactions_total         = EXCLUDED.transactions_total,
    units_total                = EXCLUDED.units_total,
    hours_worked_total         = EXCLUDED.hours_worked_total,
    cash_overshort_total       = EXCLUDED.cash_overshort_total,
    bread_overshort_total      = EXCLUDED.bread_overshort_total,
    deposit_in_bank_total      = EXCLUDED.deposit_in_bank_total,
    customer_count             = EXCLUDED.customer_count,
    factor                     = EXCLUDED.factor,
    average_ticket             = EXCLUDED.average_ticket,
    productivity               = EXCLUDED.productivity,
    food_cost_actual_pct       = EXCLUDED.food_cost_actual_pct,
    food_cost_expected_pct     = EXCLUDED.food_cost_expected_pct,
    food_cost_diff_pct         = EXCLUDED.food_cost_diff_pct,
    adjusted_cost_of_goods_pct = EXCLUDED.adjusted_cost_of_goods_pct,
    total_inventory_value      = EXCLUDED.total_inventory_value,
    distribution_cost_value    = EXCLUDED.distribution_cost_value,
    labor_cost_pct             = EXCLUDED.labor_cost_pct,
    refreshed_at               = now()
"""


def refresh(week_end: date | None = None) -> int:
    """Rebuild ``mart_store_weekly`` for a single week-end Tuesday.

    When called with no arguments, refreshes the most-recently closed
    business week (the Tuesday end of ``previous_business_week``).

    Returns the number of mart rows touched.
    """
    if week_end is None:
        _, week_end = previous_business_week()

    log.info("refresh_mart_store_weekly_plan", week_end=str(week_end))

    engine = get_engine()
    with track_job(JOB_NAME) as meta:
        meta["week_end"] = week_end.isoformat()
        with engine.begin() as conn:
            result = conn.execute(text(_REFRESH_SQL), {"week_end_date": week_end})
            rows = result.rowcount
        log.info("refresh_mart_store_weekly_done", rows=rows)
        meta["rows_written"] = rows

    return rows
