"""Tests for the field-manager portfolio rollup.

Synthetic field manager + stores + mart_store_weekly rows. We assert:
- Sales-weighted averages are computed correctly (a $1.5M store moves the
  metric more than a $0.5M store).
- ``store_count_in_target_food`` mirrors the upstream BOOLEAN flags.
- The GENERATED portfolio-target flags evaluate against 20% / 25%.
- Re-running the refresh leaves a single FM row per week.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from decimal import Decimal

import pytest

from subway_ops.config import (
    TARGET_FOOD_COST_PORTFOLIO,
    TARGET_FOOD_COST_STORE,
    TARGET_LABOR_COST_PORTFOLIO,
    TARGET_LABOR_COST_STORE,
    settings,
)
from subway_ops.db.connection import execute_sql
from subway_ops.db.migrate import apply_migrations
from subway_ops.transform.mart_field_manager_portfolio import refresh

FM_NAME = "TestPortfolioFM"
WEEK_END = date(2026, 5, 5)


def test_portfolio_targets_are_fractional_and_tighter() -> None:
    assert Decimal("0.20") == TARGET_FOOD_COST_PORTFOLIO
    assert Decimal("0.25") == TARGET_LABOR_COST_PORTFOLIO
    # Portfolio is supposed to be tighter than per-store.
    assert TARGET_FOOD_COST_PORTFOLIO < TARGET_FOOD_COST_STORE
    assert TARGET_LABOR_COST_PORTFOLIO < TARGET_LABOR_COST_STORE


requires_db = pytest.mark.skipif(
    not settings.database_url,
    reason="DB integration test: needs DATABASE_URL",
)


@pytest.fixture
def applied_migrations() -> None:
    apply_migrations()


def _wipe() -> None:
    execute_sql(
        "DELETE FROM mart_field_manager_portfolio WHERE field_manager_name = :fm",
        {"fm": FM_NAME},
    )
    execute_sql(
        "DELETE FROM mart_store_weekly WHERE restaurant_number IN ('T1','T2','T3')",
    )
    execute_sql("DELETE FROM ref_stores WHERE store_number IN ('T1','T2','T3')")
    execute_sql(
        # D-046 — see tests/test_mart_recon_weekly.py.
        """
        DELETE FROM ref_field_managers
         WHERE name = :fm
           AND NOT EXISTS (
               SELECT 1 FROM ref_stores WHERE field_manager_name = :fm
           )
        """,
        {"fm": FM_NAME},
    )


@pytest.fixture
def seeded_fm_and_stores(applied_migrations: None) -> Iterator[None]:
    _wipe()
    execute_sql(
        """
        INSERT INTO ref_field_managers (name, email, is_active)
        VALUES (:fm, 'portfoliofm@example.com', true)
        ON CONFLICT (name) DO NOTHING
        """,
        {"fm": FM_NAME},
    )
    for sn in ("T1", "T2", "T3"):
        execute_sql(
            """
            INSERT INTO ref_stores
              (store_number, store_name, city, state, timezone,
               field_manager_name, is_active)
            VALUES (:sn, :name, 'Seattle', 'WA', 'America/Los_Angeles', :fm, true)
            ON CONFLICT (store_number) DO UPDATE SET
              field_manager_name = EXCLUDED.field_manager_name
            """,
            {"sn": sn, "name": f"Test Store {sn}", "fm": FM_NAME},
        )
    yield
    _wipe()


def _seed_weekly_row(store: str, net_sales: Decimal, food_pct: Decimal | None) -> None:
    execute_sql(
        """
        INSERT INTO mart_store_weekly (
            restaurant_number, week_end_date,
            net_sales_total, food_cost_actual_pct
        ) VALUES (:s, :w, :ns, :fp)
        ON CONFLICT (restaurant_number, week_end_date) DO UPDATE SET
          net_sales_total      = EXCLUDED.net_sales_total,
          food_cost_actual_pct = EXCLUDED.food_cost_actual_pct
        """,
        {"s": store, "w": WEEK_END, "ns": net_sales, "fp": food_pct},
    )


@requires_db
def test_sales_weighted_average_is_skewed_by_higher_sales_store(
    seeded_fm_and_stores: None,
) -> None:
    # T1: $10k @ 18%, T2: $1k @ 30% — high-volume store should dominate.
    _seed_weekly_row("T1", Decimal("10000"), Decimal("0.18"))
    _seed_weekly_row("T2", Decimal("1000"), Decimal("0.30"))
    _seed_weekly_row("T3", Decimal("5000"), Decimal("0.20"))

    refresh(week_end=WEEK_END)

    rows = execute_sql(
        """
        SELECT store_count, total_net_sales_weighted,
               round(portfolio_food_cost_pct, 6),
               is_food_cost_in_portfolio_target
        FROM mart_field_manager_portfolio
        WHERE field_manager_name = :fm AND week_end_date = :w
        """,
        {"fm": FM_NAME, "w": WEEK_END},
    )
    assert len(rows) == 1
    store_count, total_sales, weighted_pct, food_flag = rows[0]

    assert store_count == 3
    assert total_sales == Decimal("16000.0000")

    # Hand-computed: (0.18*10000 + 0.30*1000 + 0.20*5000) / 16000
    # = (1800 + 300 + 1000) / 16000 = 3100 / 16000 = 0.19375
    assert weighted_pct == Decimal("0.193750")
    # 0.19375 <= 0.20 portfolio target → True.
    assert food_flag is True


@requires_db
def test_null_food_pct_does_not_drag_average_to_zero(
    seeded_fm_and_stores: None,
) -> None:
    """Stores without a food_cost figure must be excluded from both
    numerator AND denominator — not silently treated as 0%."""
    _seed_weekly_row("T1", Decimal("10000"), Decimal("0.22"))
    _seed_weekly_row("T2", Decimal("10000"), None)
    _seed_weekly_row("T3", Decimal("10000"), Decimal("0.22"))

    refresh(week_end=WEEK_END)

    rows = execute_sql(
        "SELECT round(portfolio_food_cost_pct, 6) "
        "FROM mart_field_manager_portfolio "
        "WHERE field_manager_name = :fm AND week_end_date = :w",
        {"fm": FM_NAME, "w": WEEK_END},
    )
    # Without the NULL guard the weighted average would land at 0.14666...
    # ((0.22 * 20000) / 30000). With the guard it should be 0.22 flat.
    assert rows[0][0] == Decimal("0.220000")


@requires_db
def test_store_counts_in_target_track_upstream_flags(
    seeded_fm_and_stores: None,
) -> None:
    # T1, T3 pass the 22% per-store food target; T2 fails it.
    _seed_weekly_row("T1", Decimal("5000"), Decimal("0.21"))
    _seed_weekly_row("T2", Decimal("5000"), Decimal("0.25"))
    _seed_weekly_row("T3", Decimal("5000"), Decimal("0.18"))

    refresh(week_end=WEEK_END)

    rows = execute_sql(
        "SELECT store_count, store_count_in_target_food "
        "FROM mart_field_manager_portfolio "
        "WHERE field_manager_name = :fm AND week_end_date = :w",
        {"fm": FM_NAME, "w": WEEK_END},
    )
    assert rows[0] == (3, 2)


@requires_db
def test_refresh_is_idempotent(seeded_fm_and_stores: None) -> None:
    _seed_weekly_row("T1", Decimal("5000"), Decimal("0.20"))
    first = refresh(week_end=WEEK_END)
    second = refresh(week_end=WEEK_END)
    # refresh rewrites every FM with a row for this week — other live
    # FMs may exist alongside our synthetic one. We only care that the
    # call is repeatable AND that our test FM lands exactly one row.
    assert first == second
    assert first >= 1

    rows = execute_sql(
        "SELECT count(*) FROM mart_field_manager_portfolio "
        "WHERE field_manager_name = :fm AND week_end_date = :w",
        {"fm": FM_NAME, "w": WEEK_END},
    )
    assert rows[0][0] == 1
