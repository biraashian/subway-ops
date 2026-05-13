"""Shared sidebar filters — store picker and week-end picker. Stubs for
Phase 4.6 polish."""

from __future__ import annotations

from datetime import date

import streamlit as st

from subway_ops.calendar import previous_business_week


def store_filter(visible: list[str], key: str = "store_filter") -> list[str]:
    """Multiselect store filter pre-populated with the user's visible cluster."""
    return st.sidebar.multiselect(
        "Stores",
        options=visible,
        default=visible,
        key=key,
    )


def week_end_filter(key: str = "week_end_filter") -> date:
    """Date picker defaulting to the most recently closed Tuesday."""
    _, default_week_end = previous_business_week()
    return st.sidebar.date_input(
        "Week ending (Tuesday)",
        value=default_week_end,
        key=key,
    )
