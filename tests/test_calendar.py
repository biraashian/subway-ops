"""Tests for subway_ops.calendar — business date and week primitives."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from subway_ops.calendar import (
    STORE_TZ,
    business_date_now,
    business_week_of,
    dt_to_business_date,
    is_business_week_end,
    previous_business_week,
)

# ---------------------------------------------------------------------------
# business_date_now / dt_to_business_date — wall-clock edge cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("hour", "minute", "expected_day"),
    [
        (0, 0, 15),  # midnight -> still yesterday
        (1, 30, 15),  # 01:30 -> still yesterday
        (1, 59, 15),  # 01:59 -> last second of yesterday
        (2, 0, 16),  # 02:00 -> new business day starts
        (2, 30, 16),
        (12, 0, 16),
        (23, 30, 16),
    ],
)
def test_business_date_now_at_clock_boundaries(hour: int, minute: int, expected_day: int) -> None:
    wall = datetime(2025, 4, 16, hour, minute, tzinfo=STORE_TZ)
    assert business_date_now(wall) == date(2025, 4, expected_day)


def test_business_date_now_with_no_argument_returns_a_date() -> None:
    # Branch coverage: now=None uses datetime.now(STORE_TZ). We only assert
    # the result is a date — the exact value depends on wall-clock time.
    result = business_date_now()
    assert isinstance(result, date)


def test_business_date_now_rejects_naive_datetime() -> None:
    naive = datetime(2025, 4, 16, 1, 30)
    with pytest.raises(ValueError, match="timezone-aware"):
        business_date_now(naive)


def test_dt_to_business_date_rejects_naive() -> None:
    naive = datetime(2025, 4, 16, 1, 30)
    with pytest.raises(ValueError, match="timezone-aware"):
        dt_to_business_date(naive)


def test_dt_to_business_date_converts_from_utc() -> None:
    # 2025-04-16 08:00 UTC = 01:00 PDT (still on 2025-04-15 business date).
    utc_dt = datetime(2025, 4, 16, 8, 0, tzinfo=UTC)
    assert dt_to_business_date(utc_dt) == date(2025, 4, 15)

    # 2025-04-16 10:00 UTC = 03:00 PDT (now on 2025-04-16 business date).
    utc_dt = datetime(2025, 4, 16, 10, 0, tzinfo=UTC)
    assert dt_to_business_date(utc_dt) == date(2025, 4, 16)


# ---------------------------------------------------------------------------
# business_week_of — every day of a Wed-Tue week resolves to the same tuple
# ---------------------------------------------------------------------------


def test_business_week_of_friday() -> None:
    assert business_week_of(date(2025, 4, 18)) == (
        date(2025, 4, 16),
        date(2025, 4, 22),
    )


def test_business_week_of_each_day_of_week_resolves_identically() -> None:
    wed = date(2025, 4, 16)
    tue = date(2025, 4, 22)
    for offset in range(7):
        d = wed + timedelta(days=offset)
        assert business_week_of(d) == (wed, tue), f"failed for {d} (weekday {d.weekday()})"


def test_business_week_of_wednesday_starts_new_week() -> None:
    # Tuesday Apr 22 is the end; Wednesday Apr 23 starts the next week.
    assert business_week_of(date(2025, 4, 22)) == (date(2025, 4, 16), date(2025, 4, 22))
    assert business_week_of(date(2025, 4, 23)) == (date(2025, 4, 23), date(2025, 4, 29))


# ---------------------------------------------------------------------------
# previous_business_week
# ---------------------------------------------------------------------------


def test_previous_business_week_on_wednesday() -> None:
    # Wed Apr 23 -> the week that just ended is Wed Apr 16 - Tue Apr 22.
    assert previous_business_week(date(2025, 4, 23)) == (
        date(2025, 4, 16),
        date(2025, 4, 22),
    )


def test_previous_business_week_on_tuesday_returns_week_before_this_one() -> None:
    # On Tue Apr 22 (last day of current week), the previous closed week is
    # the one before — Wed Apr 9 - Tue Apr 15.
    assert previous_business_week(date(2025, 4, 22)) == (
        date(2025, 4, 9),
        date(2025, 4, 15),
    )


def test_previous_business_week_stable_across_a_week() -> None:
    # Every day Wed Apr 23 through Tue Apr 29 should report the same previous
    # closed week: Wed Apr 16 - Tue Apr 22.
    expected = (date(2025, 4, 16), date(2025, 4, 22))
    for offset in range(7):
        d = date(2025, 4, 23) + timedelta(days=offset)
        assert previous_business_week(d) == expected, f"failed for {d}"


def test_previous_business_week_default_argument() -> None:
    # Branch coverage: today=None path. Just assert the result is a Wed-Tue
    # tuple — the exact value depends on wall-clock.
    start, end = previous_business_week()
    assert start.weekday() == 2  # Wednesday
    assert end.weekday() == 1  # Tuesday
    assert (end - start).days == 6


# ---------------------------------------------------------------------------
# is_business_week_end
# ---------------------------------------------------------------------------


def test_is_business_week_end_only_true_on_tuesday() -> None:
    wed = date(2025, 4, 16)
    assert is_business_week_end(wed + timedelta(days=6))  # Tuesday
    for offset in range(6):
        assert not is_business_week_end(wed + timedelta(days=offset))


# ---------------------------------------------------------------------------
# DST transitions
# ---------------------------------------------------------------------------


def test_spring_forward_business_date_jumps_at_skipped_two_am() -> None:
    """On 2025-03-09 the clock jumps from 01:59 PST to 03:00 PDT (02:00
    doesn't exist). The business date flips at the missing 02:00."""
    # 01:30 PST on Mar 9 — still on Mar 8 business date.
    pre = datetime(2025, 3, 9, 1, 30, tzinfo=STORE_TZ)
    assert business_date_now(pre) == date(2025, 3, 8)

    # 03:30 PDT on Mar 9 (post-jump) — now on Mar 9 business date.
    post = datetime(2025, 3, 9, 3, 30, tzinfo=STORE_TZ)
    assert business_date_now(post) == date(2025, 3, 9)


def test_fall_back_business_date_first_one_thirty_is_still_yesterday() -> None:
    """On 2025-11-02 the clock falls from 01:59 PDT back to 01:00 PST.
    01:30 occurs twice; both are before 02:00 wall-clock, so both should
    map to the prior business date (Nov 1)."""
    # 01:30 PDT, first occurrence (UTC-7).
    first = datetime(2025, 11, 2, 1, 30, tzinfo=STORE_TZ, fold=0)
    assert business_date_now(first) == date(2025, 11, 1)

    # 01:30 PST, second occurrence (UTC-8) — the disambiguated fold=1.
    second = datetime(2025, 11, 2, 1, 30, tzinfo=STORE_TZ, fold=1)
    assert business_date_now(second) == date(2025, 11, 1)


def test_fall_back_business_date_after_two_am_pst_is_new_day() -> None:
    """After the fall-back, 02:00 PST on Nov 2 starts the Nov 2 business
    day. 03:00 PST is solidly in Nov 2."""
    after = datetime(2025, 11, 2, 3, 0, tzinfo=STORE_TZ)
    assert business_date_now(after) == date(2025, 11, 2)
