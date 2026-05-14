"""Regression tests for the ``decimal.InvalidOperation`` crash class.

Before the fix, ``status_bucket`` / ``compliance_bucket`` /
``delta_badge_text`` would all crash when handed a NaN, ``pd.NA``, or
non-numeric string — which happens whenever a NULL ``NUMERIC`` column
gets widened to a float64 series by pandas. The dashboard then 500'd
mid-render on the owner overview and the field-manager page.

These tests pin the contract: every "missing" sentinel collapses to
the "unknown" bucket (and ``delta_badge_text`` collapses to
``("—", None)``), so the UI renders a neutral placeholder instead of
crashing.
"""

from __future__ import annotations

import importlib.util
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from subway_ops.config import TARGET_FOOD_COST_STORE
from subway_ops.dashboard.components import (
    EMOJI_UNKNOWN,
    compliance_bucket,
    compliance_emoji,
    food_cost_emoji,
    labor_cost_emoji,
    safe_decimal,
    status_bucket,
)

# Values that should every count as "missing" from the dashboard's
# point of view. ``pd.NaT`` shows up if a date column collapses to NaN.
MISSING_VALUES: list[Any] = [
    None,
    float("nan"),
    np.nan,
    pd.NA,
    pd.NaT,
    "",
    "NaN",
    "None",
    "not a number",
]


# ---------------------------------------------------------------------------
# safe_decimal
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("missing", MISSING_VALUES)
def test_safe_decimal_returns_none_for_missing(missing: Any) -> None:
    """Every flavour of missing → None, not an exception."""
    assert safe_decimal(missing) is None


def test_safe_decimal_passes_through_decimal() -> None:
    assert safe_decimal(Decimal("0.22")) == Decimal("0.22")


def test_safe_decimal_rejects_decimal_nan() -> None:
    """A Decimal that's already NaN is still a Decimal — filter it."""
    assert safe_decimal(Decimal("NaN")) is None


def test_safe_decimal_converts_float() -> None:
    out = safe_decimal(0.22)
    assert out == Decimal("0.22")


def test_safe_decimal_converts_int() -> None:
    assert safe_decimal(1) == Decimal("1")


def test_safe_decimal_honours_default() -> None:
    sentinel = Decimal("-1")
    assert safe_decimal(None, default=sentinel) == sentinel
    assert safe_decimal(float("nan"), default=sentinel) == sentinel


def test_safe_decimal_handles_infinity() -> None:
    """``inf`` is non-finite — treat it as missing for KPI math."""
    assert safe_decimal(float("inf")) is None
    assert safe_decimal(float("-inf")) is None


# ---------------------------------------------------------------------------
# status_bucket
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("missing", MISSING_VALUES)
def test_status_bucket_missing_values_are_unknown(missing: Any) -> None:
    """The pre-fix crash path: NaN / pd.NA / None blew up on
    ``Decimal(str(value))`` and propagated out of the page render."""
    assert status_bucket(missing, TARGET_FOOD_COST_STORE) == "unknown"


def test_status_bucket_in_target_below_target() -> None:
    assert status_bucket(Decimal("0.20"), TARGET_FOOD_COST_STORE) == "in_target"


def test_status_bucket_near_target_within_tolerance() -> None:
    # 22% target + 2pp tolerance → 23% is "near".
    assert status_bucket(Decimal("0.23"), TARGET_FOOD_COST_STORE) == "near"


def test_status_bucket_off_target_above_tolerance() -> None:
    assert status_bucket(Decimal("0.30"), TARGET_FOOD_COST_STORE) == "off"


# ---------------------------------------------------------------------------
# compliance_bucket
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("missing", MISSING_VALUES)
def test_compliance_bucket_missing_values_are_unknown(missing: Any) -> None:
    assert compliance_bucket(missing) == "unknown"


def test_compliance_bucket_recognises_known_thresholds() -> None:
    assert compliance_bucket(Decimal("0.92")) == "in_target"
    assert compliance_bucket(Decimal("0.85")) == "near"
    assert compliance_bucket(Decimal("0.50")) == "off"


# ---------------------------------------------------------------------------
# Emoji helpers — they're 1:1 with their buckets but the dashboard calls
# them directly, so cover the missing-value path end-to-end.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("missing", MISSING_VALUES)
def test_food_cost_emoji_neutral_for_missing(missing: Any) -> None:
    assert food_cost_emoji(missing) == EMOJI_UNKNOWN


@pytest.mark.parametrize("missing", MISSING_VALUES)
def test_food_cost_emoji_portfolio_neutral_for_missing(missing: Any) -> None:
    """Same contract for the FM portfolio variant (different target)."""
    assert food_cost_emoji(missing, portfolio=True) == EMOJI_UNKNOWN


@pytest.mark.parametrize("missing", MISSING_VALUES)
def test_labor_cost_emoji_neutral_for_missing(missing: Any) -> None:
    assert labor_cost_emoji(missing) == EMOJI_UNKNOWN


@pytest.mark.parametrize("missing", MISSING_VALUES)
def test_compliance_emoji_neutral_for_missing(missing: Any) -> None:
    assert compliance_emoji(missing) == EMOJI_UNKNOWN


# ---------------------------------------------------------------------------
# delta_badge_text — page-level helper, lives on the FM page.
#
# The page filename starts with a digit so we can't ``import`` it normally;
# load it via importlib so the test can call the pure helper.
# ---------------------------------------------------------------------------


def _load_fm_page() -> Any:
    path = Path(__file__).parent.parent / (
        "src/subway_ops/dashboard/pages/3_field_manager.py"
    )
    spec = importlib.util.spec_from_file_location("fm_page_under_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def fm_page() -> Any:
    return _load_fm_page()


@pytest.mark.parametrize("missing", MISSING_VALUES)
def test_delta_badge_text_missing_value_neutral(fm_page: Any, missing: Any) -> None:
    """The other pre-fix crash path. ``Decimal(str(NaN))`` exploded
    before reaching the comparison; now we collapse to the placeholder."""
    text, in_target = fm_page.delta_badge_text(missing, TARGET_FOOD_COST_STORE)
    assert text == "—"
    assert in_target is None


def test_delta_badge_text_under_target_is_in_target(fm_page: Any) -> None:
    text, in_target = fm_page.delta_badge_text(
        Decimal("0.18"), TARGET_FOOD_COST_STORE
    )
    assert "-" in text  # negative delta
    assert "pp vs target" in text
    assert in_target is True


def test_delta_badge_text_over_target_is_off(fm_page: Any) -> None:
    text, in_target = fm_page.delta_badge_text(
        Decimal("0.25"), TARGET_FOOD_COST_STORE
    )
    assert text.startswith("+")
    assert in_target is False


def test_delta_badge_text_accepts_float(fm_page: Any) -> None:
    """The mart helpers sometimes hand us floats (pandas widened
    NUMERIC → float64). The helper must accept those."""
    text, in_target = fm_page.delta_badge_text(0.21, TARGET_FOOD_COST_STORE)
    assert "pp vs target" in text
    assert in_target is True
