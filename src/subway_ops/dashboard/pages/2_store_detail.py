"""Store detail drill-down.

Four tabs:
1. **Daily trend** — 30 days of net sales, transactions, sales/labor hour,
   food-cost % from ``mart_store_daily`` with the per-store target line
   on food cost.
2. **Weekly history** — last 13 weeks from ``mart_store_weekly``, same
   KPIs at the weekly grain plus the 22% / 28% target reference lines.
3. **Inventory detail** — ``stg_wisr_inventory_items`` for a chosen
   week, sorted with the worst negative ``value_difference`` first; the
   value-difference column carries a red/green chip.
4. **Cash drops** — ``stg_cash_drops`` events for a chosen date range,
   each row joined to the same-day ``deposit_in_bank`` from
   ``stg_controlsheet_weekly``.

The store selector defaults to ``st.session_state["selected_store"]``
(set when a row on the owner overview is clicked) and is otherwise the
first store in the user's visible cluster.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, cast

import altair as alt
import pandas as pd
import streamlit as st

from subway_ops.calendar import business_date_now, previous_business_week
from subway_ops.config import (
    TARGET_FOOD_COST_STORE,
    TARGET_LABOR_COST_STORE,
)
from subway_ops.dashboard.components import (
    COLOR_IN_TARGET,
    COLOR_OFF_TARGET,
    COMPLIANCE_GREEN_MIN,
)
from subway_ops.dashboard.components.helpers import csv_download_button
from subway_ops.dashboard.components.sidebar import render_sidebar
from subway_ops.dashboard.data import (
    cash_drops_with_deposits,
    get_compliance_summary,
    get_store_compliance_detail,
    get_store_compliance_trend,
    store_daily,
    store_weekly_history,
    wisr_inventory_items,
)

DAILY_LOOKBACK_DAYS = 30
WEEKLY_LOOKBACK_WEEKS = 13
TRAINING_TREND_WEEKS = 13


def _pick_store(visible: list[str]) -> str | None:
    default = st.session_state.get("selected_store") or (visible[0] if visible else None)
    if default not in visible:
        default = visible[0] if visible else None
    if not default:
        return None
    selected = st.selectbox(
        "Store",
        options=visible,
        index=visible.index(default),
        key="store_detail_selectbox",
    )
    st.session_state["selected_store"] = selected
    return selected


def _line_chart(
    df: pd.DataFrame,
    *,
    x: str,
    y: str,
    title: str,
    y_format: str | None = None,
    target: float | None = None,
) -> alt.Chart:
    base: Any = (
        alt.Chart(df)
        .mark_line(point=True)
        .encode(
            x=alt.X(f"{x}:T", title=title and x.replace("_", " ")),
            y=alt.Y(
                f"{y}:Q",
                title=title,
                axis=alt.Axis(format=y_format) if y_format else alt.Undefined,
            ),
            tooltip=[
                alt.Tooltip(f"{x}:T"),
                alt.Tooltip(f"{y}:Q", format=y_format or ",.2f"),
            ],
        )
        .properties(height=240)
    )
    if target is None:
        return cast(alt.Chart, base)
    rule = (
        alt.Chart(pd.DataFrame({"y": [target]}))
        .mark_rule(strokeDash=[6, 4], color=COLOR_IN_TARGET)
        .encode(y="y:Q")
    )
    return cast(alt.Chart, base + rule)


def _daily_trend_tab(store: str) -> None:
    end = business_date_now()
    start = end - timedelta(days=DAILY_LOOKBACK_DAYS)
    st.caption(f"Showing {start:%Y-%m-%d} through {end:%Y-%m-%d}.")
    df = store_daily(store, start, end)
    if df.empty:
        st.info("No mart_store_daily rows for this store yet in the lookback window.")
        return

    csv_download_button(
        df, filename=f"{store}_daily_{start}_{end}.csv", key="store_detail_daily_csv"
    )

    c1, c2 = st.columns(2)
    with c1:
        chart = _line_chart(
            df, x="business_date", y="net_sales",
            title="Net sales ($)", y_format="$,.0f",
        )
        st.altair_chart(chart, use_container_width=True)
    with c2:
        chart = _line_chart(
            df, x="business_date", y="transactions", title="Transactions",
        )
        st.altair_chart(chart, use_container_width=True)
    c3, c4 = st.columns(2)
    with c3:
        chart = _line_chart(
            df, x="business_date", y="sales_per_labor_hour",
            title="Sales / labor hour ($)", y_format="$,.0f",
        )
        st.altair_chart(chart, use_container_width=True)
    with c4:
        chart = _line_chart(
            df, x="business_date", y="food_cost_pct",
            title=f"Food cost % (target {float(TARGET_FOOD_COST_STORE):.0%})",
            y_format="%", target=float(TARGET_FOOD_COST_STORE),
        )
        st.altair_chart(chart, use_container_width=True)


def _weekly_history_tab(store: str) -> None:
    df = store_weekly_history(store, WEEKLY_LOOKBACK_WEEKS)
    if df.empty:
        st.info("No mart_store_weekly rows for this store yet.")
        return
    csv_download_button(
        df,
        filename=f"{store}_weekly_history.csv",
        key="store_detail_weekly_csv",
    )
    st.caption(
        f"Showing the last {len(df)} closed weeks (target food cost "
        f"{float(TARGET_FOOD_COST_STORE):.0%}, target labor cost "
        f"{float(TARGET_LABOR_COST_STORE):.0%})."
    )

    c1, c2 = st.columns(2)
    with c1:
        chart = _line_chart(
            df, x="week_end_date", y="net_sales_total",
            title="Net sales ($)", y_format="$,.0f",
        )
        st.altair_chart(chart, use_container_width=True)
    with c2:
        chart = _line_chart(
            df, x="week_end_date", y="transactions_total", title="Transactions",
        )
        st.altair_chart(chart, use_container_width=True)
    c3, c4 = st.columns(2)
    with c3:
        chart = _line_chart(
            df, x="week_end_date", y="food_cost_actual_pct",
            title="Food cost %", y_format="%",
            target=float(TARGET_FOOD_COST_STORE),
        )
        st.altair_chart(chart, use_container_width=True)
    with c4:
        chart = _line_chart(
            df, x="week_end_date", y="labor_cost_pct",
            title="Labor cost %", y_format="%",
            target=float(TARGET_LABOR_COST_STORE),
        )
        st.altair_chart(chart, use_container_width=True)


def _style_value_difference(val: object) -> str:
    """Red text for negative variance (used MORE than expected), green
    for positive. Returns a CSS string that pandas Styler applies."""
    if val is None or pd.isna(val):
        return ""
    try:
        f = float(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return ""
    if f < 0:
        return f"color: {COLOR_OFF_TARGET}"
    if f > 0:
        return f"color: {COLOR_IN_TARGET}"
    return ""


def _inventory_tab(store: str) -> None:
    _, default_week_end = previous_business_week()
    week_end = st.date_input(
        "Week ending (Tuesday)",
        value=default_week_end,
        key="store_detail_wisr_week",
    )
    df = wisr_inventory_items(store, week_end)
    if df.empty:
        st.info(
            "No WISR inventory rows for this store + week. The WISR endpoint "
            "is weekly and may not have closed yet."
        )
        return
    styled = df.style.map(_style_value_difference, subset=["value_difference"])
    st.dataframe(styled, use_container_width=True, hide_index=True)
    csv_download_button(
        df,
        filename=f"{store}_wisr_{week_end}.csv",
        key="store_detail_wisr_csv",
    )


def _cash_drops_tab(store: str) -> None:
    _, default_week_end = previous_business_week()
    default_start = default_week_end - timedelta(days=6)
    range_value = st.date_input(
        "Date range",
        value=(default_start, default_week_end),
        key="store_detail_cashdrops_range",
    )
    if not isinstance(range_value, tuple) or len(range_value) != 2:
        st.info("Pick a start and end date.")
        return
    start, end = range_value
    df = cash_drops_with_deposits(store, start, end)
    if df.empty:
        st.info("No cash-drop events for this store in the selected range.")
        return
    display = df.copy()
    display["drop_time"] = pd.to_datetime(display["drop_time"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    display["deposit_in_bank"] = display["deposit_in_bank"].apply(
        lambda v: f"${float(v):,.2f}" if v is not None and not pd.isna(v) else "—"
    )
    st.dataframe(
        display[["business_date", "drop_time", "clerk_id", "clerk_name", "deposit_in_bank"]],
        use_container_width=True,
        hide_index=True,
    )
    csv_download_button(
        df,
        filename=f"{store}_cash_drops_{start}_{end}.csv",
        key="store_detail_cashdrops_csv",
    )


def _training_tab(store: str) -> None:
    """Three-stack training view: trend → per-employee table → overdue list.

    Compliance data is per-(store, report_date); the summary helper
    finds the latest report on/before today and the trend chart
    backfills the prior reports.
    """
    today = business_date_now()
    summary = get_compliance_summary(today, (store,))
    if summary.empty:
        st.info(
            "No uOS compliance data for this store yet. The uos_pull "
            "workflow lands new reports daily once Gmail is wired up."
        )
        return

    latest = summary.iloc[0]
    report_date = pd.to_datetime(latest["latest_report_date"]).date()
    pct = latest["compliance_pct"]
    pct_value = float(pct) if pct is not None and not pd.isna(pct) else None

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric(
            "Compliance %",
            "—" if pct_value is None else f"{pct_value * 100:.1f}%",
            help=f"Latest report: {report_date:%Y-%m-%d}",
        )
    with c2:
        st.metric("Overdue", int(latest["overdue_cells"]))
    with c3:
        st.metric("Pending", int(latest["pending_cells"]))

    trend = get_store_compliance_trend(store, TRAINING_TREND_WEEKS)
    if not trend.empty:
        chart_df = trend.copy()
        chart_df["compliance_pct"] = pd.to_numeric(
            chart_df["compliance_pct"], errors="coerce"
        )
        chart = _line_chart(
            chart_df,
            x="report_date",
            y="compliance_pct",
            title=(
                f"Compliance % (green ≥ "
                f"{float(COMPLIANCE_GREEN_MIN):.0%})"
            ),
            y_format="%",
            target=float(COMPLIANCE_GREEN_MIN),
        )
        st.altair_chart(chart, use_container_width=True)

    detail = get_store_compliance_detail(store, report_date)
    if detail.empty:
        return

    st.subheader(f"Per-employee detail — {report_date:%Y-%m-%d}")
    # Per-employee compliance %: complete / total across courses.
    grouped = (
        detail.assign(
            is_complete=detail["completion_status"].eq("complete").astype(int),
        )
        .groupby("employee_name", as_index=False)
        .agg(
            courses=("course_name", "count"),
            complete=("is_complete", "sum"),
        )
    )
    grouped["compliance_pct"] = grouped["complete"] / grouped["courses"]
    grouped["compliance_label"] = grouped["compliance_pct"].apply(
        lambda v: "—" if pd.isna(v) else f"{v * 100:.0f}%"
    )
    st.dataframe(
        grouped[["employee_name", "courses", "complete", "compliance_label"]].rename(
            columns={"compliance_label": "compliance"}
        ),
        use_container_width=True,
        hide_index=True,
    )

    overdue = detail[detail["completion_status"] == "overdue"].copy()
    if not overdue.empty:
        st.subheader("Overdue items")
        overdue["days_overdue"] = (
            pd.Timestamp(report_date)
            - pd.to_datetime(overdue["completed_at"], errors="coerce")
        ).dt.days
        overdue["days_overdue"] = overdue["days_overdue"].fillna("—")
        ordered = overdue[
            ["employee_name", "course_name", "completed_at", "days_overdue"]
        ].sort_values(
            "days_overdue",
            ascending=False,
            key=lambda s: pd.to_numeric(s, errors="coerce"),
        )
        st.dataframe(ordered, use_container_width=True, hide_index=True)
    csv_download_button(
        detail,
        filename=f"{store}_compliance_{report_date}.csv",
        key="store_detail_training_csv",
    )


def main() -> None:
    if not st.session_state.get("user_email"):
        st.warning("Please log in via the main page.")
        return

    render_sidebar()
    visible = list(st.session_state.get("assigned_stores", []))
    if not visible:
        st.error("No stores visible for your role.")
        return

    st.title("Store detail")
    store = _pick_store(visible)
    if not store:
        return

    daily_tab, weekly_tab, inventory_tab, cash_tab, training_tab = st.tabs(
        ["Daily trend", "Weekly history", "Inventory detail", "Cash drops", "Training"]
    )
    with daily_tab:
        _daily_trend_tab(store)
    with weekly_tab:
        _weekly_history_tab(store)
    with inventory_tab:
        _inventory_tab(store)
    with cash_tab:
        _cash_drops_tab(store)
    with training_tab:
        _training_tab(store)


main()
