"""Tests for the mart_store_weekly refresh.

Synthetic ControlSheet + Wisr rows are seeded into the staging tables, then
``refresh`` is invoked. We assert: the join produces a single mart row, the
percentage-fraction conversion is applied, and the GENERATED target flags
evaluate correctly against ``TARGET_FOOD_COST_STORE``.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from decimal import Decimal

import pytest

from subway_ops.config import TARGET_FOOD_COST_STORE, TARGET_LABOR_COST_STORE, settings
from subway_ops.db.connection import execute_sql
from subway_ops.db.migrate import apply_migrations
from subway_ops.transform.mart_store_weekly import refresh
from tests.conftest import ns

TEST_STORE = ns("T-4092")
WEEK_END = date(2026, 5, 5)  # a Tuesday


def test_targets_are_fractional() -> None:
    """Mart logic assumes targets are fractional, not whole-percent."""
    assert Decimal("0.22") == TARGET_FOOD_COST_STORE
    assert Decimal("0.28") == TARGET_LABOR_COST_STORE


requires_db = pytest.mark.skipif(
    not settings.database_url,
    reason="DB integration test: needs DATABASE_URL",
)


@pytest.fixture
def applied_migrations() -> None:
    apply_migrations()


def _wipe() -> None:
    params = {"store": TEST_STORE, "w": WEEK_END}
    for tbl in (
        "stg_controlsheet_weekly",
        "stg_wisr_weekly",
        "stg_wisr_inventory_items",
        "mart_store_weekly",
    ):
        execute_sql(
            f"DELETE FROM {tbl} WHERE restaurant_number = :store AND week_end_date = :w",
            params,
        )
    execute_sql(
        "DELETE FROM stg_daily_sales WHERE restaurant_number = :store "
        "AND business_date BETWEEN :w - INTERVAL '6 days' AND :w",
        params,
    )


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
    _wipe()
    yield
    _wipe()


def _seed_controlsheet(
    net_sales: Decimal,
    customer_count: int,
    hours: Decimal,
    units: int,
    cash_overshort: Decimal,
    bread_overshort: Decimal,
    deposit: Decimal,
    avg_ticket: Decimal,
    factor: Decimal,
    productivity: Decimal,
) -> None:
    execute_sql(
        """
        INSERT INTO stg_controlsheet_weekly (
            restaurant_number, week_end_date,
            net_sales, customer_count, productivity, factor,
            labor_hours_worked_total,
            unit_itemization_total_units_total,
            cash_control_over_short_total,
            bread_bread_over_short_total,
            cash_control_deposit_in_bank_total,
            metrics_average_ticket_total
        ) VALUES (
            :s, :w, :ns, :cc, :p, :f, :h, :u, :co, :bo, :d, :at
        )
        ON CONFLICT (restaurant_number, week_end_date) DO UPDATE SET
          net_sales = EXCLUDED.net_sales,
          customer_count = EXCLUDED.customer_count
        """,
        {
            "s": TEST_STORE,
            "w": WEEK_END,
            "ns": net_sales,
            "cc": customer_count,
            "p": productivity,
            "f": factor,
            "h": hours,
            "u": units,
            "co": cash_overshort,
            "bo": bread_overshort,
            "d": deposit,
            "at": avg_ticket,
        },
    )


def _seed_wisr(
    actual_pct: Decimal,
    expected_pct: Decimal,
    diff_pct: Decimal,
    acg_pct: Decimal,
    total_inventory: Decimal,
    distribution_cost: Decimal,
) -> None:
    execute_sql(
        """
        INSERT INTO stg_wisr_weekly (
            restaurant_number, week_end_date,
            ics_cost_of_goods_actual_percentage,
            ics_cost_of_goods_expected_percentage,
            ics_cost_of_goods_percentage_diff,
            acg_adjusted_cost_of_goods_percentage,
            total_inventory_value,
            dc_distribution_costs_value_used
        ) VALUES (
            :s, :w, :a, :e, :df, :acg, :ti, :dc
        )
        ON CONFLICT (restaurant_number, week_end_date) DO UPDATE SET
          ics_cost_of_goods_actual_percentage = EXCLUDED.ics_cost_of_goods_actual_percentage
        """,
        {
            "s": TEST_STORE,
            "w": WEEK_END,
            "a": actual_pct,
            "e": expected_pct,
            "df": diff_pct,
            "acg": acg_pct,
            "ti": total_inventory,
            "dc": distribution_cost,
        },
    )


def _seed_daily_sales_for_week(transactions_per_day: int) -> None:
    """Seed seven days of stg_daily_sales rows so transactions_total isn't null."""
    for offset in range(7):
        bd = WEEK_END - __import__("datetime").timedelta(days=offset)
        execute_sql(
            """
            INSERT INTO stg_daily_sales (restaurant_number, business_date,
                net_sales, tax, units, transactions,
                cash_card_total, third_party_sales, third_party_transactions,
                hours_worked)
            VALUES (:s, :d, 100, 0, 10, :t, 0, 0, 0, 5)
            ON CONFLICT (restaurant_number, business_date) DO UPDATE SET
              transactions = EXCLUDED.transactions
            """,
            {"s": TEST_STORE, "d": bd, "t": transactions_per_day},
        )


@requires_db
def test_refresh_joins_and_converts_percentages(seeded_store: None) -> None:
    _seed_controlsheet(
        net_sales=Decimal("6000"),
        customer_count=400,
        hours=Decimal("80"),
        units=520,
        cash_overshort=Decimal("3.50"),
        bread_overshort=Decimal("12.00"),
        deposit=Decimal("1500"),
        avg_ticket=Decimal("15"),
        factor=Decimal("8.9"),
        productivity=Decimal("6.5"),
    )
    # 18% food cost (well inside the 22% target) — store WHOLE percent.
    _seed_wisr(
        actual_pct=Decimal("18.00"),
        expected_pct=Decimal("22.00"),
        diff_pct=Decimal("-4.00"),
        acg_pct=Decimal("16.50"),
        total_inventory=Decimal("2025.50"),
        distribution_cost=Decimal("-55.00"),
    )
    _seed_daily_sales_for_week(transactions_per_day=50)

    rows = refresh(week_end=WEEK_END)
    # refresh rewrites every store with a stg_controlsheet_weekly row for
    # this week_end — the live backfill may have populated others, so we
    # care only that THIS store's row exists.
    assert rows >= 1

    out = execute_sql(
        """
        SELECT week_start_date, net_sales_total, transactions_total,
               units_total, hours_worked_total,
               cash_overshort_total, bread_overshort_total, deposit_in_bank_total,
               customer_count, factor, average_ticket, productivity,
               food_cost_actual_pct, food_cost_expected_pct,
               food_cost_diff_pct, adjusted_cost_of_goods_pct,
               total_inventory_value, distribution_cost_value,
               labor_cost_pct,
               is_food_cost_in_target, is_labor_cost_in_target
        FROM mart_store_weekly
        WHERE restaurant_number = :s AND week_end_date = :w
        """,
        {"s": TEST_STORE, "w": WEEK_END},
    )
    assert len(out) == 1
    (
        week_start,
        net_sales,
        txns,
        units,
        hours,
        cash_os,
        bread_os,
        deposit,
        cust,
        factor,
        at,
        prod,
        food_actual,
        food_expected,
        food_diff,
        acg_pct,
        ti,
        dc,
        labor,
        food_ok,
        labor_ok,
    ) = out[0]

    assert week_start == WEEK_END - __import__("datetime").timedelta(days=6)
    assert net_sales == Decimal("6000.0000")
    assert txns == 50 * 7
    assert units == 520
    assert hours == Decimal("80.00")
    assert cash_os == Decimal("3.5000")
    assert bread_os == Decimal("12.0000")
    assert deposit == Decimal("1500.0000")
    assert cust == 400
    assert factor == Decimal("8.9000")
    assert at == Decimal("15.0000")
    assert prod == Decimal("6.5000")

    # Whole-percent → fractional conversion:
    assert food_actual == Decimal("0.180000")
    assert food_expected == Decimal("0.220000")
    assert food_diff == Decimal("-0.040000")
    assert acg_pct == Decimal("0.165000")
    assert ti == Decimal("2025.5000")
    assert dc == Decimal("-55.0000")
    assert labor is None

    # 0.18 <= 0.22 → True; labor_cost_pct NULL → NULL flag.
    assert food_ok is True
    assert labor_ok is None


@requires_db
def test_refresh_flag_false_when_above_target(seeded_store: None) -> None:
    _seed_controlsheet(
        net_sales=Decimal("5000"),
        customer_count=300,
        hours=Decimal("60"),
        units=400,
        cash_overshort=Decimal("0"),
        bread_overshort=Decimal("0"),
        deposit=Decimal("1000"),
        avg_ticket=Decimal("16"),
        factor=Decimal("9"),
        productivity=Decimal("6"),
    )
    _seed_wisr(
        actual_pct=Decimal("28.00"),  # 0.28 > 0.22 → flag should be False
        expected_pct=Decimal("22.00"),
        diff_pct=Decimal("6.00"),
        acg_pct=Decimal("26.00"),
        total_inventory=Decimal("1800"),
        distribution_cost=Decimal("0"),
    )
    refresh(week_end=WEEK_END)

    out = execute_sql(
        "SELECT food_cost_actual_pct, is_food_cost_in_target "
        "FROM mart_store_weekly WHERE restaurant_number = :s "
        "AND week_end_date = :w",
        {"s": TEST_STORE, "w": WEEK_END},
    )
    food_actual, food_ok = out[0]
    assert food_actual == Decimal("0.280000")
    assert food_ok is False


@requires_db
def test_refresh_is_idempotent(seeded_store: None) -> None:
    _seed_controlsheet(
        net_sales=Decimal("1000"),
        customer_count=80,
        hours=Decimal("20"),
        units=100,
        cash_overshort=Decimal("0"),
        bread_overshort=Decimal("0"),
        deposit=Decimal("250"),
        avg_ticket=Decimal("12"),
        factor=Decimal("9"),
        productivity=Decimal("5"),
    )
    first = refresh(week_end=WEEK_END)
    second = refresh(week_end=WEEK_END)
    # Whatever the global row count is for the week, refresh must be
    # repeatable AND the test store's row must remain unique.
    assert first == second
    assert first >= 1

    count = execute_sql(
        "SELECT count(*) FROM mart_store_weekly "
        "WHERE restaurant_number = :s AND week_end_date = :w",
        {"s": TEST_STORE, "w": WEEK_END},
    )
    assert count[0][0] == 1
