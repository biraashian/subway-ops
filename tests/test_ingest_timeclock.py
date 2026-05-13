"""Tests for the DailyTimeclock ingest pipeline.

Unit tests: batching limits (10 stores / 30 days).

DB integration: mocked client + recorded fixture writes rows to
``stg_timeclock`` with business_date computed via the 02:00 cutoff;
re-running is a no-op.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from subway_ops.config import settings
from subway_ops.db.connection import execute_sql
from subway_ops.db.migrate import apply_migrations
from subway_ops.ingest.timeclock import (
    MAX_DAYS_PER_CALL,
    MAX_STORES_PER_CALL,
    ingest,
    plan_batches,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "recorded" / "daily_timeclock.json"
)


# ---------------------------------------------------------------------------
# Unit
# ---------------------------------------------------------------------------


def test_plan_batches_single_call() -> None:
    batches = plan_batches(["4092"], date(2026, 5, 11), date(2026, 5, 11))
    assert batches == [(["4092"], date(2026, 5, 11), date(2026, 5, 11))]


def test_plan_batches_splits_stores_at_10() -> None:
    stores = [str(i) for i in range(MAX_STORES_PER_CALL + 2)]
    batches = plan_batches(stores, date(2026, 5, 1), date(2026, 5, 1))
    assert len(batches) == 2
    assert len(batches[0][0]) == MAX_STORES_PER_CALL


def test_plan_batches_splits_dates_at_30_days() -> None:
    end = date(2026, 5, 1) + timedelta(days=39)
    batches = plan_batches(["4092"], date(2026, 5, 1), end)
    assert len(batches) == 2
    win0_days = (batches[0][2] - batches[0][1]).days + 1
    assert win0_days == MAX_DAYS_PER_CALL


# ---------------------------------------------------------------------------
# DB integration
# ---------------------------------------------------------------------------


def _fixture_has_data() -> bool:
    if not FIXTURE_PATH.exists():
        return False
    return bool(json.loads(FIXTURE_PATH.read_text(encoding="utf-8")).get("data"))


requires_db_and_fixture = pytest.mark.skipif(
    not settings.database_url or not _fixture_has_data(),
    reason="DB integration test: needs DATABASE_URL and a non-empty fixture",
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
    execute_sql("DELETE FROM stg_timeclock WHERE restaurant_number = '4092'")
    yield
    execute_sql("DELETE FROM stg_timeclock WHERE restaurant_number = '4092'")


def _mock_client(payload: dict[str, Any]) -> MagicMock:
    client = MagicMock()
    client.get_daily_timeclock.return_value = payload
    client.close.return_value = None
    return client


def _expected_rows(payload: dict[str, Any]) -> int:
    return len({
        (e["restaurantNumber"], e["clerkId"], e["clockIn"])
        for e in payload["data"]
    })


@requires_db_and_fixture
def test_ingest_writes_timeclock_rows(
    fixture_payload: dict[str, Any], seeded_store_4092: None
) -> None:
    written = ingest(
        date(2026, 5, 11),
        date(2026, 5, 11),
        ["4092"],
        client=_mock_client(fixture_payload),
    )
    expected = _expected_rows(fixture_payload)
    assert written == expected > 0

    rows = execute_sql(
        "SELECT count(*) FROM stg_timeclock WHERE restaurant_number = '4092'"
    )
    assert rows[0][0] == expected


@requires_db_and_fixture
def test_ingest_is_idempotent(
    fixture_payload: dict[str, Any], seeded_store_4092: None
) -> None:
    client = _mock_client(fixture_payload)
    first = ingest(date(2026, 5, 11), date(2026, 5, 11), ["4092"], client=client)
    second = ingest(date(2026, 5, 11), date(2026, 5, 11), ["4092"], client=client)
    assert first == second

    rows = execute_sql(
        "SELECT count(*) FROM stg_timeclock WHERE restaurant_number = '4092'"
    )
    assert rows[0][0] == _expected_rows(fixture_payload)
