"""Tests for the daily orchestrator.

The DB-touching parts (track_job, settings-driven ingests) are deliberately
out of scope here — ``run_daily_pull`` is a pure dispatcher that we exercise
with mocked ingest callables. The shape and ordering of calls is what
matters.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from scripts.daily_pull import WEDNESDAY, run_daily_pull

DAILY_INGEST_NAMES = (
    "daily_sales",
    "paidouts",
    "inventory_movement",
    "timeclock",
    "third_party_daily",
)
WEEKLY_INGEST_NAMES = ("controlsheet", "wisr")


def _spy() -> tuple[Callable[..., int], list[tuple[date, ...]]]:
    calls: list[tuple[date, ...]] = []

    def fn(*args: date) -> int:
        calls.append(args)
        return 1

    return fn, calls


def _build_mock_ingests() -> tuple[
    dict[str, dict[str, Callable[..., int]]],
    dict[str, list[tuple[date, ...]]],
]:
    daily: dict[str, Callable[..., int]] = {}
    weekly: dict[str, Callable[..., int]] = {}
    log: dict[str, list[tuple[date, ...]]] = {}
    for name in DAILY_INGEST_NAMES:
        fn, calls = _spy()
        daily[name] = fn
        log[name] = calls
    for name in WEEKLY_INGEST_NAMES:
        fn, calls = _spy()
        weekly[name] = fn
        log[name] = calls
    return ({"daily": daily, "weekly": weekly}, log)


def test_non_wednesday_runs_only_daily_ingests() -> None:
    # Thursday — weekly ingests should NOT fire.
    today = date(2026, 5, 7)
    assert today.weekday() != WEDNESDAY

    mocks, log = _build_mock_ingests()
    result = run_daily_pull(
        today=today,
        daily_ingests=mocks["daily"],
        weekly_ingests=mocks["weekly"],
    )

    yesterday = date(2026, 5, 6)
    for name in DAILY_INGEST_NAMES:
        assert log[name] == [(yesterday, yesterday)], name
    for name in WEEKLY_INGEST_NAMES:
        assert log[name] == []

    assert result["is_wednesday"] is False
    assert result["total_rows"] == 5
    assert result["per_ingest_rows"]["daily_sales"] == 1


def test_wednesday_runs_daily_and_weekly_ingests() -> None:
    today = date(2026, 5, 13)  # a Wednesday
    assert today.weekday() == WEDNESDAY

    mocks, log = _build_mock_ingests()
    result = run_daily_pull(
        today=today,
        daily_ingests=mocks["daily"],
        weekly_ingests=mocks["weekly"],
    )

    yesterday = date(2026, 5, 12)
    last_week_end = date(2026, 5, 12)  # the just-closed Tuesday

    for name in DAILY_INGEST_NAMES:
        assert log[name] == [(yesterday, yesterday)], name
    for name in WEEKLY_INGEST_NAMES:
        assert log[name] == [(last_week_end,)], name

    assert result["is_wednesday"] is True
    assert result["total_rows"] == 7


def test_total_rows_sums_per_ingest_counts() -> None:
    """Distinct return values from each ingest sum into total_rows."""
    today = date(2026, 5, 13)  # Wednesday — exercises all 7 ingests

    return_values = iter([10, 20, 30, 40, 50, 60, 70])

    def make(_value_iter: object) -> Callable[..., int]:
        def fn(*_a: date) -> int:
            return next(return_values)
        return fn

    daily = {n: make(None) for n in DAILY_INGEST_NAMES}
    weekly = {n: make(None) for n in WEEKLY_INGEST_NAMES}

    result = run_daily_pull(today=today, daily_ingests=daily, weekly_ingests=weekly)
    assert result["total_rows"] == sum([10, 20, 30, 40, 50, 60, 70])
