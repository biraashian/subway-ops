"""Tests for the Wisr weekly ingest.

Unit tests: DDL generator is self-consistent, on-disk migration matches
generator output, ``flatten_weekly`` populates every expected column
against the recorded fixture.

DB integration: mocked client + recorded fixture lands one weekly row and
one row per inventory item; re-running is a no-op.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from subway_ops.config import settings
from subway_ops.db.connection import execute_sql
from subway_ops.db.migrate import apply_migrations
from subway_ops.freshconnect.models import WisrResponse
from subway_ops.ingest.wisr import (
    column_definitions,
    flatten_weekly,
    generate_ddl,
    ingest,
)

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "recorded" / "wisr.json"
MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "subway_ops"
    / "db"
    / "migrations"
    / "007_wisr.sql"
)


# ---------------------------------------------------------------------------
# DB-free
# ---------------------------------------------------------------------------


def test_generate_ddl_includes_every_column() -> None:
    ddl = generate_ddl()
    for name, _typ in column_definitions():
        assert re.search(rf"\b{name}\b", ddl), f"missing column in DDL: {name}"


def test_committed_migration_matches_generator() -> None:
    assert MIGRATION_PATH.read_text(encoding="utf-8").strip() == generate_ddl().strip()


@pytest.mark.skipif(not FIXTURE_PATH.exists(), reason="No recorded wisr fixture")
def test_flatten_weekly_populates_every_column() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    parsed = WisrResponse.model_validate(payload)
    row = parsed.data[0]
    flat = flatten_weekly(row, date(2026, 5, 5))

    expected = {name for name, _typ in column_definitions()}
    expected.add("restaurant_number")
    expected.add("week_end_date")
    assert set(flat.keys()) == expected

    assert flat["restaurant_number"] == row.restaurant_number
    assert flat["week_end_date"] == date(2026, 5, 5)


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
    execute_sql("DELETE FROM stg_wisr_weekly WHERE restaurant_number = '4092'")
    execute_sql("DELETE FROM stg_wisr_inventory_items WHERE restaurant_number = '4092'")
    yield
    execute_sql("DELETE FROM stg_wisr_weekly WHERE restaurant_number = '4092'")
    execute_sql("DELETE FROM stg_wisr_inventory_items WHERE restaurant_number = '4092'")


def _mock_client(payload: dict[str, Any]) -> MagicMock:
    client = MagicMock()
    client.get_wisr.return_value = payload
    client.close.return_value = None
    return client


@requires_db_and_fixture
def test_ingest_writes_weekly_and_items(
    fixture_payload: dict[str, Any], seeded_store_4092: None
) -> None:
    written = ingest(date(2026, 5, 5), ["4092"], client=_mock_client(fixture_payload))
    expected_items = len(
        {
            (row["restaurantNumber"], item["name"])
            for row in fixture_payload["data"]
            for item in row["inventoryItems"]
        }
    )
    assert written == len(fixture_payload["data"]) + expected_items

    weekly = execute_sql("SELECT count(*) FROM stg_wisr_weekly WHERE restaurant_number = '4092'")
    items = execute_sql(
        "SELECT count(*) FROM stg_wisr_inventory_items WHERE restaurant_number = '4092'"
    )
    assert weekly[0][0] == 1
    assert items[0][0] == expected_items > 0


@requires_db_and_fixture
def test_ingest_is_idempotent(fixture_payload: dict[str, Any], seeded_store_4092: None) -> None:
    client = _mock_client(fixture_payload)
    first = ingest(date(2026, 5, 5), ["4092"], client=client)
    second = ingest(date(2026, 5, 5), ["4092"], client=client)
    assert first == second

    weekly = execute_sql("SELECT count(*) FROM stg_wisr_weekly WHERE restaurant_number = '4092'")
    assert weekly[0][0] == 1
