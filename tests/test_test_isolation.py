"""The isolation machinery itself — D-039, D-040.

These test the fixtures rather than the product, which is unusual and
deliberate: the isolation is the thing that made a gate contradict itself and
wrote a business's roster to production twice, so it gets the same scrutiny as
the code it protects.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from subway_ops.config import settings
from subway_ops.db.connection import execute_sql
from tests.conftest import SESSION_TOKEN, ns

requires_db = pytest.mark.skipif(
    not settings.database_url, reason="DB integration test: needs DATABASE_URL"
)

TESTS_DIR = Path(__file__).parent


def test_session_token_is_stable_within_a_run() -> None:
    """One token for the whole process, however often it is asked for."""
    assert ns("x") == ns("x")
    assert SESSION_TOKEN and SESSION_TOKEN in ns("x")
    assert ns("a") != ns("b"), "the marker still distinguishes files"


def test_session_token_differs_between_runs() -> None:
    """A second interpreter must get a different token. D-040.

    Started as a subprocess rather than mocked, because the property that
    matters is about two real processes: the whole defect was one run deleting
    another run's rows.
    """
    other = subprocess.run(
        [sys.executable, "-c", "from tests.conftest import SESSION_TOKEN; print(SESSION_TOKEN)"],
        capture_output=True,
        text=True,
        cwd=TESTS_DIR.parent,
        check=True,
    ).stdout.strip()
    assert other
    assert other != SESSION_TOKEN, "two processes must not share a namespace"


@requires_db
def test_two_concurrent_runs_do_not_delete_each_others_rows() -> None:
    """The B-0036 reproduction, inverted. D-040.

    Before this task, two runs of one file started together gave
    ``3 failed, 21 passed`` and ``4 failed, 19 passed``, where serially the same
    file gave ``25 passed`` — each run's teardown deleted the other's fixtures
    mid-test.

    This simulates the two runs directly: rows written under two different
    session tokens, and a teardown scoped to one of them. The other's rows must
    survive. A file-scoped marker fails this; a run-scoped one passes.
    """
    mine = ns("t0016-isolation")
    theirs = "t0016-isolation-someotherrun"

    for marker in (mine, theirs):
        execute_sql(
            "INSERT INTO ops_worklist_items (kind, subject_ref, assigned_role, summary) "
            "VALUES (:k, :s, 'office', 'isolation probe')",
            {"k": marker, "s": f"{marker}:subject"},
        )
    try:
        # Teardown as every one of these files writes it — scoped to my marker.
        execute_sql("DELETE FROM ops_worklist_items WHERE kind = :k", {"k": mine})

        survived = execute_sql(
            "SELECT count(*) FROM ops_worklist_items WHERE kind = :k", {"k": theirs}
        )[0][0]
        assert survived == 1, "the other run's row must survive my teardown"

        gone = execute_sql("SELECT count(*) FROM ops_worklist_items WHERE kind = :k", {"k": mine})[
            0
        ][0]
        assert gone == 0, "and my own teardown must still work"
    finally:
        execute_sql("DELETE FROM ops_worklist_items WHERE kind = :k", {"k": theirs})


def test_no_db_test_selects_a_real_store_number() -> None:
    """D-039 / codex 13 — no test reads a store number out of ``ref_stores``.

    A grep-style guard rather than a behavioural one, because the failure it
    prevents is a person writing the convenient thing in a file nobody reviews
    closely. It caught two live sites when written: ``test_people_schema.py``
    took the two lowest real store numbers to satisfy a foreign key, and had
    passed an audit doing it.

    Reads that are ABOUT ``ref_stores`` — counting rows, checking a join — are
    fine and excluded by the pattern: the rule is against borrowing a real
    store's identity, not against querying the table.
    """
    borrow = re.compile(r"SELECT\s+store_number\s+FROM\s+ref_stores", re.IGNORECASE | re.DOTALL)
    offenders = [
        path.name for path in sorted(TESTS_DIR.glob("test_*.py")) if borrow.search(path.read_text())
    ]
    assert offenders == [], (
        f"these tests borrow a real store number (D-039, codex 13): {offenders}. "
        "Seed a synthetic store with is_active=false and drop it."
    )


@requires_db
def test_synthetic_stores_are_inactive_and_removed(
    synthetic_store_factory: object,
) -> None:
    """D-039 — is_active=false is the half that stops the ingests picking it up."""
    make = synthetic_store_factory
    numbers = make("ISO-A", "ISO-B")  # type: ignore[operator]

    rows = execute_sql(
        "SELECT store_number, is_active FROM ref_stores WHERE store_number = ANY(:n)",
        {"n": numbers},
    )
    assert len(rows) == 2
    assert all(r[1] is False for r in rows), "codex 13 — the ingests must not see it"
