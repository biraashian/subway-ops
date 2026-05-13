"""Tests for the owner-overview helpers.

The DB-touching queries are exercised only through their pure parts —
status bucketing, week-selector math, and the weighted-food-cost util.
"""

from __future__ import annotations

import importlib.util
from datetime import date
from decimal import Decimal
from types import ModuleType

import pandas as pd

from subway_ops.config import (
    TARGET_FOOD_COST_PORTFOLIO,
    TARGET_FOOD_COST_STORE,
    TARGET_LABOR_COST_STORE,
)
from subway_ops.dashboard.components import (
    EMOJI_IN_TARGET,
    EMOJI_NEAR_TARGET,
    EMOJI_OFF_TARGET,
    EMOJI_UNKNOWN,
    NEAR_TARGET_TOLERANCE,
    food_cost_emoji,
    labor_cost_emoji,
    status_bucket,
)
from subway_ops.dashboard.data import current_and_last_week_ends


def _load_owner_overview_module() -> ModuleType:
    """Load the digit-prefixed Streamlit page file as a one-off module."""
    spec = importlib.util.spec_from_file_location(
        "owner_overview_module",
        "src/subway_ops/dashboard/pages/1_owner_overview.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Threshold bucketing
# ---------------------------------------------------------------------------


def test_status_bucket_in_target_at_threshold() -> None:
    assert status_bucket(Decimal("0.22"), TARGET_FOOD_COST_STORE) == "in_target"


def test_status_bucket_near_within_tolerance() -> None:
    bucket = status_bucket(
        TARGET_FOOD_COST_STORE + NEAR_TARGET_TOLERANCE,
        TARGET_FOOD_COST_STORE,
    )
    assert bucket == "near"


def test_status_bucket_off_above_tolerance() -> None:
    bucket = status_bucket(
        TARGET_FOOD_COST_STORE + NEAR_TARGET_TOLERANCE + Decimal("0.0001"),
        TARGET_FOOD_COST_STORE,
    )
    assert bucket == "off"


def test_status_bucket_none_unknown() -> None:
    assert status_bucket(None, TARGET_FOOD_COST_STORE) == "unknown"


def test_food_cost_emoji_uses_store_target_by_default() -> None:
    # 0.21 < 0.22 → green
    assert food_cost_emoji(Decimal("0.21")) == EMOJI_IN_TARGET
    # 0.23 is within +2pp of 0.22 → yellow
    assert food_cost_emoji(Decimal("0.23")) == EMOJI_NEAR_TARGET
    # 0.30 is off
    assert food_cost_emoji(Decimal("0.30")) == EMOJI_OFF_TARGET
    assert food_cost_emoji(None) == EMOJI_UNKNOWN


def test_food_cost_emoji_portfolio_uses_tighter_target() -> None:
    # Per-store target is 0.22 (would be green), portfolio is 0.20 (red).
    assert food_cost_emoji(Decimal("0.21"), portfolio=False) == EMOJI_IN_TARGET
    assert (
        food_cost_emoji(TARGET_FOOD_COST_PORTFOLIO + Decimal("0.05"), portfolio=True)
        == EMOJI_OFF_TARGET
    )


def test_labor_cost_emoji_against_store_target() -> None:
    # 0.27 < 0.28 → green
    assert labor_cost_emoji(Decimal("0.27")) == EMOJI_IN_TARGET
    # 0.29 is within +2pp of 0.28 → yellow
    assert labor_cost_emoji(Decimal("0.29")) == EMOJI_NEAR_TARGET
    # 0.31 > 0.28 + 0.02 → red
    assert labor_cost_emoji(TARGET_LABOR_COST_STORE + Decimal("0.05")) == EMOJI_OFF_TARGET


# ---------------------------------------------------------------------------
# Week selector
# ---------------------------------------------------------------------------


def test_current_and_last_week_ends_on_wednesday() -> None:
    """On a Wednesday, current_we is six days out and last_closed_we is yesterday."""
    today = date(2026, 5, 13)  # Wednesday
    current, last_closed = current_and_last_week_ends(today=today)
    assert current == date(2026, 5, 19)  # next Tuesday
    assert last_closed == date(2026, 5, 12)  # yesterday (Tuesday)


def test_current_and_last_week_ends_on_tuesday() -> None:
    """On a Tuesday, today IS the current week-end and the prior Tuesday closed."""
    today = date(2026, 5, 12)
    current, last_closed = current_and_last_week_ends(today=today)
    assert current == today
    assert last_closed == date(2026, 5, 5)


# ---------------------------------------------------------------------------
# Sales-weighted food cost
# ---------------------------------------------------------------------------


def test_weighted_food_cost_direct_call() -> None:
    """Pull the helper from the owner-overview page module by file path."""
    module = _load_owner_overview_module()
    df = pd.DataFrame(
        {
            "food_cost_actual_pct": [Decimal("0.18"), Decimal("0.30"), None],
            "net_sales_total": [Decimal("10000"), Decimal("1000"), Decimal("5000")],
        }
    )
    result = module._weighted_food_cost(df)
    # (0.18*10000 + 0.30*1000) / (10000 + 1000) = 2100 / 11000 ≈ 0.190909
    assert result is not None
    assert abs(result - Decimal("0.190909")) < Decimal("0.0001")


def test_weighted_food_cost_returns_none_when_no_rows_have_pct() -> None:
    module = _load_owner_overview_module()
    df = pd.DataFrame(
        {
            "food_cost_actual_pct": [None, None],
            "net_sales_total": [Decimal("100"), Decimal("200")],
        }
    )
    assert module._weighted_food_cost(df) is None
