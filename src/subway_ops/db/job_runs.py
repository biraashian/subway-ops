"""Per-job-run audit trail for scheduled work.

Every ingest, mart refresh, digest send, etc. wraps itself in
`track_job("job_name")` so we have a row in `ops_job_runs` for each invocation:
when it started, when it finished, whether it succeeded, how many rows it
wrote, and the error text on failure.

Typical use:

    with track_job("ingest_daily_sales") as meta:
        rows = do_the_thing()
        meta["rows_written"] = rows
        meta["start_date"] = "2026-05-01"
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from subway_ops.db.connection import get_engine


def start_job(name: str) -> int:
    """Insert a `running` row for this job and return its primary key."""
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text(
                """
                INSERT INTO ops_job_runs (job_name, started_at, status)
                VALUES (:name, :started_at, 'running')
                RETURNING id
                """
            ),
            {"name": name, "started_at": datetime.now(UTC)},
        )
        row = result.one()
    return int(row[0])


def finish_job(
    job_id: int,
    status: str,
    rows_written: int | None = None,
    error: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Mark a previously-started job as `success` or `failed`."""
    if status not in {"success", "failed"}:
        raise ValueError(f"finish_job status must be 'success' or 'failed', got {status!r}")

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE ops_job_runs
                SET finished_at  = :finished_at,
                    status       = :status,
                    rows_written = :rows_written,
                    error_text   = :error_text,
                    metadata     = CAST(:metadata AS JSONB)
                WHERE id = :id
                """
            ),
            {
                "id": job_id,
                "finished_at": datetime.now(UTC),
                "status": status,
                "rows_written": rows_written,
                "error_text": error,
                "metadata": json.dumps(metadata) if metadata else None,
            },
        )


@contextmanager
def track_job(name: str) -> Iterator[dict[str, Any]]:
    """Context manager that records start/finish for a job.

    Yields a mutable dict the caller can populate; `rows_written` (int) is
    pulled out and stored in its own column, everything else lands in the
    `metadata` JSONB column.

    On exception, the row is marked `failed` with `error_text` set to the
    exception's string form and the exception is re-raised.
    """
    job_id = start_job(name)
    meta: dict[str, Any] = {}
    try:
        yield meta
    except Exception as exc:
        finish_job(
            job_id,
            status="failed",
            rows_written=_pop_rows_written(meta),
            error=f"{type(exc).__name__}: {exc}",
            metadata=meta or None,
        )
        raise
    else:
        finish_job(
            job_id,
            status="success",
            rows_written=_pop_rows_written(meta),
            metadata=meta or None,
        )


def _pop_rows_written(meta: dict[str, Any]) -> int | None:
    value = meta.pop("rows_written", None)
    if value is None:
        return None
    return int(value)
