"""Tests for wages — SPEC-PPL-001 AC-011, AC-012, AC-013, AC-014.

DB-backed per B-0001 until D-025's containerised Postgres lands (T-0011). Rows
are namespaced and removed in dependency order. No real store number, no
hardcoded date (codex/13-BUILD/CONVENTIONS.md).
"""

from __future__ import annotations

import inspect
from collections.abc import Iterator
from datetime import timedelta
from decimal import Decimal

import pytest

from subway_ops.calendar import business_date_now
from subway_ops.config import settings
from subway_ops.db.connection import execute_sql
from subway_ops.db.migrate import apply_migrations
from subway_ops.people.wages import (
    WAGE_ROLES,
    rate_in_force,
    read_wage,
    record_wage,
)

MARK = "t0007-wages-selftest"

requires_db = pytest.mark.skipif(
    not settings.database_url, reason="DB integration test: needs DATABASE_URL"
)


def _wipe() -> None:
    execute_sql(
        "DELETE FROM ref_employee_wages WHERE employee_id IN "
        "(SELECT employee_id FROM ref_employees WHERE display_name = :m)",
        {"m": MARK},
    )
    execute_sql("DELETE FROM ref_employees WHERE display_name = :m", {"m": MARK})


@pytest.fixture
def person() -> Iterator[int]:
    apply_migrations()
    _wipe()
    rows = execute_sql(
        "INSERT INTO ref_employees (display_name) VALUES (:m) RETURNING employee_id",
        {"m": MARK},
    )
    yield int(rows[0][0])
    _wipe()


# --- AC-011 — insert, never modify -----------------------------------------


@requires_db
def test_record_wage_inserts_and_never_updates(person: int) -> None:
    """AC-011 / INV-005 — a second rate for the same date is REFUSED, not applied.

    The T-0004 audit proved the schema cannot enforce this: a raw UPDATE
    rewrites a historical rate happily. The PK only blocks a second ROW. So this
    test is the enforcement, and it asserts the original rate SURVIVES rather
    than merely that an error was raised.
    """
    today = business_date_now()
    record_wage(
        employee_id=person,
        effective_date=today,
        hourly_rate=Decimal("18.0000"),
        set_by=MARK,
        actor_role="office",
    )
    with pytest.raises(Exception, match="ref_employee_wages_pkey"):
        record_wage(
            employee_id=person,
            effective_date=today,
            hourly_rate=Decimal("99.0000"),
            set_by=MARK,
            actor_role="office",
        )
    assert rate_in_force(person, today) == Decimal("18.0000"), (
        "the original rate must survive a refused re-record"
    )


@requires_db
def test_record_wage_carries_set_by_and_set_at(person: int) -> None:
    """AC-011 — wages are hand-keyed (D-020), so who and when are the audit trail."""
    record_wage(
        employee_id=person,
        effective_date=business_date_now(),
        hourly_rate=Decimal("21.5000"),
        set_by=MARK,
        actor_role="owner",
    )
    rows = execute_sql(
        "SELECT set_by, set_at IS NOT NULL FROM ref_employee_wages WHERE employee_id = :e",
        {"e": person},
    )
    assert rows[0][0] == MARK
    assert rows[0][1] is True


# --- AC-012 — the rate in force for a DATE ---------------------------------


@requires_db
def test_rate_in_force_resolves_the_row_for_that_date(person: int) -> None:
    """AC-012 — not the current rate. Costing March must use March's rate."""
    today = business_date_now()
    record_wage(
        employee_id=person,
        effective_date=today - timedelta(days=60),
        hourly_rate=Decimal("16.0000"),
        set_by=MARK,
        actor_role="office",
    )
    record_wage(
        employee_id=person,
        effective_date=today,
        hourly_rate=Decimal("20.0000"),
        set_by=MARK,
        actor_role="office",
    )
    assert rate_in_force(person, today - timedelta(days=30)) == Decimal("16.0000")


@requires_db
def test_rate_in_force_across_a_raise(person: int) -> None:
    """Before, exactly on, and after the effective date.

    "On" belongs to the new rate — REQ-003 says the greatest effective_date
    LESS THAN OR EQUAL TO the asked date.
    """
    today = business_date_now()
    raise_day = today - timedelta(days=10)
    record_wage(
        employee_id=person,
        effective_date=today - timedelta(days=90),
        hourly_rate=Decimal("15.0000"),
        set_by=MARK,
        actor_role="office",
    )
    record_wage(
        employee_id=person,
        effective_date=raise_day,
        hourly_rate=Decimal("19.0000"),
        set_by=MARK,
        actor_role="office",
    )
    assert rate_in_force(person, raise_day - timedelta(days=1)) == Decimal("15.0000")
    assert rate_in_force(person, raise_day) == Decimal("19.0000")
    assert rate_in_force(person, raise_day + timedelta(days=1)) == Decimal("19.0000")


@requires_db
def test_rate_in_force_returns_none_when_no_row(person: int) -> None:
    """INV-007 — None, never Decimal("0"). A zero understates labor cost invisibly."""
    result = rate_in_force(person, business_date_now())
    assert result is None
    assert result != Decimal("0")


@requires_db
def test_rate_in_force_returns_none_before_the_first_row(person: int) -> None:
    """A date earlier than any recorded rate is still 'we do not know'."""
    today = business_date_now()
    record_wage(
        employee_id=person,
        effective_date=today,
        hourly_rate=Decimal("18.0000"),
        set_by=MARK,
        actor_role="office",
    )
    assert rate_in_force(person, today - timedelta(days=1)) is None


@requires_db
def test_backdated_wage_insert_leaves_later_rows_intact(person: int) -> None:
    """A correction for an earlier date must not disturb the rate after it."""
    today = business_date_now()
    record_wage(
        employee_id=person,
        effective_date=today,
        hourly_rate=Decimal("20.0000"),
        set_by=MARK,
        actor_role="office",
    )
    record_wage(
        employee_id=person,
        effective_date=today - timedelta(days=45),
        hourly_rate=Decimal("17.0000"),
        set_by=MARK,
        actor_role="office",
    )
    assert rate_in_force(person, today) == Decimal("20.0000")
    assert rate_in_force(person, today - timedelta(days=30)) == Decimal("17.0000")

    rows = execute_sql(
        "SELECT count(*) FROM ref_employee_wages WHERE employee_id = :e", {"e": person}
    )
    assert rows[0][0] == 2, "a backdated correction is a NEW row, not an edit"


# --- AC-013 — office and owner only ----------------------------------------


@requires_db
@pytest.mark.parametrize("role", ["crew", "shift_lead", "store_manager", "field_manager"])
def test_non_office_role_raises_permission_error(person: int, role: str) -> None:
    """AC-013 — every rung below office is refused, including field_manager.

    field_manager is the interesting one: they outrank a store manager and run a
    territory, and they still may not see or set pay. INV-006 is about the kind
    of data, not seniority.
    """
    with pytest.raises(PermissionError, match="may not set wages"):
        record_wage(
            employee_id=person,
            effective_date=business_date_now(),
            hourly_rate=Decimal("18.0000"),
            set_by=MARK,
            actor_role=role,
        )


@requires_db
def test_permission_error_body_contains_no_rate(person: int) -> None:
    """AC-013's second clause — the rate appears in NO part of the refusal.

    An exception message is a response body the moment it reaches a log line or
    an API error handler. This checks the whole formatted exception, not just
    that a PermissionError was raised.
    """
    secret_rate = Decimal("47.1234")
    with pytest.raises(PermissionError) as caught:
        record_wage(
            employee_id=person,
            effective_date=business_date_now(),
            hourly_rate=secret_rate,
            set_by=MARK,
            actor_role="crew",
        )
    body = f"{caught.value!r} {caught.value!s}"
    assert "47.1234" not in body
    assert str(secret_rate) not in body
    # NOT `assert "47" not in body`. That was the original assertion and it
    # failed the gate at 0a1e02e: `body` also carries the employee_id, which is
    # BIGSERIAL and climbs forever, so the test broke the moment that id
    # happened to contain "47" — nothing to do with the rate. An assertion
    # broader than the property it is testing fails on unrelated data, and a
    # test that cries wolf gets muted.


@requires_db
def test_permitted_roles_are_exactly_office_and_owner(person: int) -> None:
    assert frozenset({"office", "owner"}) == WAGE_ROLES
    for role in sorted(WAGE_ROLES):
        record_wage(
            employee_id=person,
            effective_date=business_date_now() - timedelta(days=200 + len(role)),
            hourly_rate=Decimal("15.0000"),
            set_by=MARK,
            actor_role=role,
        )


@requires_db
def test_permission_is_checked_before_the_rate(person: int) -> None:
    """A refused caller gets PermissionError even with an invalid rate.

    Order matters: validating the rate first would tell an unauthorised caller
    whether their proposed rate was acceptable, which is a small oracle they
    should not have.
    """
    with pytest.raises(PermissionError):
        record_wage(
            employee_id=person,
            effective_date=business_date_now(),
            hourly_rate=Decimal("-5.0000"),
            set_by=MARK,
            actor_role="crew",
        )


# --- AC-014 — positive rates only ------------------------------------------


@requires_db
@pytest.mark.parametrize("bad", ["0", "-0.0001", "-20.0000"])
def test_zero_and_negative_rate_rejected(person: int, bad: str) -> None:
    """AC-014 — refused in Python as well as by the CHECK, and nothing is written."""
    with pytest.raises(ValueError, match="must be positive"):
        record_wage(
            employee_id=person,
            effective_date=business_date_now(),
            hourly_rate=Decimal(bad),
            set_by=MARK,
            actor_role="office",
        )
    rows = execute_sql(
        "SELECT count(*) FROM ref_employee_wages WHERE employee_id = :e", {"e": person}
    )
    assert rows[0][0] == 0


# --- CON-006 — the guarded read (D-037) ------------------------------------


@requires_db
@pytest.mark.parametrize("role", ["crew", "shift_lead", "store_manager", "field_manager"])
def test_read_wage_refuses_a_non_office_role(person: int, role: str) -> None:
    """AC-013 / CON-006 — the READ that AC-013 actually names is now guarded.

    Before D-037 this had no code path at all: AC-013 described a read and
    CON-002 gave it no actor to check, so every test claiming to cover AC-013
    was in fact exercising a write.
    """
    record_wage(
        employee_id=person,
        effective_date=business_date_now(),
        hourly_rate=Decimal("18.0000"),
        set_by=MARK,
        actor_role="office",
    )
    with pytest.raises(PermissionError, match="may not read wages"):
        read_wage(person, business_date_now(), actor_role=role)


@requires_db
def test_read_wage_error_never_contains_the_rate(person: int) -> None:
    """AC-013 clause 2 — and here the rate is never even read before refusing."""
    secret_rate = Decimal("61.5432")
    record_wage(
        employee_id=person,
        effective_date=business_date_now(),
        hourly_rate=secret_rate,
        set_by=MARK,
        actor_role="office",
    )
    with pytest.raises(PermissionError) as caught:
        read_wage(person, business_date_now(), actor_role="crew")
    body = f"{caught.value!r} {caught.value!s}"
    assert str(secret_rate) not in body
    assert "61.5432" not in body


@requires_db
def test_read_wage_returns_the_rate_for_a_permitted_role(person: int) -> None:
    """The guard must not break the read for the roles that may have it."""
    record_wage(
        employee_id=person,
        effective_date=business_date_now(),
        hourly_rate=Decimal("23.0000"),
        set_by=MARK,
        actor_role="office",
    )
    for role in sorted(WAGE_ROLES):
        assert read_wage(person, business_date_now(), actor_role=role) == Decimal("23.0000")


@requires_db
def test_read_wage_returns_none_for_an_absent_rate(person: int) -> None:
    """INV-007 survives the guard — absent is still None, never Decimal("0")."""
    assert read_wage(person, business_date_now(), actor_role="office") is None


@requires_db
def test_rate_in_force_stays_unguarded_for_marts(person: int) -> None:
    """D-037, pinned deliberately — this is a decision, not an oversight.

    ``rate_in_force`` takes no actor and must keep taking none: it is the
    internal resolver for marts and for ``cost_week``, neither of which has a
    human actor to name. If someone later adds a guard here, this test fails and
    sends them to D-037 rather than letting the two accessors quietly merge.
    """
    assert "actor_role" not in inspect.signature(rate_in_force).parameters

    record_wage(
        employee_id=person,
        effective_date=business_date_now(),
        hourly_rate=Decimal("19.0000"),
        set_by=MARK,
        actor_role="office",
    )
    assert rate_in_force(person, business_date_now()) == Decimal("19.0000")
