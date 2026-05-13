"""Cached DB query helpers used by the dashboard pages.

Streamlit's caching primitives let us run the SQL once per (input, TTL)
combination — the engine itself is a process-wide singleton, the marts
get refreshed every 4 hours by the cron, and a 5-minute query cache is a
nice compromise between freshness and load on the Supabase free tier.

All helpers return ``pandas.DataFrame`` so pages can render directly via
``st.dataframe`` / ``st.bar_chart`` etc.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st
from sqlalchemy import Engine, text

from subway_ops.db.connection import get_engine as _get_engine

CACHE_TTL_SECONDS = 300


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
    """One row per visible store for the given Tuesday week-end."""
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
                    w.week_end_date,
                    w.net_sales_total,
                    w.transactions_total,
                    w.customer_count,
                    w.average_ticket,
                    w.productivity,
                    w.food_cost_actual_pct,
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
