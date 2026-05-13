"""Tests for the rolling mart refresh orchestrator.

The script is a thin dispatcher — we exercise its logic with mocked
``refresh_*`` callables. No DB needed.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta

from scripts.refresh_marts import (
    DAILY_LOOKBACK_DAYS,
    WEEKLY_LOOKBACK_WEEKS,
    _recent_week_ends,
    run_refresh,
)


def _spy() -> tuple[Callable[..., int], list[tuple[tuple[object, ...], dict[str, object]]]]:
    log: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fn(*args: object, **kwargs: object) -> int:
        log.append((args, kwargs))
        return 1

    return fn, log


def test_recent_week_ends_returns_two_consecutive_tuesdays() -> None:
    # 2026-05-13 is a Wednesday → previous closed week ends 2026-05-12 (Tue).
    out = _recent_week_ends(date(2026, 5, 13), 2)
    assert out == [date(2026, 5, 12), date(2026, 5, 5)]


def test_recent_week_ends_on_a_tuesday_uses_prior_tuesday() -> None:
    # On a Tuesday the previous CLOSED week ends a week ago.
    out = _recent_week_ends(date(2026, 5, 12), 2)
    assert out == [date(2026, 5, 5), date(2026, 4, 28)]


def test_run_refresh_calls_daily_with_14_day_window() -> None:
    daily, daily_log = _spy()
    weekly, _ = _spy()
    fm, _ = _spy()

    today = date(2026, 5, 13)
    run_refresh(today=today, refresh_daily=daily, refresh_weekly=weekly, refresh_fm=fm)

    assert len(daily_log) == 1
    _, kwargs = daily_log[0]
    assert kwargs["end"] == today
    assert kwargs["start"] == today - timedelta(days=DAILY_LOOKBACK_DAYS)


def test_run_refresh_calls_weekly_and_fm_for_each_recent_week() -> None:
    daily, _ = _spy()
    weekly, weekly_log = _spy()
    fm, fm_log = _spy()

    today = date(2026, 5, 13)
    run_refresh(today=today, refresh_daily=daily, refresh_weekly=weekly, refresh_fm=fm)

    expected_week_ends = _recent_week_ends(today, WEEKLY_LOOKBACK_WEEKS)
    weekly_args = [call[0][0] for call in weekly_log]
    fm_args = [call[0][0] for call in fm_log]
    assert weekly_args == expected_week_ends
    assert fm_args == expected_week_ends


def test_run_refresh_returns_per_mart_counts() -> None:
    daily, _ = _spy()
    weekly, _ = _spy()
    fm, _ = _spy()

    result = run_refresh(
        today=date(2026, 5, 13),
        refresh_daily=daily,
        refresh_weekly=weekly,
        refresh_fm=fm,
    )
    # Each spy returns 1 per call. Two weekly + two FM + one daily.
    assert result == {
        "mart_store_daily": 1,
        "mart_store_weekly": 2,
        "mart_field_manager_portfolio": 2,
    }
