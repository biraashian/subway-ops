"""Single-metric KPI card. Placeholder for Phase 4.2 — real charts land
when the owner overview page wires in mart data."""

from __future__ import annotations

import streamlit as st

from subway_ops.dashboard.components import (
    COLOR_IN_TARGET,
    COLOR_NEUTRAL,
    COLOR_OFF_TARGET,
)


def kpi_card(
    *,
    label: str,
    value: str,
    delta: str | None = None,
    in_target: bool | None = None,
) -> None:
    """Render a small KPI block. ``in_target=None`` skips the colour band."""
    color = (
        COLOR_IN_TARGET
        if in_target is True
        else COLOR_OFF_TARGET
        if in_target is False
        else COLOR_NEUTRAL
    )
    st.markdown(
        f"<div style='padding:0.5rem;border-left:4px solid {color};'>"
        f"<div style='color:#64748b;font-size:0.85rem'>{label}</div>"
        f"<div style='font-size:1.6rem;font-weight:600'>{value}</div>"
        + (f"<div style='font-size:0.85rem'>{delta}</div>" if delta else "")
        + "</div>",
        unsafe_allow_html=True,
    )
