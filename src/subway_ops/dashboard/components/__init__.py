"""Shared dashboard primitives — colour palette + constants used by pages.

Importing from a single module keeps colour usage consistent across the
KPI cards, the store grid, and any future chart.
"""

from __future__ import annotations

# Traffic-light palette used wherever a value gets compared to a target.
# Hex values match the dark-theme defaults Streamlit ships with so cards
# look at home next to st.metric() out of the box.
COLOR_IN_TARGET: str = "#16a34a"  # green-600
COLOR_NEAR_TARGET: str = "#f59e0b"  # amber-500
COLOR_OFF_TARGET: str = "#dc2626"  # red-600
COLOR_NEUTRAL: str = "#475569"  # slate-600

# How wide a tolerance counts as "near" vs "off" for the amber bucket
# (fractional, same scale as the mart pct columns).
NEAR_TARGET_TOLERANCE = 0.02
