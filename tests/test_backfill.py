"""Tests for the backfill orchestrator.

Window-planning math is pure and tested without a DB. The resume logic
exercises ``ops_backfill_progress`` against the live engine.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from scripts.backfill import (
    EndpointDef,
    _completed_windows,
    _record_completion,
    _run_endpoint,
    daily_windows,
    plan_windows,
    tuesdays_in_range,
)
from subway_ops.config import settings
from subway_ops.db.connection import execute_sql
from subway_ops.db.migrate import apply_migrations
from subway_ops.freshconnect.client import RateLimitError

# ---------------------------------------------------------------------------
# Pure window planning
# ---------------------------------------------------------------------------


def test_daily_windows_single_chunk() -> None:
    assert daily_windows(date(2026, 1, 1), date(2026, 1, 10), 50) == [
        (date(2026, 1, 1), date(2026, 1, 10))
    ]


def test_daily_windows_splits_at_max() -> None:
    # 60 days inclusive, max=50 → two windows (50 + 10).
    out = daily_windows(date(2026, 1, 1), date(2026, 3, 1), 50)
    assert len(out) == 2
    assert (out[0][1] - out[0][0]).days + 1 == 50
    # No gap between windows.
    assert out[1][0] == date(2026, 2, 20)


def test_daily_windows_rejects_inverted_range() -> None:
    with pytest.raises(ValueError, match="precedes"):
        daily_windows(date(2026, 2, 1), date(2026, 1, 1), 50)


def test_tuesdays_in_range_picks_only_tuesdays() -> None:
    # 2026-01-06 is the first Tuesday of 2026.
    out = tuesdays_in_range(date(2026, 1, 1), date(2026, 1, 31))
    assert out == [
        date(2026, 1, 6), date(2026, 1, 13), date(2026, 1, 20), date(2026, 1, 27),
    ]


def test_tuesdays_in_range_inclusive_when_start_is_tuesday() -> None:
    out = tuesdays_in_range(date(2026, 1, 6), date(2026, 1, 13))
    assert out == [date(2026, 1, 6), date(2026, 1, 13)]


def test_plan_windows_daily_endpoint() -> None:
    ep = EndpointDef("daily_sales", "daily", 50, ingest_daily=lambda _s, _e: 0)
    out = plan_windows(ep, date(2026, 1, 1), date(2026, 1, 10))
    assert out == [(date(2026, 1, 1), date(2026, 1, 10))]


def test_plan_windows_weekly_endpoint_returns_tuesday_pairs() -> None:
    ep = EndpointDef("controlsheet", "weekly", None, ingest_weekly=lambda _w: 0)
    out = plan_windows(ep, date(2026, 1, 1), date(2026, 1, 20))
    assert out == [
        (date(2026, 1, 6), date(2026, 1, 6)),
        (date(2026, 1, 13), date(2026, 1, 13)),
        (date(2026, 1, 20), date(2026, 1, 20)),
    ]


# ---------------------------------------------------------------------------
# _run_endpoint dispatch
# ---------------------------------------------------------------------------


def test_run_endpoint_calls_daily_ingest_per_window() -> None:
    calls: list[tuple[date, date]] = []

    def fake(s: date, e: date) -> int:
        calls.append((s, e))
        return 1

    ep = EndpointDef("daily_sales", "daily", 50, ingest_daily=fake)
    pending = [(date(2026, 1, 1), date(2026, 1, 5))]

    # _record_completion writes to the DB — patch it out so we don't need one.
    with patch("scripts.backfill._record_completion") as rc:
        n = _run_endpoint(ep, pending)
    assert n == 1
    assert calls == pending
    rc.assert_called_once_with("daily_sales", date(2026, 1, 1), date(2026, 1, 5))


def test_run_endpoint_calls_weekly_ingest_with_week_end() -> None:
    calls: list[date] = []

    def fake(w: date) -> int:
        calls.append(w)
        return 1

    ep = EndpointDef("wisr", "weekly", None, ingest_weekly=fake)
    pending = [(date(2026, 1, 6), date(2026, 1, 6))]
    with patch("scripts.backfill._record_completion"):
        n = _run_endpoint(ep, pending)
    assert n == 1
    assert calls == [date(2026, 1, 6)]


def test_run_endpoint_propagates_rate_limit() -> None:
    def fake(_s: date, _e: date) -> int:
        raise RateLimitError("test 429")

    ep = EndpointDef("daily_sales", "daily", 50, ingest_daily=fake)
    with patch("scripts.backfill._record_completion"), pytest.raises(RateLimitError):
        _run_endpoint(ep, [(date(2026, 1, 1), date(2026, 1, 5))])


# ---------------------------------------------------------------------------
# DB-backed checkpoint behaviour
# ---------------------------------------------------------------------------


requires_db = pytest.mark.skipif(
    not settings.database_url,
    reason="DB integration test: needs DATABASE_URL",
)


@pytest.fixture
def applied_migrations() -> None:
    apply_migrations()


@pytest.fixture
def clean_progress_for_test_endpoint(applied_migrations: None) -> Iterator[None]:
    name = "_bf_test"
    execute_sql(
        "DELETE FROM ops_backfill_progress WHERE endpoint = :ep", {"ep": name}
    )
    yield
    execute_sql(
        "DELETE FROM ops_backfill_progress WHERE endpoint = :ep", {"ep": name}
    )


@requires_db
def test_record_completion_and_lookup_round_trip(
    clean_progress_for_test_endpoint: None,
) -> None:
    name = "_bf_test"
    _record_completion(name, date(2026, 1, 1), date(2026, 1, 31))
    _record_completion(name, date(2026, 2, 1), date(2026, 2, 28))
    # Idempotent — second insert with same key is a no-op.
    _record_completion(name, date(2026, 1, 1), date(2026, 1, 31))

    done = _completed_windows(name)
    assert done == {
        (date(2026, 1, 1), date(2026, 1, 31)),
        (date(2026, 2, 1), date(2026, 2, 28)),
    }


@requires_db
def test_run_endpoint_skips_already_completed_windows(
    clean_progress_for_test_endpoint: None,
) -> None:
    """When the caller filters pending against _completed_windows, prior
    windows are skipped — only NEW ones invoke the ingest function."""
    name = "_bf_test"
    _record_completion(name, date(2026, 1, 1), date(2026, 1, 10))

    fake = MagicMock(return_value=1)
    ep = EndpointDef(name, "daily", 10, ingest_daily=fake)

    planned = [
        (date(2026, 1, 1), date(2026, 1, 10)),
        (date(2026, 1, 11), date(2026, 1, 20)),
    ]
    pending = [w for w in planned if w not in _completed_windows(name)]
    assert pending == [(date(2026, 1, 11), date(2026, 1, 20))]

    _run_endpoint(ep, pending)
    fake.assert_called_once_with(date(2026, 1, 11), date(2026, 1, 20))
    assert _completed_windows(name) == {
        (date(2026, 1, 1), date(2026, 1, 10)),
        (date(2026, 1, 11), date(2026, 1, 20)),
    }
