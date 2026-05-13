"""Refresh logic for ``mart_recon_weekly``.

One row per ``(store, week_end_date Tuesday)``. POS deposit comes from
the ``stg_controlsheet_weekly.cash_control_deposit_in_bank_total``
column; the actual bank deposit, when known, comes from
``ops_variance_entries`` (operator-entered on the recon review page
that Task 5.2 builds).

The mart's variance and status columns are GENERATED in Postgres — the
refresh just keeps the two source values in sync. Status semantics:

- ``unverified`` — no operator entry yet for this (store, week).
- ``clean``      — |variance| ≤ ``VARIANCE_FLAGGED_USD``.
- ``flagged``    — variance bigger than clean but ≤ ``VARIANCE_ESCALATED_USD``.
- ``escalated`` — variance above the escalated threshold; bubbles into
  the weekly digest's "needs owner attention" block.

The Python thresholds (``subway_ops.config.VARIANCE_*``) and the SQL
generated-column expression in migration 014 must stay in lockstep.
"""

from __future__ import annotations

from datetime import date, timedelta

import structlog
from sqlalchemy import text

from subway_ops.calendar import previous_business_week
from subway_ops.db.connection import get_engine
from subway_ops.db.job_runs import track_job

JOB_NAME = "refresh_mart_recon_weekly"
DEFAULT_WEEKS_BACK = 8

log = structlog.get_logger(__name__)


_REFRESH_SQL = """
WITH weeks AS (
    SELECT DISTINCT week_end_date
    FROM stg_controlsheet_weekly
    WHERE week_end_date >= :earliest
),
pos AS (
    SELECT cs.restaurant_number,
           cs.week_end_date,
           cs.cash_control_deposit_in_bank_total AS pos_deposit_in_bank
    FROM stg_controlsheet_weekly cs
    JOIN weeks w USING (week_end_date)
),
keys AS (
    SELECT restaurant_number, week_end_date FROM pos
    UNION
    SELECT v.restaurant_number, v.week_end_date
    FROM ops_variance_entries v
    WHERE v.week_end_date >= :earliest
)
INSERT INTO mart_recon_weekly (
    restaurant_number, week_end_date,
    pos_deposit_in_bank, actual_bank_deposit
)
SELECT
    k.restaurant_number,
    k.week_end_date,
    pos.pos_deposit_in_bank,
    v.actual_bank_deposit
FROM keys k
LEFT JOIN pos USING (restaurant_number, week_end_date)
LEFT JOIN ops_variance_entries v USING (restaurant_number, week_end_date)
ON CONFLICT (restaurant_number, week_end_date) DO UPDATE SET
    pos_deposit_in_bank = EXCLUDED.pos_deposit_in_bank,
    actual_bank_deposit = EXCLUDED.actual_bank_deposit,
    refreshed_at = now()
"""


def refresh(weeks_back: int = DEFAULT_WEEKS_BACK) -> int:
    """Rebuild ``mart_recon_weekly`` for the last ``weeks_back`` weeks.

    Default 8 weeks is enough to catch a late variance entry (operators
    typically reconcile within a few days) without rewriting stable
    history every refresh.
    """
    if weeks_back <= 0:
        raise ValueError(f"weeks_back must be positive, got {weeks_back}")

    _, last_closed = previous_business_week()
    # last_closed is a Tuesday; step back ``weeks_back - 1`` weeks so the
    # window includes that many closed weeks ending today's prior Tuesday.
    earliest = last_closed - timedelta(days=7 * (weeks_back - 1))

    log.info(
        "refresh_mart_recon_weekly_plan",
        earliest=str(earliest),
        last_closed=str(last_closed),
        weeks_back=weeks_back,
    )

    engine = get_engine()
    with track_job(JOB_NAME) as meta:
        meta["earliest"] = earliest.isoformat()
        meta["weeks_back"] = weeks_back
        with engine.begin() as conn:
            result = conn.execute(text(_REFRESH_SQL), {"earliest": earliest})
            rows = result.rowcount
        log.info("refresh_mart_recon_weekly_done", rows=rows)
        meta["rows_written"] = rows

    return rows


def refresh_for_week(week_end: date) -> int:
    """Refresh the mart for a single Tuesday week-end. Convenience wrapper
    for the recon page's "save and recompute" flow in Task 5.2."""
    engine = get_engine()
    with track_job(JOB_NAME) as meta:
        meta["earliest"] = week_end.isoformat()
        meta["weeks_back"] = 1
        with engine.begin() as conn:
            result = conn.execute(text(_REFRESH_SQL), {"earliest": week_end})
            rows = result.rowcount
        meta["rows_written"] = rows
    return rows
