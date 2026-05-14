"""Shared dashboard primitives — palette + KPI bucketing used by every page.

Importing colour and threshold logic from one module keeps the dashboard
internally consistent. Pages should never hand-roll their own thresholds.
"""

from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation
from typing import Any

from subway_ops.config import (
    TARGET_FOOD_COST_PORTFOLIO,
    TARGET_FOOD_COST_STORE,
    TARGET_LABOR_COST_PORTFOLIO,
    TARGET_LABOR_COST_STORE,
)


def safe_decimal(value: Any, *, default: Decimal | None = None) -> Decimal | None:
    """Coerce a possibly-missing DB value into a ``Decimal`` or ``default``.

    Treats every flavour of "missing" the dashboard sees in practice as
    ``default`` rather than letting ``Decimal(str(value))`` blow up with
    ``InvalidOperation``:

    - ``None``
    - float / numpy ``NaN`` (NULL Numeric columns surface as NaN when
      pandas widens the column to float64)
    - ``pd.NA`` / any sentinel where ``not bool(x == x)`` would have
      flagged NaN — we check ``x != x`` defensively via ``math.isnan``
      after a float coercion
    - strings like ``"NaN"`` / ``"None"`` / ``""``
    - any value that ``Decimal(str(value))`` rejects outright

    Returning ``None`` (or the caller's chosen default) lets the
    consumer take the "unknown" branch instead of crashing.
    """
    if value is None:
        return default
    if isinstance(value, Decimal):
        # Already a Decimal — but Decimal('NaN') is still a Decimal,
        # and comparing it against another Decimal raises. Filter it.
        return default if value.is_nan() else value
    if value is False or value is True:
        # bools are ints — keep the explicit allow.
        return Decimal(int(value))
    # Numeric path: pandas / numpy / int / float / numeric-string.
    # float() raises TypeError on pd.NA / NaT and ValueError on bad
    # strings; non-finite floats (NaN / inf) collapse to the default
    # too. Then convert via repr(f) for floats (avoids 0.1 →
    # Decimal('0.10000000000000000555…')) and str(value) otherwise.
    try:
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return default
        return Decimal(repr(f)) if isinstance(value, float) else Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        return default


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

    Returns ``"unknown"`` for any missing value (``None``, NaN,
    ``pd.NA``, non-numeric strings, etc.). Uses ``Decimal`` math so the
    fractional comparisons can't bite us on float rounding.
    """
    v = safe_decimal(value)
    if v is None:
        return "unknown"
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
    grid colour helpers can share emoji + colour logic — including the
    same NaN / ``pd.NA`` / ``None`` tolerance.
    """
    v = safe_decimal(value)
    if v is None:
        return "unknown"
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
