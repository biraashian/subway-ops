"""Tests for the reconciliation review page + supporting helpers."""

from __future__ import annotations

import importlib.util
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from types import ModuleType

import pandas as pd
import pytest

from subway_ops.config import settings
from subway_ops.dashboard.data import (
    delete_variance_entries,
    recent_week_ends,
    save_variance_entries,
)
from subway_ops.db.connection import execute_sql
from subway_ops.db.migrate import apply_migrations


def _load_recon_page() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "recon_module",
        "src/subway_ops/dashboard/pages/4_reconciliation.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Pure: diff logic
# ---------------------------------------------------------------------------


def test_diff_rows_detects_inserted_entry() -> None:
    module = _load_recon_page()
    original = pd.DataFrame(
        {
            "restaurant_number": ["4092"],
            "week_end_date": [date(2026, 5, 12)],
            "actual_bank_deposit": [None],
            "note": [None],
        }
    )
    edited = original.copy()
    edited.at[0, "actual_bank_deposit"] = 1480.0
    edited.at[0, "note"] = "Bank confirmed"
    upserts, deletes = module._diff_rows(original, edited)
    assert len(upserts) == 1
    assert upserts[0]["restaurant_number"] == "4092"
    assert upserts[0]["actual_bank_deposit"] == 1480.0
    assert upserts[0]["note"] == "Bank confirmed"
    assert deletes == []


def test_diff_rows_detects_amount_change() -> None:
    module = _load_recon_page()
    original = pd.DataFrame(
        {
            "restaurant_number": ["4092"],
            "week_end_date": [date(2026, 5, 12)],
            "actual_bank_deposit": [1500.0],
            "note": ["initial"],
        }
    )
    edited = original.copy()
    edited.at[0, "actual_bank_deposit"] = 1480.0
    upserts, deletes = module._diff_rows(original, edited)
    assert len(upserts) == 1
    assert upserts[0]["actual_bank_deposit"] == 1480.0
    assert deletes == []


def test_diff_rows_detects_note_only_change_when_actual_present() -> None:
    module = _load_recon_page()
    original = pd.DataFrame(
        {
            "restaurant_number": ["4092"],
            "week_end_date": [date(2026, 5, 12)],
            "actual_bank_deposit": [1500.0],
            "note": ["initial"],
        }
    )
    edited = original.copy()
    edited.at[0, "note"] = "Updated note"
    upserts, _ = module._diff_rows(original, edited)
    assert len(upserts) == 1
    assert upserts[0]["note"] == "Updated note"


def test_diff_rows_ignores_note_change_when_actual_is_null() -> None:
    """A note without an actual deposit has nowhere to live — skip it."""
    module = _load_recon_page()
    original = pd.DataFrame(
        {
            "restaurant_number": ["4092"],
            "week_end_date": [date(2026, 5, 12)],
            "actual_bank_deposit": [None],
            "note": [None],
        }
    )
    edited = original.copy()
    edited.at[0, "note"] = "Stray note"
    upserts, deletes = module._diff_rows(original, edited)
    assert upserts == []
    assert deletes == []


def test_diff_rows_emits_delete_when_actual_cleared() -> None:
    module = _load_recon_page()
    original = pd.DataFrame(
        {
            "restaurant_number": ["4092"],
            "week_end_date": [date(2026, 5, 12)],
            "actual_bank_deposit": [1500.0],
            "note": ["old"],
        }
    )
    edited = original.copy()
    edited.at[0, "actual_bank_deposit"] = None
    upserts, deletes = module._diff_rows(original, edited)
    assert upserts == []
    assert deletes == [("4092", date(2026, 5, 12))]


# ---------------------------------------------------------------------------
# recent_week_ends helper
# ---------------------------------------------------------------------------


def test_recent_week_ends_returns_n_tuesdays_descending() -> None:
    out = recent_week_ends(4, today=date(2026, 5, 13))
    assert out == [
        date(2026, 5, 12),
        date(2026, 5, 5),
        date(2026, 4, 28),
        date(2026, 4, 21),
    ]


def test_recent_week_ends_handles_zero() -> None:
    assert recent_week_ends(0, today=date(2026, 5, 13)) == []


# ---------------------------------------------------------------------------
# DB integration: save + delete round-trip
# ---------------------------------------------------------------------------


requires_db = pytest.mark.skipif(
    not settings.database_url, reason="DB integration test: needs DATABASE_URL"
)

TEST_STORE = "4092"
WEEK_END = date(2026, 5, 5)
TEST_USER = "recon-page-test@example.com"


@pytest.fixture
def applied_migrations() -> None:
    apply_migrations()


@pytest.fixture
def seeded_world(applied_migrations: None) -> Iterator[None]:
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
        VALUES (:s, 'Test', 'Seattle', 'WA', 'America/Los_Angeles', 'TestFM', true)
        ON CONFLICT (store_number) DO NOTHING
        """,
        {"s": TEST_STORE},
    )
    execute_sql(
        """
        INSERT INTO ref_users (email, display_name, role, password_hash, is_active)
        VALUES (:e, 'Recon Page', 'owner', 'unused', true)
        ON CONFLICT (email) DO NOTHING
        """,
        {"e": TEST_USER},
    )
    execute_sql(
        "DELETE FROM ops_variance_entries WHERE restaurant_number = :s AND week_end_date = :w",
        {"s": TEST_STORE, "w": WEEK_END},
    )
    yield
    execute_sql(
        "DELETE FROM ops_variance_entries WHERE restaurant_number = :s AND week_end_date = :w",
        {"s": TEST_STORE, "w": WEEK_END},
    )
    execute_sql("DELETE FROM ref_users WHERE email = :e", {"e": TEST_USER})


@requires_db
def test_save_variance_entries_inserts_with_audit(seeded_world: None) -> None:
    n = save_variance_entries(
        [
            {
                "restaurant_number": TEST_STORE,
                "week_end_date": WEEK_END,
                "actual_bank_deposit": Decimal("1480.00"),
                "note": "first save",
            }
        ],
        entered_by=TEST_USER,
    )
    assert n == 1
    rows = execute_sql(
        "SELECT actual_bank_deposit, entered_by, note "
        "FROM ops_variance_entries "
        "WHERE restaurant_number = :s AND week_end_date = :w",
        {"s": TEST_STORE, "w": WEEK_END},
    )
    assert rows[0][0] == Decimal("1480.0000")
    assert rows[0][1] == TEST_USER
    assert rows[0][2] == "first save"


@requires_db
def test_save_variance_entries_updates_existing_row(seeded_world: None) -> None:
    save_variance_entries(
        [
            {
                "restaurant_number": TEST_STORE,
                "week_end_date": WEEK_END,
                "actual_bank_deposit": Decimal("1000.00"),
                "note": None,
            }
        ],
        entered_by=TEST_USER,
    )
    save_variance_entries(
        [
            {
                "restaurant_number": TEST_STORE,
                "week_end_date": WEEK_END,
                "actual_bank_deposit": Decimal("1234.56"),
                "note": "corrected",
            }
        ],
        entered_by=TEST_USER,
    )
    rows = execute_sql(
        "SELECT count(*), MAX(actual_bank_deposit), MAX(note) "
        "FROM ops_variance_entries "
        "WHERE restaurant_number = :s AND week_end_date = :w",
        {"s": TEST_STORE, "w": WEEK_END},
    )
    count, amount, note = rows[0]
    assert count == 1  # UPSERT, not duplicate
    assert amount == Decimal("1234.5600")
    assert note == "corrected"


@requires_db
def test_save_variance_entries_requires_entered_by() -> None:
    with pytest.raises(ValueError, match="entered_by is required"):
        save_variance_entries(
            [
                {
                    "restaurant_number": TEST_STORE,
                    "week_end_date": WEEK_END,
                    "actual_bank_deposit": Decimal("1000.00"),
                    "note": None,
                }
            ],
            entered_by="",
        )


@requires_db
def test_save_variance_entries_no_op_on_empty() -> None:
    assert save_variance_entries([], entered_by=TEST_USER) == 0


@requires_db
def test_delete_variance_entries_removes_targeted_rows(seeded_world: None) -> None:
    save_variance_entries(
        [
            {
                "restaurant_number": TEST_STORE,
                "week_end_date": WEEK_END,
                "actual_bank_deposit": Decimal("1234.00"),
                "note": None,
            }
        ],
        entered_by=TEST_USER,
    )
    deleted = delete_variance_entries([(TEST_STORE, WEEK_END)])
    assert deleted == 1
    rows = execute_sql(
        "SELECT count(*) FROM ops_variance_entries "
        "WHERE restaurant_number = :s AND week_end_date = :w",
        {"s": TEST_STORE, "w": WEEK_END},
    )
    assert rows[0][0] == 0


@requires_db
def test_delete_variance_entries_no_op_on_empty() -> None:
    assert delete_variance_entries([]) == 0
