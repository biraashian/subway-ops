"""Tests for the reconciliation mart.

Each test seeds POS deposits (in ``stg_controlsheet_weekly``) and zero or
one ``ops_variance_entries`` row, then calls ``refresh()`` and asserts
the four-way status bucket: unverified / clean / flagged / escalated.
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal

import pytest

from subway_ops.calendar import previous_business_week
from subway_ops.config import (
    VARIANCE_ESCALATED_USD,
    VARIANCE_FLAGGED_USD,
    settings,
)
from subway_ops.db.connection import execute_sql
from subway_ops.db.migrate import apply_migrations
from subway_ops.transform.mart_recon_weekly import refresh

# A synthetic restaurant number that can never collide with a real store.
# ``_wipe`` hard-DELETEs every row for (TEST_STORE, WEEK_END); pointing these
# tests at a live store destroys production history on every run. Seeded
# is_active=false so the ingests' ``_active_store_numbers()`` can't pick it up.
TEST_STORE = "T-RECON-TEST"

# The last closed business week, so the seeded row always lands inside
# ``refresh(weeks_back=2)``'s window (earliest = last_closed - 7 days). A
# hardcoded date silently stops being refreshed two weeks after it is written,
# and every assertion here then reads back None.
WEEK_END = previous_business_week()[1]

TEST_USER_EMAIL = "test-recon-user@example.com"
TEST_FM_NAME = "TestFM"


requires_db = pytest.mark.skipif(
    not settings.database_url,
    reason="DB integration test: needs DATABASE_URL",
)


def test_thresholds_match_migration() -> None:
    """Sanity check that the Python and SQL thresholds didn't drift."""
    assert Decimal("5") == VARIANCE_FLAGGED_USD
    assert Decimal("50") == VARIANCE_ESCALATED_USD


@pytest.fixture
def applied_migrations() -> None:
    apply_migrations()


def _wipe() -> None:
    params = {"s": TEST_STORE, "w": WEEK_END}
    execute_sql(
        "DELETE FROM mart_recon_weekly WHERE restaurant_number = :s AND week_end_date = :w",
        params,
    )
    execute_sql(
        "DELETE FROM ops_variance_entries WHERE restaurant_number = :s AND week_end_date = :w",
        params,
    )
    execute_sql(
        "DELETE FROM stg_controlsheet_weekly WHERE restaurant_number = :s AND week_end_date = :w",
        params,
    )


@pytest.fixture
def seeded_world(applied_migrations: None) -> Iterator[None]:
    execute_sql(
        """
        INSERT INTO ref_field_managers (name, email, is_active)
        VALUES (:f, 'testfm@example.com', true)
        ON CONFLICT (name) DO NOTHING
        """,
        {"f": TEST_FM_NAME},
    )
    execute_sql(
        """
        INSERT INTO ref_stores
          (store_number, store_name, city, state, timezone, field_manager_name, is_active)
        VALUES (:s, 'Test Store', 'Seattle', 'WA', 'America/Los_Angeles', :f, false)
        ON CONFLICT (store_number) DO NOTHING
        """,
        {"s": TEST_STORE, "f": TEST_FM_NAME},
    )
    execute_sql(
        """
        INSERT INTO ref_users (email, display_name, role, password_hash, is_active)
        VALUES (:e, 'Recon Test', 'owner', 'unused-hash', true)
        ON CONFLICT (email) DO NOTHING
        """,
        {"e": TEST_USER_EMAIL},
    )
    _wipe()
    yield
    # Teardown in FK order: the mart/staging rows go first (they reference
    # ref_stores), then the store (it references ref_field_managers), then
    # the manager. Leaving these behind pollutes the live reference tables.
    _wipe()
    execute_sql("DELETE FROM ref_users WHERE email = :e", {"e": TEST_USER_EMAIL})
    execute_sql("DELETE FROM ref_stores WHERE store_number = :s", {"s": TEST_STORE})
    execute_sql("DELETE FROM ref_field_managers WHERE name = :f", {"f": TEST_FM_NAME})


def _seed_pos(amount: Decimal) -> None:
    execute_sql(
        """
        INSERT INTO stg_controlsheet_weekly
            (restaurant_number, week_end_date, cash_control_deposit_in_bank_total)
        VALUES (:s, :w, :a)
        ON CONFLICT (restaurant_number, week_end_date) DO UPDATE SET
          cash_control_deposit_in_bank_total = EXCLUDED.cash_control_deposit_in_bank_total
        """,
        {"s": TEST_STORE, "w": WEEK_END, "a": amount},
    )


def _seed_variance_entry(amount: Decimal) -> None:
    execute_sql(
        """
        INSERT INTO ops_variance_entries
            (restaurant_number, week_end_date, actual_bank_deposit, entered_by, note)
        VALUES (:s, :w, :a, :u, 'pytest')
        ON CONFLICT (restaurant_number, week_end_date) DO UPDATE SET
          actual_bank_deposit = EXCLUDED.actual_bank_deposit,
          entered_by = EXCLUDED.entered_by
        """,
        {"s": TEST_STORE, "w": WEEK_END, "a": amount, "u": TEST_USER_EMAIL},
    )


def _read_mart() -> tuple[Decimal | None, Decimal | None, Decimal | None, str | None]:
    rows = execute_sql(
        """
        SELECT pos_deposit_in_bank, actual_bank_deposit, variance, status
        FROM mart_recon_weekly
        WHERE restaurant_number = :s AND week_end_date = :w
        """,
        {"s": TEST_STORE, "w": WEEK_END},
    )
    if not rows:
        return None, None, None, None
    return rows[0]


# ---------------------------------------------------------------------------
# Status cases
# ---------------------------------------------------------------------------


@requires_db
def test_status_unverified_when_no_variance_entry(seeded_world: None) -> None:
    _seed_pos(Decimal("1500.00"))
    refresh(weeks_back=2)
    pos, actual, variance, status = _read_mart()
    assert pos == Decimal("1500.0000")
    assert actual is None
    assert variance is None
    assert status == "unverified"


@requires_db
def test_status_clean_within_5_dollars(seeded_world: None) -> None:
    _seed_pos(Decimal("1500.00"))
    _seed_variance_entry(Decimal("1497.50"))  # diff = $2.50 → clean
    refresh(weeks_back=2)
    _, _, variance, status = _read_mart()
    assert variance == Decimal("2.5000")
    assert status == "clean"


@requires_db
def test_status_flagged_between_5_and_50(seeded_world: None) -> None:
    _seed_pos(Decimal("1500.00"))
    _seed_variance_entry(Decimal("1480.00"))  # diff = $20.00 → flagged
    refresh(weeks_back=2)
    _, _, variance, status = _read_mart()
    assert variance == Decimal("20.0000")
    assert status == "flagged"


@requires_db
def test_status_escalated_above_50(seeded_world: None) -> None:
    _seed_pos(Decimal("1500.00"))
    _seed_variance_entry(Decimal("1400.00"))  # diff = $100.00 → escalated
    refresh(weeks_back=2)
    _, _, variance, status = _read_mart()
    assert variance == Decimal("100.0000")
    assert status == "escalated"


@requires_db
def test_status_at_threshold_boundaries(seeded_world: None) -> None:
    """Boundary checks: exactly $5 → clean, exactly $50 → flagged."""
    _seed_pos(Decimal("1000.00"))

    _seed_variance_entry(Decimal("995.00"))  # diff = $5 → clean (≤ 5)
    refresh(weeks_back=2)
    _, _, _, status = _read_mart()
    assert status == "clean"

    _seed_variance_entry(Decimal("950.00"))  # diff = $50 → flagged (≤ 50)
    refresh(weeks_back=2)
    _, _, _, status = _read_mart()
    assert status == "flagged"


@requires_db
def test_refresh_is_idempotent(seeded_world: None) -> None:
    _seed_pos(Decimal("1500.00"))
    first = refresh(weeks_back=2)
    second = refresh(weeks_back=2)
    # Row count is whatever's in scope; the meaningful invariant is that
    # we end up with exactly one row for the test (store, week).
    assert first >= 1 and second >= 1
    count = execute_sql(
        "SELECT count(*) FROM mart_recon_weekly "
        "WHERE restaurant_number = :s AND week_end_date = :w",
        {"s": TEST_STORE, "w": WEEK_END},
    )
    assert count[0][0] == 1


@requires_db
def test_refresh_rejects_zero_weeks_back() -> None:
    with pytest.raises(ValueError, match="weeks_back must be positive"):
        refresh(weeks_back=0)


@requires_db
def test_negative_variance_status_uses_absolute_value(seeded_world: None) -> None:
    """Deposit ABOVE the POS-recorded amount should still bucket the
    same as below — status is about |variance|, not sign."""
    _seed_pos(Decimal("1000.00"))
    _seed_variance_entry(Decimal("1020.00"))  # POS - actual = -20 → flagged
    refresh(weeks_back=2)
    _, _, variance, status = _read_mart()
    assert variance == Decimal("-20.0000")
    assert status == "flagged"
