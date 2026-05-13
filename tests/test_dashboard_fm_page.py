"""Tests for the field-manager portfolio page's pure helpers."""

from __future__ import annotations

import importlib.util
from decimal import Decimal
from types import ModuleType

from subway_ops.config import TARGET_FOOD_COST_PORTFOLIO


def _load_fm_page() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "fm_page_module",
        "src/subway_ops/dashboard/pages/3_field_manager.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_delta_badge_text_handles_none() -> None:
    module = _load_fm_page()
    text, in_target = module.delta_badge_text(None, TARGET_FOOD_COST_PORTFOLIO)
    assert text == "—"
    assert in_target is None


def test_delta_badge_text_negative_when_under_target() -> None:
    """An actual food cost of 18% is 2pp UNDER the 20% target — should be
    rendered as -2.0pp and the in_target flag should be True."""
    module = _load_fm_page()
    text, in_target = module.delta_badge_text(Decimal("0.18"), TARGET_FOOD_COST_PORTFOLIO)
    assert text == "-2.0pp vs target"
    assert in_target is True


def test_delta_badge_text_positive_when_over_target() -> None:
    module = _load_fm_page()
    text, in_target = module.delta_badge_text(Decimal("0.23"), TARGET_FOOD_COST_PORTFOLIO)
    assert text == "+3.0pp vs target"
    assert in_target is False


def test_delta_badge_text_exact_target_is_in_target() -> None:
    module = _load_fm_page()
    text, in_target = module.delta_badge_text(
        TARGET_FOOD_COST_PORTFOLIO, TARGET_FOOD_COST_PORTFOLIO
    )
    assert text == "0.0pp vs target"
    assert in_target is True


def test_format_pct_and_currency_helpers() -> None:
    module = _load_fm_page()
    assert module._format_pct(Decimal("0.185")) == "18.5%"
    assert module._format_pct(None) == "—"
    assert module._format_currency(Decimal("1234.56")) == "$1,235"
    assert module._format_currency(None) == "—"


def test_module_imports_clean() -> None:
    module = _load_fm_page()
    assert hasattr(module, "main")
    assert callable(module.main)
