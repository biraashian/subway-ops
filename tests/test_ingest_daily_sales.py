"""Tests for the DailySalesSummary ingest pipeline.

Unit tests (always run):
- ``plan_batches`` respects the documented 20-store / 50-day caps.

DB integration tests (run only when DATABASE_URL is set and the recorded
fixture exists at ``tests/fixtures/recorded/daily_sales_summary.json``):
- A mocked FreshConnect client serves the fixture payload; ingest writes
  rows to ``stg_daily_sales`` keyed on (restaurant_number, business_date).
- Re-running for the same window upserts (no duplicate rows).
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
from subway_ops.ingest.daily_sales import (
    MAX_DAYS_PER_CALL,
    MAX_STORES_PER_CALL,
    ingest,
    plan_batches,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "recorded" / "daily_sales_summary.json"
)


# ---------------------------------------------------------------------------
# Batching (DB-free)
# ---------------------------------------------------------------------------


def test_plan_batches_single_call_under_limits() -> None:
    batches = plan_batches(["4092"], date(2026, 5, 11), date(2026, 5, 11))
    assert batches == [(["4092"], date(2026, 5, 11), date(2026, 5, 11))]


def test_plan_batches_splits_stores_at_20() -> None:
    stores = [str(i) for i in range(MAX_STORES_PER_CALL + 5)]
    batches = plan_batches(stores, date(2026, 5, 1), date(2026, 5, 1))
    assert len(batches) == 2
    assert len(batches[0][0]) == MAX_STORES_PER_CALL
    assert len(batches[1][0]) == 5


def test_plan_batches_splits_dates_at_50_days() -> None:
    # 60 days inclusive (start..start+59); 60 > 50, so we expect two windows.
    end = date(2026, 5, 1) + timedelta(days=59)
    batches = plan_batches(["4092"], date(2026, 5, 1), end)
    assert len(batches) == 2
    win0_days = (batches[0][2] - batches[0][1]).days + 1
    assert win0_days == MAX_DAYS_PER_CALL
    # Second window picks up the day after the first ends.
    assert batches[1][1] == batches[0][2] + timedelta(days=1)


def test_plan_batches_rejects_inverted_range() -> None:
    with pytest.raises(ValueError, match="precedes"):
        plan_batches(["4092"], date(2026, 5, 5), date(2026, 5, 1))


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
    """Ensure ref_stores contains the test store so the FK on stg passes."""
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
    yield
    # Tidy stg row but leave ref rows so re-runs are cheap.
    execute_sql(
        "DELETE FROM stg_daily_sales WHERE restaurant_number = '4092' AND business_date = :d",
        {"d": date(2026, 5, 11)},
    )


def _mock_client(payload: dict[str, Any]) -> MagicMock:
    client = MagicMock()
    client.get_daily_sales_summary.return_value = payload
    client.close.return_value = None
    return client


@requires_db_and_fixture
def test_ingest_writes_stg_rows(fixture_payload: dict[str, Any], seeded_store_4092: None) -> None:
    client = _mock_client(fixture_payload)
    written = ingest(date(2026, 5, 11), date(2026, 5, 11), ["4092"], client=client)
    assert written == len(fixture_payload["data"]) > 0

    rows = execute_sql(
        "SELECT net_sales, units FROM stg_daily_sales "
        "WHERE restaurant_number = '4092' AND business_date = :d",
        {"d": date(2026, 5, 11)},
    )
    assert len(rows) == 1
    net_sales, units = rows[0]
    assert net_sales > 0
    assert units > 0


@requires_db_and_fixture
def test_ingest_is_idempotent(fixture_payload: dict[str, Any], seeded_store_4092: None) -> None:
    client = _mock_client(fixture_payload)
    first = ingest(date(2026, 5, 11), date(2026, 5, 11), ["4092"], client=client)
    second = ingest(date(2026, 5, 11), date(2026, 5, 11), ["4092"], client=client)
    assert first == second  # same window writes same row count

    rows = execute_sql(
        "SELECT count(*) FROM stg_daily_sales "
        "WHERE restaurant_number = '4092' AND business_date = :d",
        {"d": date(2026, 5, 11)},
    )
    assert rows[0][0] == 1  # one PK-keyed row, even after two ingests


@requires_db_and_fixture
def test_ingest_logs_to_ops_job_runs(
    fixture_payload: dict[str, Any],
    seeded_store_4092: None,
) -> None:
    client = _mock_client(fixture_payload)
    ingest(date(2026, 5, 11), date(2026, 5, 11), ["4092"], client=client)

    rows = execute_sql(
        "SELECT status, rows_written FROM ops_job_runs "
        "WHERE job_name = 'ingest_daily_sales' "
        "ORDER BY id DESC LIMIT 1"
    )
    assert rows
    status, rows_written = rows[0]
    assert status == "success"
    assert rows_written == len(fixture_payload["data"])
