"""Tests for the ControlSheet weekly ingest.

Unit tests (always run):
- ``flatten_row`` against the recorded fixture (DB-free).
- Generated DDL matches the column list the flatten function emits.

DB integration tests (run only when DATABASE_URL is set and the recorded
fixture exists):
- Full ingest with a mocked client + recorded fixture, then a second run
  to prove idempotency on (restaurant_number, week_end_date).
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
from subway_ops.freshconnect.models import ControlSheetResponse
from subway_ops.ingest.controlsheet import (
    DAYS_DAILY,
    FOOTER_COL,
    column_definitions,
    flatten_row,
    generate_ddl,
    ingest,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "recorded" / "control_sheet.json"
)
MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "subway_ops"
    / "db"
    / "migrations"
    / "004_controlsheet.sql"
)


# ---------------------------------------------------------------------------
# DB-free
# ---------------------------------------------------------------------------


def test_generate_ddl_includes_every_column() -> None:
    """Generated DDL must list every column emitted by column_definitions()."""
    ddl = generate_ddl()
    for name, _typ in column_definitions():
        assert re.search(rf"\b{name}\b", ddl), f"missing column in DDL: {name}"


def test_committed_migration_matches_generator() -> None:
    """The on-disk migration is the canonical artefact; regenerating it must be a no-op."""
    assert MIGRATION_PATH.read_text(encoding="utf-8").strip() == generate_ddl().strip()


@pytest.mark.skipif(not FIXTURE_PATH.exists(), reason="No recorded control_sheet fixture")
def test_flatten_row_against_fixture() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    parsed = ControlSheetResponse.model_validate(payload)
    row = parsed.data[0]
    flat = flatten_row(row)

    # Keys come from the schema generator — flatten must populate ALL of them
    # plus the two PK columns.
    expected_cols = {name for name, _typ in column_definitions()}
    expected_cols.add("restaurant_number")
    expected_cols.add("week_end_date")
    assert set(flat.keys()) == expected_cols

    assert flat["restaurant_number"] == "4092"
    assert flat["week_end_date"] == date(2026, 5, 5)
    # spot-check daily and footer cols come from the model
    assert flat[f"cash_control_deposit_in_bank_{FOOTER_COL}"] is not None
    for day in DAYS_DAILY:
        assert f"cash_control_deposit_in_bank_{day}" in flat
    # average-footer field collapses into *_total
    assert flat[f"labor_productivity_{FOOTER_COL}"] is not None


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
    yield
    execute_sql(
        "DELETE FROM stg_controlsheet_weekly "
        "WHERE restaurant_number = '4092' AND week_end_date = :w",
        {"w": date(2026, 5, 5)},
    )


def _mock_client(payload: dict[str, Any]) -> MagicMock:
    client = MagicMock()
    client.get_control_sheet.return_value = payload
    client.close.return_value = None
    return client


@requires_db_and_fixture
def test_ingest_writes_stg_row(
    fixture_payload: dict[str, Any], seeded_store_4092: None
) -> None:
    written = ingest(date(2026, 5, 5), ["4092"], client=_mock_client(fixture_payload))
    assert written == 1

    rows = execute_sql(
        "SELECT net_sales, customer_count, "
        "cash_control_deposit_in_bank_total, "
        "labor_productivity_total "
        "FROM stg_controlsheet_weekly "
        "WHERE restaurant_number = '4092' AND week_end_date = :w",
        {"w": date(2026, 5, 5)},
    )
    assert len(rows) == 1
    net_sales, cust, deposit, productivity = rows[0]
    assert net_sales > 0
    assert cust > 0
    # depositInBank.total and labor.productivity.average both land in their *_total cols.
    assert deposit is not None
    assert productivity is not None


@requires_db_and_fixture
def test_ingest_is_idempotent(
    fixture_payload: dict[str, Any], seeded_store_4092: None
) -> None:
    client = _mock_client(fixture_payload)
    first = ingest(date(2026, 5, 5), ["4092"], client=client)
    second = ingest(date(2026, 5, 5), ["4092"], client=client)
    assert first == 1 and second == 1

    rows = execute_sql(
        "SELECT count(*) FROM stg_controlsheet_weekly "
        "WHERE restaurant_number = '4092' AND week_end_date = :w",
        {"w": date(2026, 5, 5)},
    )
    assert rows[0][0] == 1
