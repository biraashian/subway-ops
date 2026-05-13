"""Cached DB query helpers used by the dashboard pages.

Streamlit's caching primitives let us run the SQL once per (input, TTL)
combination — the engine itself is a process-wide singleton, the marts
get refreshed every 4 hours by the cron, and a 5-minute query cache is a
nice compromise between freshness and load on the Supabase free tier.

All helpers return ``pandas.DataFrame`` so pages can render directly via
``st.dataframe`` / ``st.bar_chart`` etc.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st
from sqlalchemy import Engine, text

from subway_ops.calendar import business_date_now, previous_business_week
from subway_ops.db.connection import get_engine as _get_engine

CACHE_TTL_SECONDS = 300
TUESDAY = 1  # date.weekday() index — the Subway business-week-end day.


@st.cache_resource
def cached_engine() -> Engine:
    """Process-wide SQLAlchemy engine, memoised for Streamlit's lifecycle."""
    return _get_engine()


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def last_data_refresh() -> pd.Timestamp | None:
    """The newest ``refreshed_at`` across ``mart_store_daily``."""
    engine = cached_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT MAX(refreshed_at) FROM mart_store_daily")
        ).first()
    if row is None or row[0] is None:
        return None
    return pd.Timestamp(row[0])


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def weekly_overview(week_end: date, store_filter: tuple[str, ...]) -> pd.DataFrame:
    """One row per visible store for the given Tuesday week-end.

    Columns: restaurant_number, store_name, field_manager_name,
    week_end_date, net_sales_total, transactions_total, customer_count,
    average_ticket, productivity, food_cost_actual_pct, labor_cost_pct,
    cash_overshort_total, is_food_cost_in_target, is_labor_cost_in_target.
    """
    if not store_filter:
        return pd.DataFrame()
    engine = cached_engine()
    with engine.connect() as conn:
        return pd.read_sql_query(
            text(
                """
                SELECT
                    w.restaurant_number,
                    s.store_name,
                    s.field_manager_name,
                    w.week_end_date,
                    w.net_sales_total,
                    w.transactions_total,
                    w.customer_count,
                    w.average_ticket,
                    w.productivity,
                    w.food_cost_actual_pct,
                    w.labor_cost_pct,
                    w.cash_overshort_total,
                    w.is_food_cost_in_target,
                    w.is_labor_cost_in_target
                FROM mart_store_weekly w
                JOIN ref_stores s ON s.store_number = w.restaurant_number
                WHERE w.week_end_date = :w
                  AND w.restaurant_number = ANY(:stores)
                ORDER BY w.restaurant_number
                """
            ),
            conn,
            params={"w": week_end, "stores": list(store_filter)},
        )


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def portfolio_trend(weeks: int, store_filter: tuple[str, ...]) -> pd.DataFrame:
    """Sum ``net_sales_total`` per ``week_end_date`` for the last ``weeks`` weeks.

    Returns columns ``week_end_date`` (date) and ``net_sales`` (Decimal),
    ordered chronologically so an Altair line chart renders left-to-right.
    """
    if not store_filter or weeks <= 0:
        return pd.DataFrame(columns=["week_end_date", "net_sales"])
    engine = cached_engine()
    with engine.connect() as conn:
        return pd.read_sql_query(
            text(
                """
                SELECT week_end_date, SUM(net_sales_total) AS net_sales
                FROM mart_store_weekly
                WHERE restaurant_number = ANY(:stores)
                GROUP BY week_end_date
                ORDER BY week_end_date DESC
                LIMIT :weeks
                """
            ),
            conn,
            params={"stores": list(store_filter), "weeks": weeks},
        ).iloc[::-1].reset_index(drop=True)


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def store_daily(store_number: str, start: date, end: date) -> pd.DataFrame:
    """Trend rows from ``mart_store_daily`` for a single store."""
    engine = cached_engine()
    with engine.connect() as conn:
        return pd.read_sql_query(
            text(
                """
                SELECT
                    business_date,
                    net_sales, transactions, units, hours_worked,
                    sales_per_labor_hour, average_ticket,
                    third_party_sales, third_party_pct,
                    daily_inventory_cost, food_cost_pct,
                    cash_drop_count
                FROM mart_store_daily
                WHERE restaurant_number = :s
                  AND business_date BETWEEN :start AND :end
                ORDER BY business_date
                """
            ),
            conn,
            params={"s": store_number, "start": start, "end": end},
        )


def current_and_last_week_ends(today: date | None = None) -> tuple[date, date]:
    """Return ``(current_in_progress_week_end, last_closed_week_end)``.

    The current week-end is the next Tuesday on or after ``today``; the
    last closed week-end is the most recent Tuesday strictly before
    today's business week (so it's never the in-progress one).
    """
    if today is None:
        today = business_date_now()
    days_ahead = (TUESDAY - today.weekday()) % 7
    current = today + timedelta(days=days_ahead)
    _, last_closed = previous_business_week(today)
    return current, last_closed


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def store_weekly_history(store_number: str, weeks: int) -> pd.DataFrame:
    """The last ``weeks`` weekly rows for a single store, chronological order."""
    if weeks <= 0:
        return pd.DataFrame()
    engine = cached_engine()
    with engine.connect() as conn:
        df = pd.read_sql_query(
            text(
                """
                SELECT
                    week_end_date,
                    net_sales_total,
                    transactions_total,
                    units_total,
                    hours_worked_total,
                    customer_count,
                    average_ticket,
                    productivity,
                    food_cost_actual_pct,
                    food_cost_expected_pct,
                    labor_cost_pct,
                    cash_overshort_total,
                    bread_overshort_total,
                    deposit_in_bank_total
                FROM mart_store_weekly
                WHERE restaurant_number = :s
                ORDER BY week_end_date DESC
                LIMIT :weeks
                """
            ),
            conn,
            params={"s": store_number, "weeks": weeks},
        )
    return df.iloc[::-1].reset_index(drop=True)


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def wisr_inventory_items(store_number: str, week_end: date) -> pd.DataFrame:
    """Per-item WISR rows for a single store + week, ordered by largest
    negative ``value_difference`` first so worst variances surface."""
    engine = cached_engine()
    with engine.connect() as conn:
        return pd.read_sql_query(
            text(
                """
                SELECT
                    item_name,
                    open_qty, delivered_qty, left_qty, used_qty,
                    pos_difference, recorded_waste, cost,
                    value_used, value_difference,
                    actual_percentage, expected_percentage, diff_percentage
                FROM stg_wisr_inventory_items
                WHERE restaurant_number = :s AND week_end_date = :w
                ORDER BY value_difference NULLS LAST
                """
            ),
            conn,
            params={"s": store_number, "w": week_end},
        )


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def cash_drops_with_deposits(
    store_number: str, start: date, end: date
) -> pd.DataFrame:
    """Cash-drop events alongside the per-day ``deposit_in_bank`` they
    relate to.

    The cash-drop table is event-level; the deposit comes from
    ``stg_controlsheet_weekly``'s seven per-day columns. We unpivot
    those columns via a ``VALUES`` join so the result is one row per
    cash drop with the same-day deposit attached.
    """
    if end < start:
        raise ValueError(f"end ({end}) precedes start ({start})")
    engine = cached_engine()
    with engine.connect() as conn:
        return pd.read_sql_query(
            text(
                """
                WITH deposits AS (
                    SELECT
                        cs.restaurant_number,
                        cs.week_end_date - d.offset_back AS business_date,
                        CASE d.day_name
                            WHEN 'wed' THEN cs.cash_control_deposit_in_bank_wed
                            WHEN 'thu' THEN cs.cash_control_deposit_in_bank_thu
                            WHEN 'fri' THEN cs.cash_control_deposit_in_bank_fri
                            WHEN 'sat' THEN cs.cash_control_deposit_in_bank_sat
                            WHEN 'sun' THEN cs.cash_control_deposit_in_bank_sun
                            WHEN 'mon' THEN cs.cash_control_deposit_in_bank_mon
                            WHEN 'tue' THEN cs.cash_control_deposit_in_bank_tue
                        END AS deposit_in_bank
                    FROM stg_controlsheet_weekly cs
                    CROSS JOIN (
                        VALUES (6, 'wed'), (5, 'thu'), (4, 'fri'), (3, 'sat'),
                               (2, 'sun'), (1, 'mon'), (0, 'tue')
                    ) AS d(offset_back, day_name)
                    WHERE cs.restaurant_number = :s
                )
                SELECT
                    cd.business_date,
                    cd.event_time AS drop_time,
                    cd.clerk_id,
                    cd.clerk_name,
                    d.deposit_in_bank
                FROM stg_cash_drops cd
                LEFT JOIN deposits d
                       ON d.restaurant_number = cd.restaurant_number
                      AND d.business_date     = cd.business_date
                WHERE cd.restaurant_number = :s
                  AND cd.business_date BETWEEN :start AND :end
                ORDER BY cd.event_time
                """
            ),
            conn,
            params={"s": store_number, "start": start, "end": end},
        )


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def list_field_managers() -> list[str]:
    """Active FM names sorted alphabetically — populates the owner-only picker."""
    engine = cached_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT name FROM ref_field_managers "
                "WHERE is_active = true ORDER BY name"
            )
        ).all()
    return [str(r[0]) for r in rows]


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def fm_name_for_email(email: str) -> str | None:
    """Look up the FM ``name`` that owns the given ``email``.

    Returns ``None`` for users (owner/readonly) who aren't field managers.
    """
    if not email:
        return None
    engine = cached_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT name FROM ref_field_managers "
                "WHERE lower(email) = lower(:e)"
            ),
            {"e": email},
        ).first()
    return None if row is None else str(row[0])


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def fm_portfolio_history(fm_name: str, weeks: int) -> pd.DataFrame:
    """The last ``weeks`` rollup rows for one FM, chronologically."""
    if weeks <= 0:
        return pd.DataFrame()
    engine = cached_engine()
    with engine.connect() as conn:
        df = pd.read_sql_query(
            text(
                """
                SELECT
                    week_end_date,
                    store_count, store_count_in_target_food, store_count_in_target_labor,
                    total_net_sales_weighted,
                    portfolio_food_cost_pct,
                    portfolio_labor_cost_pct,
                    is_food_cost_in_portfolio_target,
                    is_labor_cost_in_portfolio_target
                FROM mart_field_manager_portfolio
                WHERE field_manager_name = :fm
                ORDER BY week_end_date DESC
                LIMIT :weeks
                """
            ),
            conn,
            params={"fm": fm_name, "weeks": weeks},
        )
    return df.iloc[::-1].reset_index(drop=True)


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def fm_stores_for_week(fm_name: str, week_end: date) -> pd.DataFrame:
    """The cluster's per-store rows for a single Tuesday week-end."""
    engine = cached_engine()
    with engine.connect() as conn:
        return pd.read_sql_query(
            text(
                """
                SELECT
                    w.restaurant_number,
                    s.store_name,
                    w.net_sales_total,
                    w.food_cost_actual_pct,
                    w.labor_cost_pct,
                    w.cash_overshort_total,
                    w.customer_count,
                    w.average_ticket,
                    w.is_food_cost_in_target,
                    w.is_labor_cost_in_target
                FROM mart_store_weekly w
                JOIN ref_stores s ON s.store_number = w.restaurant_number
                WHERE s.field_manager_name = :fm
                  AND w.week_end_date = :w
                ORDER BY w.restaurant_number
                """
            ),
            conn,
            params={"fm": fm_name, "w": week_end},
        )


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def recon_review_table(
    week_ends: tuple[date, ...],
    store_filter: tuple[str, ...],
    statuses: tuple[str, ...],
) -> pd.DataFrame:
    """Rows for the reconciliation review page.

    Joins ``mart_recon_weekly`` (POS / actual / variance / status) to
    ``ref_stores`` (name) and to ``ops_variance_entries`` (note +
    last-edited-by audit). Empty filters return an empty frame so the
    page doesn't accidentally query the whole history.
    """
    if not week_ends or not store_filter or not statuses:
        return pd.DataFrame()
    engine = cached_engine()
    with engine.connect() as conn:
        return pd.read_sql_query(
            text(
                """
                SELECT
                    r.restaurant_number,
                    s.store_name,
                    r.week_end_date,
                    r.pos_deposit_in_bank,
                    r.actual_bank_deposit,
                    r.variance,
                    r.status,
                    v.note,
                    v.entered_by,
                    v.entered_at
                FROM mart_recon_weekly r
                JOIN ref_stores s ON s.store_number = r.restaurant_number
                LEFT JOIN ops_variance_entries v
                       ON v.restaurant_number = r.restaurant_number
                      AND v.week_end_date     = r.week_end_date
                WHERE r.week_end_date    = ANY(:weeks)
                  AND r.restaurant_number = ANY(:stores)
                  AND r.status            = ANY(:statuses)
                ORDER BY r.week_end_date DESC, r.restaurant_number
                """
            ),
            conn,
            params={
                "weeks": list(week_ends),
                "stores": list(store_filter),
                "statuses": list(statuses),
            },
        )


def save_variance_entries(
    rows: list[dict[str, object]], *, entered_by: str
) -> int:
    """UPSERT a batch of variance entries on (restaurant_number, week_end_date).

    Each ``rows`` dict must carry ``restaurant_number``, ``week_end_date``,
    ``actual_bank_deposit``, and optionally ``note``. ``entered_by`` is
    stamped on every row from the calling page's session — never trust a
    payload to set it.

    Returns the number of rows passed in (every one was either inserted
    or updated). Empty input is a no-op.
    """
    if not rows:
        return 0
    if not entered_by:
        raise ValueError("entered_by is required (audit log)")
    payload = [
        {
            "store": r["restaurant_number"],
            "week": r["week_end_date"],
            "actual": r["actual_bank_deposit"],
            "note": r.get("note"),
            "user": entered_by,
        }
        for r in rows
    ]
    engine = cached_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO ops_variance_entries
                    (restaurant_number, week_end_date, actual_bank_deposit,
                     entered_by, note)
                VALUES (:store, :week, :actual, :user, :note)
                ON CONFLICT (restaurant_number, week_end_date) DO UPDATE SET
                    actual_bank_deposit = EXCLUDED.actual_bank_deposit,
                    entered_by          = EXCLUDED.entered_by,
                    entered_at          = now(),
                    note                = EXCLUDED.note
                """
            ),
            payload,
        )
    return len(payload)


def delete_variance_entries(keys: list[tuple[str, date]]) -> int:
    """Delete the operator-entered rows for the given ``(store, week)`` keys.

    SQLAlchemy's ``text()`` doesn't natively bind tuple IN-lists, so we
    build the placeholders ourselves and bind the values one slot per
    pair. Empty input is a no-op.
    """
    if not keys:
        return 0
    clauses: list[str] = []
    params: dict[str, object] = {}
    for i, (store, week) in enumerate(keys):
        clauses.append(f"(:s{i}, :w{i})")
        params[f"s{i}"] = store
        params[f"w{i}"] = week
    sql = (
        "DELETE FROM ops_variance_entries WHERE "
        "(restaurant_number, week_end_date) IN ("
        + ", ".join(clauses)
        + ")"
    )
    engine = cached_engine()
    with engine.begin() as conn:
        result = conn.execute(text(sql), params)
    return int(result.rowcount or 0)


def recent_week_ends(n: int, today: date | None = None) -> list[date]:
    """Most-recent ``n`` closed Tuesdays as of ``today`` — used as the
    default value for the recon page's week range filter."""
    today = today or date.today()
    _, last_closed = previous_business_week(today)
    return [last_closed - timedelta(days=7 * i) for i in range(max(n, 0))]


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def fm_portfolio(week_end: date) -> pd.DataFrame:
    engine = cached_engine()
    with engine.connect() as conn:
        return pd.read_sql_query(
            text(
                """
                SELECT
                    field_manager_name,
                    store_count, store_count_in_target_food, store_count_in_target_labor,
                    total_net_sales_weighted,
                    portfolio_food_cost_pct,
                    portfolio_labor_cost_pct,
                    is_food_cost_in_portfolio_target,
                    is_labor_cost_in_portfolio_target
                FROM mart_field_manager_portfolio
                WHERE week_end_date = :w
                ORDER BY field_manager_name
                """
            ),
            conn,
            params={"w": week_end},
        )
