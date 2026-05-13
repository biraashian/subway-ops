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
