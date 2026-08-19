"""Shared pytest fixtures — test isolation against the shared database.

Until D-025's containerised Postgres lands (T-0011), every DB-backed test in
this repo runs against the live database (B-0001). Two rules make that survivable
and both exist because both were broken:

* **D-040 — namespaces are per RUN, not per file.** A marker like
  ``MARK = "t0004-selftest"`` identifies the file, and teardown deletes
  everything carrying it. Two concurrent runs therefore delete each other's
  fixtures mid-test. Measured before this module existed: two runs of one file
  started together gave ``3 failed, 21 passed`` and ``4 failed, 19 passed``,
  where the same file run serially gave ``25 passed``. A pre-merge gate and an
  ``/audit`` re-run of the same commit disagreed for exactly this reason.

* **D-039 — a test never points at a real store.** codex 13 says so plainly,
  after ``test_mart_recon_weekly.py`` spent three months hard-deleting a real
  store's history on every run. Fixtures create the stores they need and drop
  them.

Neither rule survives on discipline alone, which is why the mechanics live here
rather than in a convention nobody re-reads.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest

from subway_ops.db.connection import execute_sql

#: A token unique to this pytest process, computed once at import.
#:
#: The PID is in there so a human reading a stray row can tell which process
#: left it; the random suffix is there because PIDs are recycled and two runs a
#: few seconds apart could otherwise collide. Short, because it is concatenated
#: into `clerk_id` and `store_number` columns that real data also uses and an
#: over-long marker starts colliding with column widths.
SESSION_TOKEN: str = f"{os.getpid():d}{uuid.uuid4().hex[:6]}"


def ns(marker: str) -> str:
    """Namespace ``marker`` to this run. D-040.

    Every DB-backed test file passes its own marker through this, so
    ``t0004-selftest`` becomes ``t0004-selftest-40123abc12de`` for one process
    and something else for the next. Teardown filters on the namespaced value,
    so a concurrent run's rows are invisible to it.

    Deliberately a plain function rather than a fixture: markers are module-level
    constants in every one of these files, evaluated at import time, and a
    fixture cannot be read there.
    """
    return f"{marker}-{SESSION_TOKEN}"


@pytest.fixture(scope="session")
def session_token() -> str:
    """The same token, for tests that want to assert on it."""
    return SESSION_TOKEN


@pytest.fixture
def synthetic_store_factory() -> Iterator[object]:
    """Create synthetic stores, drop them afterwards. D-039.

    ``is_active=false`` is not decoration — codex 13 requires it so the ingests
    cannot pick the store up and start writing real-looking data against it.

    Yields a callable taking any number of store numbers. They are namespaced to
    the run like everything else, so two concurrent runs do not fight over the
    same primary key.
    """
    created: list[str] = []

    def make(*suffixes: str) -> list[str]:
        numbers = [f"T-{s}-{SESSION_TOKEN}"[:32] for s in suffixes]
        for number in numbers:
            execute_sql(
                """
                INSERT INTO ref_stores
                    (store_number, store_name, city, state, is_active)
                VALUES (:n, :name, 'Testville', 'WA', false)
                ON CONFLICT (store_number) DO NOTHING
                """,
                {"n": number, "name": f"synthetic {number}"},
            )
            created.append(number)
        return numbers

    yield make

    for number in reversed(created):
        execute_sql("DELETE FROM ref_stores WHERE store_number = :n", {"n": number})
