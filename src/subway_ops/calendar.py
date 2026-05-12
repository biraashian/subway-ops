"""Business calendar helpers.

Subway's business day is 02:00 -> 01:59 local. Its business week runs
Wednesday -> Tuesday. Every date and week calculation in the system goes
through this module so the rules live in exactly one place.

Stdlib only by design (no `dateutil`, no `pytz`).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

STORE_TZ = ZoneInfo("America/Los_Angeles")

# Wall-clock offset from midnight that splits one business date from the next.
_BUSINESS_DAY_CUTOFF = timedelta(hours=2)

# Python's weekday() uses Mon=0..Sun=6. Wednesday=2, Tuesday=1.
_WEDNESDAY = 2
_TUESDAY = 1


def business_date_now(now: datetime | None = None) -> date:
    """Return the current Subway business date.

    Subway's business day runs 02:00 -> 01:59 local. At 01:30 wall-clock on
    2025-04-16, the business date is still 2025-04-15.

    If ``now`` is provided (for testing), it must be timezone-aware.

    Example:
        >>> from datetime import datetime
        >>> business_date_now(datetime(2025, 4, 16, 1, 30, tzinfo=STORE_TZ))
        datetime.date(2025, 4, 15)
    """
    if now is None:
        now = datetime.now(STORE_TZ)
    elif now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return dt_to_business_date(now)


def dt_to_business_date(dt: datetime) -> date:
    """Convert a timezone-aware timestamp to its Subway business date.

    The timestamp is converted into store-local time, then shifted back by
    two hours so that 00:00-01:59 falls on the prior business date.

    Example:
        >>> from datetime import datetime
        >>> dt_to_business_date(datetime(2025, 4, 16, 1, 30, tzinfo=STORE_TZ))
        datetime.date(2025, 4, 15)
        >>> dt_to_business_date(datetime(2025, 4, 16, 2, 30, tzinfo=STORE_TZ))
        datetime.date(2025, 4, 16)
    """
    if dt.tzinfo is None:
        raise ValueError("dt must be timezone-aware")
    local = dt.astimezone(STORE_TZ)
    return (local - _BUSINESS_DAY_CUTOFF).date()


def business_week_of(d: date) -> tuple[date, date]:
    """Return (wednesday_start, tuesday_end) of the Wed-Tue business week
    containing the given business date.

    Example:
        >>> business_week_of(date(2025, 4, 18))  # a Friday
        (datetime.date(2025, 4, 16), datetime.date(2025, 4, 22))
    """
    days_since_wed = (d.weekday() - _WEDNESDAY) % 7
    wed_start = d - timedelta(days=days_since_wed)
    tue_end = wed_start + timedelta(days=6)
    return (wed_start, tue_end)


def previous_business_week(today: date | None = None) -> tuple[date, date]:
    """Return the most recently closed business week as of ``today``.

    On a Wednesday, the week that just ended yesterday (Tuesday) is the
    previous closed week. On any other day, the previous closed week is the
    one whose Tuesday is the most recent Tuesday strictly before this week's
    Wednesday.

    Example:
        >>> previous_business_week(date(2025, 4, 23))  # a Wednesday
        (datetime.date(2025, 4, 16), datetime.date(2025, 4, 22))
        >>> previous_business_week(date(2025, 4, 22))  # a Tuesday
        (datetime.date(2025, 4, 9), datetime.date(2025, 4, 15))
    """
    if today is None:
        today = business_date_now()
    this_wed_start, _ = business_week_of(today)
    prev_tue_end = this_wed_start - timedelta(days=1)
    prev_wed_start = prev_tue_end - timedelta(days=6)
    return (prev_wed_start, prev_tue_end)


def is_business_week_end(d: date) -> bool:
    """True if ``d`` is a Tuesday (end of a Subway business week).

    Example:
        >>> is_business_week_end(date(2025, 4, 22))  # Tuesday
        True
        >>> is_business_week_end(date(2025, 4, 23))  # Wednesday
        False
    """
    return d.weekday() == _TUESDAY
