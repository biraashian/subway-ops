"""Owner overview page.

Top: a Tuesday-week toggle ("Current week (in progress)" vs "Last
closed week"). KPI cards summarise the visible portfolio. Beneath them,
a sortable, colour-coded grid lets the operator scan all visible stores;
clicking a row drills into the store detail page. A 13-week net-sales
trend rounds out the page.

Reconciliation columns (recon_status, recon_variance) are placeholders
until Task 5.1 lands ``mart_recon_weekly`` — we display "—" and a small
banner rather than fake the data.
"""

from __future__ import annotations

from decimal import Decimal

import altair as alt
import pandas as pd
import streamlit as st

from subway_ops.dashboard.components import (
    EMOJI_UNKNOWN,
    food_cost_emoji,
    labor_cost_emoji,
)
from subway_ops.dashboard.components.kpi_card import kpi_card
from subway_ops.dashboard.data import (
    current_and_last_week_ends,
    portfolio_trend,
    weekly_overview,
)

TREND_WEEKS = 13


def _weighted_food_cost(df: pd.DataFrame) -> Decimal | None:
    """Sales-weighted portfolio food-cost across the rows currently shown."""
    if df.empty:
        return None
    mask = df["food_cost_actual_pct"].notna() & df["net_sales_total"].notna()
    sub = df.loc[mask, ["food_cost_actual_pct", "net_sales_total"]]
    if sub.empty:
        return None
    denom = sub["net_sales_total"].sum()
    if not denom or denom == 0:
        return None
    weighted = (sub["food_cost_actual_pct"] * sub["net_sales_total"]).sum() / denom
    return Decimal(str(weighted))


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal | int | float):
        f = float(value)
        return None if pd.isna(f) else f
    return float(str(value))


def _format_currency(value: object) -> str:
    f = _to_float(value)
    return "—" if f is None else f"${f:,.0f}"


def _format_pct(value: object) -> str:
    f = _to_float(value)
    return "—" if f is None else f"{f * 100:.1f}%"


def _build_display_df(df: pd.DataFrame) -> pd.DataFrame:
    """Add status emoji columns and pretty-print pct/money for the grid."""
    out = df.copy()
    out["food_cost"] = out["food_cost_actual_pct"].apply(_format_pct)
    out["food_cost_status"] = out["food_cost_actual_pct"].apply(food_cost_emoji)
    out["labor_cost"] = out["labor_cost_pct"].apply(_format_pct)
    out["labor_cost_status"] = out["labor_cost_pct"].apply(labor_cost_emoji)
    out["net_sales"] = out["net_sales_total"].apply(_format_currency)
    out["cash_overshort"] = out["cash_overshort_total"].apply(_format_currency)
    out["recon_status"] = EMOJI_UNKNOWN  # Task 5.1 fills this in
    out["recon_variance"] = "—"
    return out[
        [
            "restaurant_number",
            "store_name",
            "field_manager_name",
            "net_sales",
            "transactions_total",
            "food_cost",
            "food_cost_status",
            "labor_cost",
            "labor_cost_status",
            "cash_overshort",
            "recon_status",
            "recon_variance",
        ]
    ].rename(
        columns={
            "restaurant_number": "store",
            "store_name": "name",
            "field_manager_name": "FM",
            "transactions_total": "txns",
        }
    )


def _render_kpi_row(df: pd.DataFrame) -> None:
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    total_sales = float(df["net_sales_total"].fillna(0).sum())
    total_txns = int(df["transactions_total"].fillna(0).sum()) if not df.empty else 0
    weighted_food = _weighted_food_cost(df)
    in_target_count = int(df["is_food_cost_in_target"].fillna(False).sum())
    total_count = len(df)

    with col1:
        kpi_card(label="Total net sales (week)", value=f"${total_sales:,.0f}")
    with col2:
        kpi_card(label="Total transactions", value=f"{total_txns:,}")
    with col3:
        in_target = (
            None if weighted_food is None
            else weighted_food <= Decimal("0.22")
        )
        kpi_card(
            label="Portfolio food cost %",
            value=_format_pct(weighted_food) if weighted_food is not None else "—",
            in_target=in_target,
        )
    with col4:
        kpi_card(
            label="Portfolio labor cost %",
            value="—",
            delta="Pending wage source",
        )
    with col5:
        kpi_card(
            label="Stores in target",
            value=f"{in_target_count} / {total_count}" if total_count else "—",
        )
    with col6:
        kpi_card(
            label="Reconciliation status",
            value="—",
            delta="Lands in Task 5.1",
        )


def _render_grid(df: pd.DataFrame) -> None:
    if df.empty:
        st.info(
            "No mart_store_weekly rows yet for the selected week. "
            "Run the backfill or wait for the 4-hour mart refresh cron."
        )
        return
    display = _build_display_df(df)
    event = st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        selection_mode="single-row",
        on_select="rerun",
        column_config={
            "store": st.column_config.TextColumn("Store #", width="small"),
            "name": st.column_config.TextColumn("Name", width="medium"),
            "FM": st.column_config.TextColumn("Field manager", width="small"),
            "net_sales": st.column_config.TextColumn("Net sales", width="small"),
            "txns": st.column_config.NumberColumn("Txns", width="small"),
            "food_cost": st.column_config.TextColumn("Food %", width="small"),
            "food_cost_status": st.column_config.TextColumn("", width="small"),
            "labor_cost": st.column_config.TextColumn("Labor %", width="small"),
            "labor_cost_status": st.column_config.TextColumn("", width="small"),
            "cash_overshort": st.column_config.TextColumn("Cash o/s", width="small"),
            "recon_status": st.column_config.TextColumn("Recon", width="small"),
            "recon_variance": st.column_config.TextColumn("Variance", width="small"),
        },
        key="owner_overview_grid",
    )
    selection_rows = getattr(event, "selection", {}).get("rows") if event else None
    if selection_rows:
        idx = selection_rows[0]
        st.session_state["selected_store"] = str(display.iloc[idx]["store"])
        st.switch_page("pages/2_store_detail.py")


def _render_trend(stores: tuple[str, ...]) -> None:
    trend = portfolio_trend(TREND_WEEKS, stores)
    if trend.empty:
        st.info("Not enough weekly mart rows to draw the 13-week trend yet.")
        return
    chart = (
        alt.Chart(trend)
        .mark_line(point=True)
        .encode(
            x=alt.X("week_end_date:T", title="Week ending"),
            y=alt.Y("net_sales:Q", title="Net sales ($)"),
            tooltip=["week_end_date:T", alt.Tooltip("net_sales:Q", format="$,.0f")],
        )
        .properties(height=260)
    )
    st.altair_chart(chart, use_container_width=True)


def main() -> None:
    if not st.session_state.get("user_email"):
        st.warning("Please log in via the main page.")
        return

    st.title("Owner overview")

    visible = tuple(st.session_state.get("assigned_stores", []))
    if not visible:
        st.error("No stores visible for your role.")
        return

    current_we, last_closed_we = current_and_last_week_ends()
    week_choice = st.radio(
        "Week",
        options=("Last closed week", "Current week (in progress)"),
        index=0,
        horizontal=True,
        key="owner_overview_week_choice",
    )
    week_end = last_closed_we if week_choice.startswith("Last") else current_we
    st.caption(f"Showing data for week ending **{week_end:%Y-%m-%d}** (Tuesday).")

    df = weekly_overview(week_end, visible)
    _render_kpi_row(df)
    st.divider()
    _render_grid(df)
    st.divider()
    st.subheader(f"Portfolio net sales — last {TREND_WEEKS} weeks")
    _render_trend(visible)


main()
