"""Tests for the worklist helper — SPEC-PPL-001 AC-018, AC-020.

These are DB-backed and, per B-0001, run against the live database. Every
subject_ref is namespaced with a synthetic prefix that no real producer will
ever emit, and teardown removes exactly those rows. No real store number, no
hardcoded date (codex/13-BUILD/CONVENTIONS.md).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta

import pytest

from subway_ops.calendar import business_date_now
from subway_ops.config import settings
from subway_ops.db.connection import execute_sql
from subway_ops.db.migrate import apply_migrations
from subway_ops.db.worklist import open_item, resolve_item

# Namespaced so teardown can delete exactly what these tests made, and so a
# stray row is instantly identifiable as test residue rather than real work.
KIND = "t0003_selftest"
SUBJECT = "t0003:subject-a"
SUBJECT_B = "t0003:subject-b"

requires_db = pytest.mark.skipif(
    not settings.database_url,
    reason="DB integration test: needs DATABASE_URL",
)


def _wipe() -> None:
    execute_sql("DELETE FROM ops_worklist_items WHERE kind = :k", {"k": KIND})


def _states(subject: str) -> list[str]:
    rows = execute_sql(
        "SELECT state FROM ops_worklist_items "
        "WHERE kind = :k AND subject_ref = :s ORDER BY id",
        {"k": KIND, "s": subject},
    )
    return [r[0] for r in rows]


@pytest.fixture
def clean_worklist() -> Iterator[None]:
    apply_migrations()
    _wipe()
    yield
    _wipe()


@requires_db
def test_open_item_creates_row(clean_worklist: None) -> None:
    item_id = open_item(
        kind=KIND,
        subject_ref=SUBJECT,
        assigned_role="office",
        summary="needs a wage",
    )
    assert item_id is not None
    assert _states(SUBJECT) == ["open"]


@requires_db
def test_open_item_is_idempotent_while_one_is_open(clean_worklist: None) -> None:
    """AC-018 — SHALL NOT open a duplicate while one is already open."""
    first = open_item(
        kind=KIND, subject_ref=SUBJECT, assigned_role="office", summary="first"
    )
    second = open_item(
        kind=KIND, subject_ref=SUBJECT, assigned_role="office", summary="second"
    )
    assert first is not None
    assert second is None, "a live item must suppress a second open"
    assert _states(SUBJECT) == ["open"], "exactly one row, not two"


@requires_db
def test_open_item_suppressed_while_in_progress(clean_worklist: None) -> None:
    """in_progress is a live state too — the index covers both."""
    open_item(kind=KIND, subject_ref=SUBJECT, assigned_role="office", summary="x")
    execute_sql(
        "UPDATE ops_worklist_items SET state = 'in_progress' "
        "WHERE kind = :k AND subject_ref = :s",
        {"k": KIND, "s": SUBJECT},
    )
    assert (
        open_item(kind=KIND, subject_ref=SUBJECT, assigned_role="office", summary="y")
        is None
    )


@requires_db
def test_open_item_creates_again_after_resolve(clean_worklist: None) -> None:
    """Resolved is not suppressed forever — a subject can go bad again."""
    open_item(kind=KIND, subject_ref=SUBJECT, assigned_role="office", summary="first")
    resolve_item(KIND, SUBJECT)
    reopened = open_item(
        kind=KIND, subject_ref=SUBJECT, assigned_role="office", summary="again"
    )
    assert reopened is not None
    assert _states(SUBJECT) == ["resolved", "open"]


@requires_db
def test_resolve_item_closes_only_matching_subject(clean_worklist: None) -> None:
    """AC-020 — resolving one subject leaves its neighbours alone."""
    open_item(kind=KIND, subject_ref=SUBJECT, assigned_role="office", summary="a")
    open_item(kind=KIND, subject_ref=SUBJECT_B, assigned_role="office", summary="b")

    assert resolve_item(KIND, SUBJECT) == 1
    assert _states(SUBJECT) == ["resolved"]
    assert _states(SUBJECT_B) == ["open"]


@requires_db
def test_resolve_item_on_absent_subject_returns_zero(clean_worklist: None) -> None:
    """Sweeping a population must not raise on subjects that are already fine."""
    assert resolve_item(KIND, "t0003:never-existed") == 0


@requires_db
def test_resolve_records_who_and_when(clean_worklist: None) -> None:
    open_item(kind=KIND, subject_ref=SUBJECT, assigned_role="office", summary="a")
    resolve_item(KIND, SUBJECT, resolved_by="office@example.com")
    rows = execute_sql(
        "SELECT resolved_by, resolved_at IS NOT NULL FROM ops_worklist_items "
        "WHERE kind = :k AND subject_ref = :s",
        {"k": KIND, "s": SUBJECT},
    )
    assert rows[0][0] == "office@example.com"
    assert rows[0][1] is True


@requires_db
def test_due_date_is_optional(clean_worklist: None) -> None:
    due = business_date_now() + timedelta(days=5)
    open_item(
        kind=KIND,
        subject_ref=SUBJECT,
        assigned_role="office",
        summary="with due date",
        due_date=due,
    )
    open_item(
        kind=KIND, subject_ref=SUBJECT_B, assigned_role="office", summary="without"
    )
    rows = execute_sql(
        "SELECT subject_ref, due_date FROM ops_worklist_items "
        "WHERE kind = :k ORDER BY subject_ref",
        {"k": KIND},
    )
    assert rows[0][1] == due
    assert rows[1][1] is None


@requires_db
def test_unknown_state_rejected_by_check_constraint(clean_worklist: None) -> None:
    open_item(kind=KIND, subject_ref=SUBJECT, assigned_role="office", summary="a")
    with pytest.raises(Exception, match="state"):
        execute_sql(
            "UPDATE ops_worklist_items SET state = 'wibble' WHERE kind = :k",
            {"k": KIND},
        )


@requires_db
def test_unknown_role_rejected_by_check_constraint(clean_worklist: None) -> None:
    """A typo'd role would assign the item to nobody and hide it forever."""
    with pytest.raises(Exception, match="assigned_role"):
        open_item(
            kind=KIND,
            subject_ref=SUBJECT,
            assigned_role="offcie",
            summary="typo",
        )


@requires_db
def test_raw_duplicate_insert_is_refused_by_the_index(clean_worklist: None) -> None:
    """AC-018 holds even for a producer that bypasses ``open_item``.

    ``open_item`` uses ON CONFLICT DO NOTHING, so its own callers never see an
    error — which means a passing idempotency test does not by itself prove the
    partial unique index exists. This inserts directly and asserts the database
    refuses it. Without the index this INSERT succeeds and AC-018 is enforced
    only by convention.
    """
    open_item(kind=KIND, subject_ref=SUBJECT, assigned_role="office", summary="a")
    with pytest.raises(Exception, match="uq_worklist_open_subject"):
        execute_sql(
            "INSERT INTO ops_worklist_items "
            "(kind, subject_ref, assigned_role, summary) "
            "VALUES (:k, :s, 'office', 'bypass')",
            {"k": KIND, "s": SUBJECT},
        )


@requires_db
def test_all_six_ladder_roles_are_accepted(clean_worklist: None) -> None:
    """The CHECK must match codex/00-INSTITUTION's ladder exactly."""
    ladder = ("owner", "field_manager", "office", "store_manager", "shift_lead", "crew")
    for i, role in enumerate(ladder):
        assert (
            open_item(
                kind=KIND,
                subject_ref=f"t0003:role-{i}",
                assigned_role=role,
                summary=role,
            )
            is not None
        ), f"{role} is in the codex ladder but rejected by the CHECK"
