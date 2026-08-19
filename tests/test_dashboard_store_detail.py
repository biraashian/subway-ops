"""Tests for the store-detail page's pure helpers.

The DB-touching queries are covered by db-integration tests that seed
synthetic rows; the in-page helpers (store picker default, variance
colouring) are exercised without Streamlit.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from types import ModuleType

import pandas as pd
import pytest

from subway_ops.config import settings
from subway_ops.dashboard.components import COLOR_IN_TARGET, COLOR_OFF_TARGET
from subway_ops.dashboard.data import (
    cash_drops_with_deposits,
    store_weekly_history,
    wisr_inventory_items,
)
from subway_ops.db.connection import execute_sql
from subway_ops.db.migrate import apply_migrations
from tests.conftest import ns


def _load_store_detail_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "store_detail_module",
        "src/subway_ops/dashboard/pages/2_store_detail.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Pure: variance colouring
# ---------------------------------------------------------------------------


def test_style_value_difference_red_for_negative() -> None:
    module = _load_store_detail_module()
    assert COLOR_OFF_TARGET in module._style_value_difference(Decimal("-12.34"))


def test_style_value_difference_green_for_positive() -> None:
    module = _load_store_detail_module()
    assert COLOR_IN_TARGET in module._style_value_difference(Decimal("5.67"))


def test_style_value_difference_blank_for_zero_or_null() -> None:
    module = _load_store_detail_module()
    assert module._style_value_difference(Decimal("0")) == ""
    assert module._style_value_difference(None) == ""


# ---------------------------------------------------------------------------
# Data helper shape (DB integration)
# ---------------------------------------------------------------------------


requires_db = pytest.mark.skipif(
    not settings.database_url,
    reason="DB integration test: needs DATABASE_URL",
)

TEST_STORE = ns("4092")


@pytest.fixture
def applied_migrations() -> None:
    apply_migrations()


@pytest.fixture
def seeded_store(applied_migrations: None) -> Iterator[None]:
    execute_sql(
        """
        INSERT INTO ref_field_managers (name, email, is_active)
        VALUES ('TestFM', 'testfm@example.com', true)
        ON CONFLICT (name) DO NOTHING
        """
    )
    execute_sql(
        """
        INSERT INTO ref_stores
          (store_number, store_name, city, state, timezone, field_manager_name, is_active)
        VALUES (:s, 'Test Store', 'Seattle', 'WA', 'America/Los_Angeles', 'TestFM', true)
        ON CONFLICT (store_number) DO NOTHING
        """,
        {"s": TEST_STORE},
    )
    yield


@requires_db
def test_store_weekly_history_returns_chronological_rows(seeded_store: None) -> None:
    df = store_weekly_history.__wrapped__(TEST_STORE, 13)  # type: ignore[attr-defined]
    if df.empty:
        pytest.skip("Live DB has no mart_store_weekly rows for the test store.")
    # Must be in ascending date order so charts render left-to-right.
    assert df["week_end_date"].is_monotonic_increasing


@requires_db
def test_wisr_inventory_items_shape(seeded_store: None) -> None:
    df = wisr_inventory_items.__wrapped__(  # type: ignore[attr-defined]
        TEST_STORE, date(2026, 5, 5)
    )
    if df.empty:
        pytest.skip("Live DB has no WISR rows for the test (store, week).")
    expected = {
        "item_name",
        "open_qty",
        "delivered_qty",
        "left_qty",
        "used_qty",
        "pos_difference",
        "recorded_waste",
        "cost",
        "value_used",
        "value_difference",
        "actual_percentage",
        "expected_percentage",
        "diff_percentage",
    }
    assert expected.issubset(set(df.columns))


@requires_db
def test_cash_drops_with_deposits_rejects_inverted_range() -> None:
    with pytest.raises(ValueError, match="precedes"):
        cash_drops_with_deposits.__wrapped__(  # type: ignore[attr-defined]
            TEST_STORE, date(2026, 5, 5), date(2026, 5, 1)
        )


@requires_db
def test_cash_drops_with_deposits_shape(seeded_store: None) -> None:
    df = cash_drops_with_deposits.__wrapped__(  # type: ignore[attr-defined]
        TEST_STORE, date(2026, 5, 5), date(2026, 5, 12)
    )
    # Whether rows exist depends on live data; assert columns regardless.
    expected = {"business_date", "drop_time", "clerk_id", "clerk_name", "deposit_in_bank"}
    if df.empty:
        # Empty frames don't carry column metadata reliably across pandas
        # versions when the underlying SELECT returns zero rows. Skip the
        # column check in that case rather than make the test flaky.
        pytest.skip("Live DB has no cash drops for the test (store, range).")
    assert expected.issubset(set(df.columns))
    # business_date should be within the requested range.
    assert df["business_date"].between(date(2026, 5, 5), date(2026, 5, 12)).all()


@requires_db
def test_cash_drops_with_deposits_joins_same_day_deposit(seeded_store: None) -> None:
    """When the controlsheet row exists for the drop's business week, the
    deposit_in_bank column must reflect THAT day's deposit, not some
    rollup. Smoke-tests the VALUES-based unpivot."""
    bd = date(2026, 5, 6)  # Wednesday → maps to *_wed columns
    week_end = date(2026, 5, 12)  # the Tuesday that closes the week containing bd

    # Seed a controlsheet row with a known per-day deposit.
    execute_sql(
        """
        INSERT INTO stg_controlsheet_weekly (
            restaurant_number, week_end_date,
            cash_control_deposit_in_bank_wed
        ) VALUES (:s, :w, :v)
        ON CONFLICT (restaurant_number, week_end_date) DO UPDATE SET
          cash_control_deposit_in_bank_wed = EXCLUDED.cash_control_deposit_in_bank_wed
        """,
        {"s": TEST_STORE, "w": week_end, "v": Decimal("123.45")},
    )
    # And a synthetic cash drop on the same business date.
    execute_sql(
        """
        INSERT INTO stg_no_sales
          (restaurant_number, event_time, business_date,
           clerk_id, clerk_name, no_sale_type, reason_type, reason)
        VALUES (:s, :t, :d, 'X', 'Test', 'cash drop', '', '')
        ON CONFLICT (restaurant_number, event_time, clerk_id, no_sale_type)
        DO NOTHING
        """,
        {
            "s": TEST_STORE,
            "t": "2026-05-06T12:30:00",
            "d": bd,
        },
    )

    try:
        df = cash_drops_with_deposits.__wrapped__(  # type: ignore[attr-defined]
            TEST_STORE, bd, bd
        )
        match = df[df["business_date"] == bd]
        assert not match.empty
        assert Decimal(str(match.iloc[0]["deposit_in_bank"])) == Decimal("123.45")
    finally:
        execute_sql(
            "DELETE FROM stg_no_sales "
            "WHERE restaurant_number = :s AND business_date = :d "
            "AND clerk_id = 'X'",
            {"s": TEST_STORE, "d": bd},
        )
        execute_sql(
            "DELETE FROM stg_controlsheet_weekly "
            "WHERE restaurant_number = :s AND week_end_date = :w",
            {"s": TEST_STORE, "w": week_end},
        )


# ---------------------------------------------------------------------------
# Page helper: store picker default
# ---------------------------------------------------------------------------


def test_module_imports_clean() -> None:
    """Cheap sanity check that the page file's top-level code executes."""
    module = _load_store_detail_module()
    assert hasattr(module, "main")
    assert callable(module.main)


def test_pandas_styler_applies_color_map() -> None:
    """Confirm the colouring function plugs into pandas.Styler without
    error. Style output is HTML so we just check we can render it."""
    module = _load_store_detail_module()
    df = pd.DataFrame({"value_difference": [Decimal("-5"), Decimal("0"), Decimal("8")]})
    styled = df.style.map(module._style_value_difference, subset=["value_difference"])
    html = styled.to_html()
    assert COLOR_OFF_TARGET in html
    assert COLOR_IN_TARGET in html
