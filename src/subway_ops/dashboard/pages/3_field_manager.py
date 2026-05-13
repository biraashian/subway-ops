"""Field-manager portfolio page.

Owner role: picks any FM from the dropdown. Field-manager role: locked
to the FM whose email matches their login. Read-only users see the
dropdown but can only inspect data — there are no edits on this page
anyway.

Layout:
- FM selector (locked for field_manager role).
- Four KPI cards: portfolio food cost %, labor cost %, total sales,
  stores-in-target count. Each carries a delta-from-target badge.
- Side-by-side store mini-grid sourced from ``mart_store_weekly``.
- Two Altair trends (last 13 weeks) for portfolio food cost and labor
  cost, each with its target reference line (20% / 25%).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, cast

import altair as alt
import pandas as pd
import streamlit as st

from subway_ops.calendar import previous_business_week
from subway_ops.config import (
    TARGET_FOOD_COST_PORTFOLIO,
    TARGET_LABOR_COST_PORTFOLIO,
)
from subway_ops.dashboard.components import (
    COLOR_IN_TARGET,
    COLOR_OFF_TARGET,
    food_cost_emoji,
    labor_cost_emoji,
)
from subway_ops.dashboard.components.helpers import csv_download_button
from subway_ops.dashboard.components.kpi_card import kpi_card
from subway_ops.dashboard.components.sidebar import render_sidebar
from subway_ops.dashboard.data import (
    fm_name_for_email,
    fm_portfolio_history,
    fm_stores_for_week,
    list_field_managers,
)

TREND_WEEKS = 13


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested without Streamlit)
# ---------------------------------------------------------------------------


def delta_badge_text(
    actual: Decimal | float | None,
    target: Decimal,
) -> tuple[str, bool | None]:
    """Return ``("+1.2pp" / "-0.5pp" / "—", in_target_flag)`` for a KPI card.

    Sign convention: positive means OVER the target (bad), negative
    means under (good). ``in_target_flag`` mirrors the sign for the
    KPI card's coloured border.
    """
    if actual is None:
        return "—", None
    a = actual if isinstance(actual, Decimal) else Decimal(str(actual))
    diff_pp = (a - target) * 100
    sign = "+" if diff_pp > 0 else ""
    return f"{sign}{diff_pp:.1f}pp vs target", a <= target


def _format_pct(value: object) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{float(value) * 100:.1f}%"  # type: ignore[arg-type]


def _format_currency(value: object) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"${float(value):,.0f}"  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Page sections
# ---------------------------------------------------------------------------


def _pick_fm(user_role: str, user_email: str) -> str | None:
    if user_role == "field_manager":
        fm = fm_name_for_email(user_email)
        if fm is None:
            st.error(
                f"No ref_field_managers row found for {user_email}. Ask the "
                "owner to update the seed."
            )
            return None
        st.caption(f"Locked to your portfolio: **{fm}**")
        return fm

    fms = list_field_managers()
    if not fms:
        st.warning("No active field managers in ref_field_managers.")
        return None
    # Default to the user's own FM if they happen to be one; otherwise first.
    own_fm = fm_name_for_email(user_email)
    default_idx = fms.index(own_fm) if own_fm in fms else 0
    selected = st.selectbox(
        "Field manager",
        options=fms,
        index=default_idx,
        key="fm_page_selector",
    )
    return selected


def _kpi_row(latest: pd.Series | None) -> None:
    col1, col2, col3, col4 = st.columns(4)
    if latest is None:
        for col, label in zip(
            (col1, col2, col3, col4),
            ("Food cost %", "Labor cost %", "Total sales", "Stores in target"),
            strict=False,
        ):
            with col:
                kpi_card(label=label, value="—", delta="No data yet")
        return

    food_pct = latest.get("portfolio_food_cost_pct")
    labor_pct = latest.get("portfolio_labor_cost_pct")
    total_sales = latest.get("total_net_sales_weighted")
    in_target = latest.get("store_count_in_target_food")
    store_count = latest.get("store_count")

    food_delta, food_ok = delta_badge_text(food_pct, TARGET_FOOD_COST_PORTFOLIO)
    labor_delta, labor_ok = delta_badge_text(labor_pct, TARGET_LABOR_COST_PORTFOLIO)

    with col1:
        kpi_card(
            label=f"Food cost % (target {float(TARGET_FOOD_COST_PORTFOLIO):.0%})",
            value=_format_pct(food_pct),
            delta=food_delta,
            in_target=food_ok,
        )
    with col2:
        kpi_card(
            label=f"Labor cost % (target {float(TARGET_LABOR_COST_PORTFOLIO):.0%})",
            value=_format_pct(labor_pct),
            delta=labor_delta,
            in_target=labor_ok,
        )
    with col3:
        kpi_card(label="Total sales (week)", value=_format_currency(total_sales))
    with col4:
        kpi_card(
            label="Stores in target (food)",
            value=(
                f"{int(in_target)} / {int(store_count)}"
                if pd.notna(in_target) and pd.notna(store_count)
                else "—"
            ),
        )


def _store_grid(fm: str, week_end: pd.Timestamp | None) -> None:
    if week_end is None:
        st.info("Run the weekly mart refresh to populate this section.")
        return
    df = fm_stores_for_week(fm, week_end.date() if hasattr(week_end, "date") else week_end)
    if df.empty:
        st.info("No mart_store_weekly rows for this FM's stores yet.")
        return
    display = df.copy()
    display["food_cost"] = display["food_cost_actual_pct"].apply(_format_pct)
    display["food_cost_status"] = display["food_cost_actual_pct"].apply(food_cost_emoji)
    display["labor_cost"] = display["labor_cost_pct"].apply(_format_pct)
    display["labor_cost_status"] = display["labor_cost_pct"].apply(labor_cost_emoji)
    display["net_sales"] = display["net_sales_total"].apply(_format_currency)
    st.dataframe(
        display[
            [
                "restaurant_number",
                "store_name",
                "net_sales",
                "food_cost",
                "food_cost_status",
                "labor_cost",
                "labor_cost_status",
            ]
        ].rename(
            columns={
                "restaurant_number": "Store",
                "store_name": "Name",
                "net_sales": "Net sales",
                "food_cost": "Food %",
                "food_cost_status": "",
                "labor_cost": "Labor %",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )
    csv_download_button(
        df, filename=f"fm_{fm}_stores.csv", key="fm_stores_csv"
    )


def _trend(df: pd.DataFrame, *, y: str, title: str, target: float) -> alt.Chart:
    base: Any = (
        alt.Chart(df)
        .mark_line(point=True)
        .encode(
            x=alt.X("week_end_date:T", title="Week ending"),
            y=alt.Y(f"{y}:Q", title=title, axis=alt.Axis(format="%")),
            tooltip=[
                alt.Tooltip("week_end_date:T"),
                alt.Tooltip(f"{y}:Q", format=".2%"),
            ],
        )
        .properties(height=240)
    )
    rule = (
        alt.Chart(pd.DataFrame({"y": [target]}))
        .mark_rule(strokeDash=[6, 4], color=COLOR_IN_TARGET)
        .encode(y="y:Q")
    )
    return cast(alt.Chart, base + rule)


def _trend_section(history: pd.DataFrame) -> None:
    if history.empty:
        st.info("Not enough portfolio history yet for the 13-week trends.")
        return
    c1, c2 = st.columns(2)
    with c1:
        chart = _trend(
            history,
            y="portfolio_food_cost_pct",
            title=f"Food cost % (target {float(TARGET_FOOD_COST_PORTFOLIO):.0%})",
            target=float(TARGET_FOOD_COST_PORTFOLIO),
        )
        st.altair_chart(chart, use_container_width=True)
    with c2:
        # labor_cost_pct is NULL upstream until a wage source lands; the
        # chart will simply have no points. The amber target line still
        # tells the operator what to expect.
        if history["portfolio_labor_cost_pct"].notna().any():
            chart = _trend(
                history,
                y="portfolio_labor_cost_pct",
                title=f"Labor cost % (target {float(TARGET_LABOR_COST_PORTFOLIO):.0%})",
                target=float(TARGET_LABOR_COST_PORTFOLIO),
            )
            st.altair_chart(chart, use_container_width=True)
        else:
            st.markdown(
                "<div style='padding:1rem;border-left:4px solid "
                f"{COLOR_OFF_TARGET};'>"
                "<strong>Labor cost % — no data yet.</strong><br>"
                "Pending the wage-cost source on "
                "<code>mart_store_weekly.labor_cost_pct</code>."
                "</div>",
                unsafe_allow_html=True,
            )


def main() -> None:
    if not st.session_state.get("user_email"):
        st.warning("Please log in via the main page.")
        return

    render_sidebar()
    st.title("Field manager portfolio")

    fm = _pick_fm(
        st.session_state.get("user_role", ""),
        st.session_state.get("user_email", ""),
    )
    if not fm:
        return

    history = fm_portfolio_history(fm, TREND_WEEKS)
    latest_row = history.iloc[-1] if not history.empty else None
    latest_week_end = latest_row["week_end_date"] if latest_row is not None else None

    # Fall back to the most-recently-closed business Tuesday if the
    # mart hasn't been refreshed yet (history empty).
    if latest_week_end is None:
        _, fallback = previous_business_week()
        latest_week_end_display = fallback
    else:
        latest_week_end_display = latest_week_end
    st.caption(f"Showing week ending **{latest_week_end_display:%Y-%m-%d}**.")

    _kpi_row(latest_row)
    st.divider()
    st.subheader("Store-by-store")
    _store_grid(fm, latest_week_end)
    st.divider()
    st.subheader(f"Portfolio trends — last {TREND_WEEKS} weeks")
    _trend_section(history)
    if not history.empty:
        csv_download_button(
            history,
            filename=f"fm_{fm}_history.csv",
            key="fm_history_csv",
        )


main()
