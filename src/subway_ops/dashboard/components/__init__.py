"""Shared dashboard primitives — palette + KPI bucketing used by every page.

Importing colour and threshold logic from one module keeps the dashboard
internally consistent. Pages should never hand-roll their own thresholds.
"""

from __future__ import annotations

from decimal import Decimal

from subway_ops.config import (
    TARGET_FOOD_COST_PORTFOLIO,
    TARGET_FOOD_COST_STORE,
    TARGET_LABOR_COST_PORTFOLIO,
    TARGET_LABOR_COST_STORE,
)

# Traffic-light palette. Hex values match the dark-theme defaults Streamlit
# ships with so cards look at home next to st.metric() out of the box.
COLOR_IN_TARGET: str = "#16a34a"  # green-600
COLOR_NEAR_TARGET: str = "#f59e0b"  # amber-500
COLOR_OFF_TARGET: str = "#dc2626"  # red-600
COLOR_NEUTRAL: str = "#475569"  # slate-600

# Email-safe palette for the weekly digest. Distinct from the dashboard
# palette: Gmail/Outlook strip <style> blocks and render best with bright,
# saturated tones on a near-white background. Importing from one module
# keeps the dashboard and digest visually coherent (same status semantics,
# slightly different shades).
GREEN: str = "#22c55e"  # green-500
YELLOW: str = "#eab308"  # yellow-500
RED: str = "#ef4444"  # red-500
NEUTRAL_BG: str = "#f9fafb"  # gray-50

# How wide a "near target" amber band is. The playbook spec is +2pp above
# the threshold (≤ target = green; target..target+2pp = yellow; > +2pp = red).
NEAR_TARGET_TOLERANCE: Decimal = Decimal("0.02")

# Emoji indicators used in the grid status columns. Keep next to the
# palette so future themes can rebrand both at once.
EMOJI_IN_TARGET = "🟢"
EMOJI_NEAR_TARGET = "🟡"
EMOJI_OFF_TARGET = "🔴"
EMOJI_UNKNOWN = "⚪"


def status_bucket(
    value: Decimal | float | None,
    target: Decimal,
    *,
    tolerance: Decimal = NEAR_TARGET_TOLERANCE,
) -> str:
    """Bucket a pct against ``target`` into ``in_target`` / ``near`` / ``off``.

    Returns ``"unknown"`` for ``None``. Uses ``Decimal`` math so the
    fractional comparisons can't bite us on float rounding.
    """
    if value is None:
        return "unknown"
    v = value if isinstance(value, Decimal) else Decimal(str(value))
    if v <= target:
        return "in_target"
    if v <= target + tolerance:
        return "near"
    return "off"


def status_emoji(bucket: str) -> str:
    return {
        "in_target": EMOJI_IN_TARGET,
        "near": EMOJI_NEAR_TARGET,
        "off": EMOJI_OFF_TARGET,
    }.get(bucket, EMOJI_UNKNOWN)


def food_cost_emoji(value: Decimal | float | None, *, portfolio: bool = False) -> str:
    """Traffic-light emoji for a fractional food-cost percentage.

    Defaults to the per-store 22% threshold; pass ``portfolio=True`` for
    the FM-level 20% target.
    """
    target = TARGET_FOOD_COST_PORTFOLIO if portfolio else TARGET_FOOD_COST_STORE
    return status_emoji(status_bucket(value, target))


def labor_cost_emoji(value: Decimal | float | None, *, portfolio: bool = False) -> str:
    """Traffic-light emoji for a fractional labor-cost percentage."""
    target = TARGET_LABOR_COST_PORTFOLIO if portfolio else TARGET_LABOR_COST_STORE
    return status_emoji(status_bucket(value, target))


# Compliance buckets. Industry custom for franchise training puts the
# "healthy" mark at 90% and the alert mark at 80%; below 80% the
# operator should be on the phone with the store manager.
COMPLIANCE_GREEN_MIN: Decimal = Decimal("0.90")
COMPLIANCE_YELLOW_MIN: Decimal = Decimal("0.80")


def compliance_bucket(value: Decimal | float | None) -> str:
    """Return ``in_target`` / ``near`` / ``off`` / ``unknown`` for a
    fractional compliance percentage. Mirrors ``status_bucket`` so the
    grid colour helpers can share emoji + colour logic.
    """
    if value is None:
        return "unknown"
    v = value if isinstance(value, Decimal) else Decimal(str(value))
    if v >= COMPLIANCE_GREEN_MIN:
        return "in_target"
    if v >= COMPLIANCE_YELLOW_MIN:
        return "near"
    return "off"


def compliance_emoji(value: Decimal | float | None) -> str:
    return status_emoji(compliance_bucket(value))


# ---------------------------------------------------------------------------
# Session-state keys for cross-page filter persistence.
# ---------------------------------------------------------------------------

# Streamlit session_state survives page navigation as long as keys are
# stable. Centralising the filter keys here means the same week-end and
# store filters appear pre-selected when the operator jumps between
# owner overview, store detail, and FM portfolio.
KEY_FILTER_WEEK_CHOICE = "filter_week_choice"
KEY_FILTER_STORE = "selected_store"
KEY_FILTER_STATUS = "filter_status"
