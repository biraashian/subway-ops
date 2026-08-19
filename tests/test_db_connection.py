"""Tests for the database connection, migration runner, and job-run tracker.

The DB-touching tests skip when DATABASE_URL is unset so unit-test runs in
fresh environments stay green.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path

import pytest

from subway_ops.config import Settings, settings
from subway_ops.db.connection import execute_sql, reset_engine_for_tests
from subway_ops.db.job_runs import track_job
from subway_ops.db.migrate import MIGRATIONS_DIR, apply_migrations


def test_settings_loads_module_singleton() -> None:
    """Importing config never raises, even with empty credentials."""
    assert isinstance(settings, Settings)
    assert settings.app_env in {"dev", "prod"}


def test_settings_defaults_are_empty_strings() -> None:
    """Fresh-environment defaults: empty strings, app_env=dev."""
    fresh = Settings(_env_file=None)  # type: ignore[call-arg]
    assert fresh.database_url == ""
    assert fresh.freshconnect_api_client == ""
    assert fresh.freshconnect_api_key == ""
    assert fresh.app_env == "dev"


# ---------------------------------------------------------------------------
# DB integration tests
# ---------------------------------------------------------------------------


requires_db = pytest.mark.skipif(
    not settings.database_url,
    reason="DATABASE_URL not set; skipping DB integration tests",
)


@pytest.fixture
def fresh_engine() -> Iterator[None]:
    """Reset the cached engine so settings changes take effect within a test."""
    reset_engine_for_tests()
    yield
    reset_engine_for_tests()


@requires_db
def test_engine_select_one(fresh_engine: None) -> None:
    rows = execute_sql("SELECT 1 AS one")
    assert len(rows) == 1
    assert rows[0][0] == 1


@requires_db
def test_migrate_applies_then_is_noop(fresh_engine: None) -> None:
    apply_migrations()
    second_run = apply_migrations()
    assert second_run == []  # nothing new to apply the second time


@requires_db
def test_migrate_records_checksum(fresh_engine: None) -> None:
    apply_migrations()
    rows = execute_sql("SELECT filename, checksum FROM ops_migrations ORDER BY filename")
    by_name = {r[0]: r[1] for r in rows}

    for path in sorted(Path(MIGRATIONS_DIR).glob("*.sql")):
        expected = hashlib.sha256(path.read_bytes()).hexdigest()
        assert by_name[path.name] == expected


@requires_db
def test_migrate_rejects_modified_migration(fresh_engine: None) -> None:
    """If the on-disk checksum no longer matches what we recorded, abort."""
    apply_migrations()

    # Tamper with one row to simulate a hand-edited migration.
    execute_sql(
        "UPDATE ops_migrations SET checksum = :bogus WHERE filename = :fn",
        {"bogus": "0" * 64, "fn": "001_ref_tables.sql"},
    )

    with pytest.raises(RuntimeError, match="has changed since it was applied"):
        apply_migrations()

    # Restore so other tests see a clean ledger.
    real = hashlib.sha256(
        (Path(MIGRATIONS_DIR) / "001_ref_tables.sql").read_bytes()
    ).hexdigest()
    execute_sql(
        "UPDATE ops_migrations SET checksum = :real WHERE filename = :fn",
        {"real": real, "fn": "001_ref_tables.sql"},
    )


@requires_db
def test_track_job_records_success(fresh_engine: None) -> None:
    apply_migrations()

    with track_job("test_job_success") as meta:
        meta["rows_written"] = 7
        meta["note"] = "hello"

    rows = execute_sql(
        """
        SELECT status, rows_written, error_text, metadata
        FROM ops_job_runs
        WHERE job_name = 'test_job_success'
        ORDER BY id DESC LIMIT 1
        """
    )
    assert len(rows) == 1
    status, rows_written, error_text, metadata = rows[0]
    assert status == "success"
    assert rows_written == 7
    assert error_text is None
    assert metadata == {"note": "hello"}


@requires_db
def test_track_job_records_failure(fresh_engine: None) -> None:
    apply_migrations()

    with pytest.raises(ValueError, match="boom"), track_job("test_job_failure") as meta:
        meta["rows_written"] = 2
        raise ValueError("boom")

    rows = execute_sql(
        """
        SELECT status, rows_written, error_text
        FROM ops_job_runs
        WHERE job_name = 'test_job_failure'
        ORDER BY id DESC LIMIT 1
        """
    )
    assert len(rows) == 1
    status, rows_written, error_text = rows[0]
    assert status == "failed"
    assert rows_written == 2
    assert error_text is not None and "boom" in error_text
