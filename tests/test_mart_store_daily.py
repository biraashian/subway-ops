"""Tests for the mart_store_daily refresh.

Synthetic rows are seeded across every source table; refresh is run; the
mart row is verified including the GENERATED rate columns.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from subway_ops.config import settings
from subway_ops.db.connection import execute_sql
from subway_ops.db.migrate import apply_migrations
from subway_ops.transform.mart_store_daily import (
    DEFAULT_LOOKBACK_DAYS,
    INVENTORY_METRIC,
    refresh,
)
from tests.conftest import ns

TEST_STORE = ns("T-4092")
TEST_DATE = date(2026, 5, 11)
TEST_WINDOW_END = TEST_DATE  # explicit end for tests so default lookback can't drift


requires_db = pytest.mark.skipif(
    not settings.database_url,
    reason="DB integration test: needs DATABASE_URL",
)


@pytest.fixture
def applied_migrations() -> None:
    apply_migrations()


def _wipe() -> None:
    """Remove anything left over from prior runs for our test (store, date)."""
    params = {"store": TEST_STORE, "d": TEST_DATE}
    execute_sql(
        "DELETE FROM stg_daily_sales WHERE restaurant_number = :store AND business_date = :d",
        params,
    )
    execute_sql(
        "DELETE FROM stg_3p_daily WHERE restaurant_number = :store AND business_date = :d",
        params,
    )
    execute_sql(
        "DELETE FROM stg_inventory_movement_totals "
        "WHERE restaurant_number = :store AND business_date = :d",
        params,
    )
    execute_sql(
        "DELETE FROM stg_no_sales WHERE restaurant_number = :store AND business_date = :d",
        params,
    )
    execute_sql(
        "DELETE FROM mart_store_daily WHERE restaurant_number = :store AND business_date = :d",
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


def _seed_daily_sales(net_sales: Decimal, txns: int, hours: Decimal) -> None:
    execute_sql(
        """
        INSERT INTO stg_daily_sales (restaurant_number, business_date,
            net_sales, tax, units, transactions,
            cash_card_total, third_party_sales, third_party_transactions,
            hours_worked)
        VALUES (:s, :d, :ns, 0, :u, :t, 0, 0, 0, :h)
        ON CONFLICT (restaurant_number, business_date) DO UPDATE SET
          net_sales = EXCLUDED.net_sales, transactions = EXCLUDED.transactions,
          hours_worked = EXCLUDED.hours_worked, units = EXCLUDED.units
        """,
        {"s": TEST_STORE, "d": TEST_DATE, "ns": net_sales, "u": 50, "t": txns, "h": hours},
    )


def _seed_third_party(net: Decimal, txns: int) -> None:
    execute_sql(
        """
        INSERT INTO stg_3p_daily (restaurant_number, business_date,
            total_sales, total_net_sales, total_transactions)
        VALUES (:s, :d, 0, :n, :t)
        ON CONFLICT (restaurant_number, business_date) DO UPDATE SET
          total_net_sales = EXCLUDED.total_net_sales,
          total_transactions = EXCLUDED.total_transactions
        """,
        {"s": TEST_STORE, "d": TEST_DATE, "n": net, "t": txns},
    )


def _seed_inventory_totals(cost: Decimal, waste: Decimal) -> None:
    execute_sql(
        """
        INSERT INTO stg_inventory_movement_totals (restaurant_number, business_date,
            metric_name, total_cost, waste_value)
        VALUES (:s, :d, :m, :c, :w)
        ON CONFLICT (restaurant_number, business_date, metric_name) DO UPDATE SET
          total_cost = EXCLUDED.total_cost, waste_value = EXCLUDED.waste_value
        """,
        {"s": TEST_STORE, "d": TEST_DATE, "m": INVENTORY_METRIC, "c": cost, "w": waste},
    )


def _seed_cash_drops(n: int) -> None:
    base = datetime(2026, 5, 11, 12, 0, 0)
    for i in range(n):
        execute_sql(
            """
            INSERT INTO stg_no_sales (restaurant_number, event_time, business_date,
                clerk_id, clerk_name, no_sale_type, reason_type, reason)
            VALUES (:s, :t, :d, '95', 'Tester', 'cash drop', '', '')
            ON CONFLICT (restaurant_number, event_time, clerk_id, no_sale_type)
            DO NOTHING
            """,
            {"s": TEST_STORE, "t": base + timedelta(minutes=i), "d": TEST_DATE},
        )


@requires_db
def test_refresh_writes_mart_row_with_generated_columns(
    seeded_store: None,
) -> None:
    _seed_daily_sales(net_sales=Decimal("1000.00"), txns=50, hours=Decimal("20.00"))
    _seed_third_party(net=Decimal("200.00"), txns=10)
    _seed_inventory_totals(cost=Decimal("250.00"), waste=Decimal("12.50"))
    _seed_cash_drops(3)

    rows = refresh(start=TEST_DATE, end=TEST_WINDOW_END)
    assert rows >= 1

    out = execute_sql(
        """
        SELECT net_sales, transactions, hours_worked,
               sales_per_labor_hour, average_ticket,
               third_party_sales, third_party_pct,
               daily_inventory_cost, food_cost_pct,
               cash_drop_count
        FROM mart_store_daily
        WHERE restaurant_number = :s AND business_date = :d
        """,
        {"s": TEST_STORE, "d": TEST_DATE},
    )
    assert len(out) == 1
    (
        net_sales,
        txns,
        hours,
        sales_per_labor,
        avg_ticket,
        tp_sales,
        tp_pct,
        inv_cost,
        food_pct,
        drops,
    ) = out[0]
    assert net_sales == Decimal("1000.0000")
    assert txns == 50
    assert hours == Decimal("20.00")
    assert sales_per_labor == Decimal("50.0000")  # 1000 / 20
    assert avg_ticket == Decimal("20.0000")  # 1000 / 50
    assert tp_sales == Decimal("200.0000")
    assert tp_pct == Decimal("0.2000")  # 200 / 1000
    assert inv_cost == Decimal("250.0000")
    assert food_pct == Decimal("0.2500")  # 250 / 1000
    assert drops == 3


@requires_db
def test_refresh_is_idempotent(seeded_store: None) -> None:
    _seed_daily_sales(net_sales=Decimal("500.00"), txns=20, hours=Decimal("10.00"))
    first = refresh(start=TEST_DATE, end=TEST_WINDOW_END)
    second = refresh(start=TEST_DATE, end=TEST_WINDOW_END)
    assert first >= 1 and second >= 1

    count = execute_sql(
        "SELECT count(*) FROM mart_store_daily WHERE restaurant_number = :s AND business_date = :d",
        {"s": TEST_STORE, "d": TEST_DATE},
    )
    assert count[0][0] == 1


@requires_db
def test_refresh_handles_zero_denominators(seeded_store: None) -> None:
    """Stores with zero hours or zero net_sales must not divide by zero."""
    _seed_daily_sales(net_sales=Decimal("0"), txns=0, hours=Decimal("0"))
    _seed_inventory_totals(cost=Decimal("0"), waste=Decimal("0"))
    refresh(start=TEST_DATE, end=TEST_WINDOW_END)

    out = execute_sql(
        """
        SELECT sales_per_labor_hour, average_ticket, third_party_pct, food_cost_pct
        FROM mart_store_daily
        WHERE restaurant_number = :s AND business_date = :d
        """,
        {"s": TEST_STORE, "d": TEST_DATE},
    )
    assert len(out) == 1
    assert all(v is None for v in out[0])


def test_default_lookback_window() -> None:
    """When called with no args, refresh defaults to the last 14 days ending today."""
    assert DEFAULT_LOOKBACK_DAYS == 14
