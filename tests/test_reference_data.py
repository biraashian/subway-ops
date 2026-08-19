"""Tests for reference data: CSV parsing and DB seed correctness."""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from seed_reference import (  # noqa: E402
    TIMEZONE_ALIASES,
    _parse_opening_date,
    apply_migrations,
    load_field_managers,
    load_stores,
    load_users,
    seed_field_managers,
    seed_stores,
)

# ---------------------------------------------------------------------------
# DB-free CSV parsing tests
# ---------------------------------------------------------------------------


def test_field_managers_csv_has_expected_managers() -> None:
    fms = load_field_managers()
    names = {fm["name"] for fm in fms}
    assert {"Sokhavy", "Ekta", "Lauren", "Bir"}.issubset(names)


def test_field_managers_bir_role_is_operations_manager() -> None:
    fms = load_field_managers()
    bir = next(fm for fm in fms if fm["name"] == "Bir")
    assert bir["role"] == "operations_manager"
    assert bir["email"] == "amitojsubway@gmail.com"


def test_field_manager_emails_unique() -> None:
    fms = load_field_managers()
    emails = [fm["email"] for fm in fms]
    assert len(emails) == len(set(emails))


def test_stores_csv_has_at_least_14_stores() -> None:
    stores = load_stores()
    assert len(stores) >= 14


def test_stores_have_valid_us_states() -> None:
    stores = load_stores()
    for s in stores:
        assert s["state"] in {"WA", "OR"}, s


def test_stores_have_unique_store_numbers() -> None:
    stores = load_stores()
    nums = [s["store_number"] for s in stores]
    assert len(nums) == len(set(nums))


def test_timezone_pst_normalizes_to_iana() -> None:
    assert TIMEZONE_ALIASES["PST"] == "America/Los_Angeles"


def test_stores_timezones_normalized() -> None:
    stores = load_stores()
    for s in stores:
        assert s["timezone"] == "America/Los_Angeles", s


def test_opening_date_parses_natural_language() -> None:
    assert str(_parse_opening_date("December 11, 2024")) == "2024-12-11"


def test_opening_date_empty_returns_none() -> None:
    assert _parse_opening_date("") is None


def test_users_csv_has_five_rows() -> None:
    users = load_users()
    assert len(users) == 5


def test_users_csv_two_owners() -> None:
    users = load_users()
    owners = [u for u in users if u["role"] == "owner"]
    assert len(owners) == 2
    owner_emails = {u["email"] for u in owners}
    assert owner_emails == {"amitojsubway@gmail.com", "taranghura@gmail.com"}


def test_users_csv_field_manager_assignments() -> None:
    users = load_users()
    by_email = {u["email"]: u for u in users}
    sokhavy = by_email["subway425.559@gmail.com"]
    assert sokhavy["role"] == "field_manager"
    assert set(sokhavy["assigned_stores"] or []) == {"4092", "17967", "26529", "39969"}


def test_every_assigned_field_manager_exists() -> None:
    """Every store_number in field_managers.csv assignments either matches a
    real store in stores.csv or is logged as a future store. The mapping itself
    should never reference an FM name that isn't in field_managers.csv."""
    fms = load_field_managers()
    fm_names = {fm["name"] for fm in fms}
    users = load_users()
    for u in users:
        if u["role"] == "field_manager":
            assert u["display_name"] in fm_names


# ---------------------------------------------------------------------------
# DB integration tests (skip if DATABASE_URL absent)
# ---------------------------------------------------------------------------


requires_db = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set; skipping DB integration tests",
)


@pytest.fixture
def db_conn() -> Iterator[psycopg.Connection]:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set")
    conn = psycopg.connect(url)
    try:
        yield conn
    finally:
        conn.close()


@requires_db
def test_migration_applies_idempotently(db_conn: psycopg.Connection) -> None:
    apply_migrations(db_conn)
    second_run = apply_migrations(db_conn)
    assert second_run == []  # nothing new the second time


@requires_db
def test_seed_field_managers_and_stores(db_conn: psycopg.Connection) -> None:
    apply_migrations(db_conn)
    n_fm = seed_field_managers(db_conn)
    seed_stores(db_conn)

    assert n_fm >= 3  # acceptance criterion: at least 3 FMs

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM ref_field_managers")
        fm_count_row = cur.fetchone()
        assert fm_count_row is not None
        fm_count = fm_count_row[0]

        cur.execute("SELECT count(*) FROM ref_stores")
        store_count_row = cur.fetchone()
        assert store_count_row is not None
        store_count = store_count_row[0]

        cur.execute("SELECT count(*) FROM ref_stores WHERE field_manager_name IS NULL")
        unassigned_row = cur.fetchone()
        assert unassigned_row is not None
        unassigned = unassigned_row[0]

    csv_store_count = len(load_stores())
    assert store_count == csv_store_count, "stores in DB should match stores.csv row count"
    assert fm_count == n_fm
    assert unassigned == 0, "every store must have a field manager assigned"


@requires_db
def test_every_stores_fm_exists_in_ref_field_managers(db_conn: psycopg.Connection) -> None:
    apply_migrations(db_conn)
    seed_field_managers(db_conn)
    seed_stores(db_conn)

    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT s.store_number, s.field_manager_name
            FROM ref_stores s
            LEFT JOIN ref_field_managers fm ON fm.name = s.field_manager_name
            WHERE s.field_manager_name IS NOT NULL AND fm.name IS NULL
            """
        )
        orphans = cur.fetchall()
    assert orphans == [], f"stores with FM names not in ref_field_managers: {orphans}"


@requires_db
def test_reseeding_is_idempotent(db_conn: psycopg.Connection) -> None:
    apply_migrations(db_conn)
    first_fm = seed_field_managers(db_conn)
    first_stores = seed_stores(db_conn)
    second_fm = seed_field_managers(db_conn)
    second_stores = seed_stores(db_conn)
    assert first_fm == second_fm
    assert first_stores == second_stores
