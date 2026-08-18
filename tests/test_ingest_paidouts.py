"""Tests for the PaidOutsAndNoSales ingest pipeline.

Unit tests (always run):
- ``_business_date`` applies the 02:00 cutoff in store-local time.
- ``plan_batches`` respects the documented 20-store / 31-day caps.

DB integration tests (run only when DATABASE_URL is set and the recorded
fixture exists):
- Mocked client + recorded fixture lands no_sales / paid_outs rows;
  stg_cash_drops view filters by no_sale_type='cash drop'.
- Re-running for the same window upserts (no duplicate rows).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from subway_ops.config import settings
from subway_ops.db.connection import execute_sql
from subway_ops.db.migrate import apply_migrations
from subway_ops.ingest.paidouts import (
    MAX_DAYS_PER_CALL,
    MAX_STORES_PER_CALL,
    _business_date,
    ingest,
    plan_batches,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "recorded" / "paid_outs_and_no_sales.json"
)


# ---------------------------------------------------------------------------
# Unit tests (DB-free)
# ---------------------------------------------------------------------------


def test_business_date_pre_cutoff_rolls_back() -> None:
    # 01:30 LA = before the 02:00 cutoff, so it still belongs to the prior date.
    naive = datetime(2026, 5, 12, 1, 30)
    assert _business_date(naive) == date(2026, 5, 11)


def test_business_date_post_cutoff_uses_today() -> None:
    naive = datetime(2026, 5, 12, 8, 57, 5, 567000)
    assert _business_date(naive) == date(2026, 5, 12)


def test_plan_batches_single_call() -> None:
    batches = plan_batches(["4092"], date(2026, 5, 11), date(2026, 5, 11))
    assert batches == [(["4092"], date(2026, 5, 11), date(2026, 5, 11))]


def test_plan_batches_splits_at_31_days() -> None:
    # 40 days inclusive: 40 > 31, so we expect two date windows.
    end = date(2026, 5, 1) + timedelta(days=39)
    batches = plan_batches(["4092"], date(2026, 5, 1), end)
    assert len(batches) == 2
    win0_days = (batches[0][2] - batches[0][1]).days + 1
    assert win0_days == MAX_DAYS_PER_CALL
    assert batches[1][1] == batches[0][2] + timedelta(days=1)


def test_plan_batches_splits_stores_at_20() -> None:
    stores = [str(i) for i in range(MAX_STORES_PER_CALL + 3)]
    batches = plan_batches(stores, date(2026, 5, 1), date(2026, 5, 1))
    assert len(batches) == 2
    assert len(batches[0][0]) == MAX_STORES_PER_CALL
    assert len(batches[1][0]) == 3


# ---------------------------------------------------------------------------
# DB integration
# ---------------------------------------------------------------------------


requires_db_and_fixture = pytest.mark.skipif(
    not settings.database_url or not FIXTURE_PATH.exists(),
    reason="DB integration test: needs DATABASE_URL and a recorded fixture",
)


@pytest.fixture
def fixture_payload() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def applied_migrations() -> None:
    apply_migrations()


@pytest.fixture
def seeded_store_4092(applied_migrations: None) -> Iterator[None]:
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
        VALUES ('4092', 'Test Store 4092', 'Seattle', 'WA',
                'America/Los_Angeles', 'TestFM', true)
        ON CONFLICT (store_number) DO NOTHING
        """
    )
    # Start each test from a clean slate for store 4092 so prior live
    # backfills don't bleed into row-count assertions.
    execute_sql("DELETE FROM stg_no_sales WHERE restaurant_number = '4092'")
    execute_sql("DELETE FROM stg_paid_outs WHERE restaurant_number = '4092'")
    yield
    execute_sql("DELETE FROM stg_no_sales WHERE restaurant_number = '4092'")
    execute_sql("DELETE FROM stg_paid_outs WHERE restaurant_number = '4092'")


def _mock_client(payload: dict[str, Any]) -> MagicMock:
    client = MagicMock()
    client.get_paidouts_and_no_sales.return_value = payload
    client.close.return_value = None
    return client


def _expected_no_sales_rows(payload: dict[str, Any]) -> int:
    return len(
        {
            (e["restaurantNumber"], e["time"], e["clerkId"], e["noSaleType"])
            for e in payload["data"]["noSales"]
        }
    )


@requires_db_and_fixture
def test_ingest_writes_no_sales_rows(
    fixture_payload: dict[str, Any], seeded_store_4092: None
) -> None:
    written = ingest(
        date(2026, 5, 11),
        date(2026, 5, 11),
        ["4092"],
        client=_mock_client(fixture_payload),
    )
    expected_no_sales = _expected_no_sales_rows(fixture_payload)
    expected_paid_outs = len(fixture_payload["data"]["paidOuts"])
    assert written == expected_no_sales + expected_paid_outs > 0

    rows = execute_sql("SELECT count(*) FROM stg_no_sales WHERE restaurant_number = '4092'")
    assert rows[0][0] == expected_no_sales


@requires_db_and_fixture
def test_cash_drops_view_filters_by_subtype(
    fixture_payload: dict[str, Any], seeded_store_4092: None
) -> None:
    ingest(
        date(2026, 5, 11),
        date(2026, 5, 11),
        ["4092"],
        client=_mock_client(fixture_payload),
    )
    expected_drops = sum(
        1 for e in fixture_payload["data"]["noSales"] if e["noSaleType"] == "cash drop"
    )
    rows = execute_sql("SELECT count(*) FROM stg_cash_drops WHERE restaurant_number = '4092'")
    assert rows[0][0] == expected_drops


@requires_db_and_fixture
def test_ingest_is_idempotent(fixture_payload: dict[str, Any], seeded_store_4092: None) -> None:
    client = _mock_client(fixture_payload)
    first = ingest(date(2026, 5, 11), date(2026, 5, 11), ["4092"], client=client)
    second = ingest(date(2026, 5, 11), date(2026, 5, 11), ["4092"], client=client)
    assert first == second

    rows = execute_sql("SELECT count(*) FROM stg_no_sales WHERE restaurant_number = '4092'")
    assert rows[0][0] == _expected_no_sales_rows(fixture_payload)
