"""Weekly labor cost for one person — SPEC-PPL-001 REQ-003, AC-015…AC-017.

`cost_week` is a READ path, invoked by a mart, never by the nightly derive job
(PLAN §4). It answers one question: what did this person cost for this business
week, and can we trust the number.

The arithmetic at the centre of it is pure and lives at the top of this module,
deliberately separated from the query. The boundary cases that matter — 40.00
exactly, 40.01, hours summed across two stores — are the ones most worth
testing, and none of them should need a database to test.

Anchors: AC-015 (hours basis), AC-016 (overtime split), AC-017 (uncosted
shifts), CON-005 (the returned shape), INV-007 (an absent rate is None).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import structlog

from subway_ops.calendar import business_week_of
from subway_ops.config import OVERTIME_MULTIPLIER, OVERTIME_THRESHOLD_HOURS
from subway_ops.db.connection import execute_sql
from subway_ops.people.wages import rate_in_force

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class WeekCost:
    """One person's cost for one business week. CON-005.

    ``dollars`` is ``None`` — never ``Decimal("0")`` — whenever the figure
    cannot be trusted, and ``is_costed`` says the same thing in boolean form.
    The two always agree; they are separate fields because a caller aggregating
    across people needs the flag without unpacking the optional (AC-019's
    ``partially_costed`` count in T-0009).

    ``regular_hours`` and ``overtime_hours`` are reported even when
    ``is_costed`` is False. Hours we could observe are still real hours, and
    AC-021 requires an incomplete person's hours to keep appearing in
    hours-based metrics even though their dollars do not exist.
    """

    regular_hours: Decimal
    overtime_hours: Decimal
    dollars: Decimal | None
    is_costed: bool


def split_weekly_hours(total_hours: Decimal) -> tuple[Decimal, Decimal]:
    """Split summed weekly hours into (regular, overtime). AC-016. Pure.

    The split is on the person's SUMMED hours for the business week — not per
    shift and not per store. That is the whole reason this takes a single total
    rather than a list of shifts: someone who worked 25 hours at each of two
    stores is at 50 hours and owed 10 hours of premium, and no store-scoped
    view would ever produce that number.

    Exactly at the threshold is all regular. ``40`` is not "beyond 40", and the
    boundary is where this would be got wrong silently, so it is stated here
    and pinned by test rather than left to the reader of a ``>`` sign.
    """
    if total_hours <= OVERTIME_THRESHOLD_HOURS:
        return (total_hours, Decimal("0"))
    return (OVERTIME_THRESHOLD_HOURS, total_hours - OVERTIME_THRESHOLD_HOURS)


def cost_hours(regular_hours: Decimal, overtime_hours: Decimal, rate: Decimal) -> Decimal:
    """Dollars for a regular/overtime split at ``rate``. AC-016. Pure.

    No rounding and no quantization. ``hourly_rate`` is ``NUMERIC(12,4)`` and
    hours carry their own scale, so the product can land beyond four decimal
    places — and nothing in SPEC-PPL-001 or codex 02 names a rounding mode.
    Picking one here would be inventing a money rule, so the exact ``Decimal``
    comes out and whoever stores or displays it owns that decision. Exactness is
    also the safer default: rounding once at the edge beats rounding at every
    intermediate step.
    """
    return regular_hours * rate + overtime_hours * rate * OVERTIME_MULTIPLIER


def cost_week(employee_id: int, week_end: date) -> WeekCost:
    """Cost one person's business week. CON-005.

    ``week_end`` is any date inside the wanted week; ``business_week_of``
    resolves the Wed-Tue span (codex 01). Never ``timedelta(days=7)`` — the
    business week does not start on Monday and arithmetic that assumes it does
    is wrong for two days out of every seven.

    Hours come from ``stg_timeclock.hours_after_adj`` (AC-015, B-0016): the
    POS's own final word. 1,369 of 19,089 rows differ from ``hours_before_adj``,
    and each difference is already somebody's decision — discarding them would
    mean re-making 1,369 decisions by hand.

    Two conditions make the week uncosted, and both produce ``dollars=None``
    rather than a zero (CON-005, INV-007):

    * **No rate in force.** A person with no wage row costs nothing knowable,
      and ``Decimal("0")`` would flow into a mart and understate labor cost
      invisibly. That is INV-008's whole point: excluded and marked, never
      silently free.
    * **Any shift with NULL ``hours_after_adj``.** AC-017 treats that shift as
      uncosted; because its hours are unknown, the person's weekly total is
      unknown, and therefore so is whether they crossed 40. A partial figure
      here would be confidently wrong in the one place overtime is decided.

    The hours that WERE observed are still returned and still split, so an
    hours-based metric keeps working (AC-021) while the dollar figure abstains.
    """
    week_start, week_finish = business_week_of(week_end)

    rows = execute_sql(
        """
        SELECT COALESCE(SUM(t.hours_after_adj), 0) AS observed_hours,
               COUNT(*) FILTER (WHERE t.hours_after_adj IS NULL) AS null_shifts
          FROM stg_timeclock t
          JOIN ref_employee_assignments a
            ON a.store_number = t.restaurant_number
           AND a.clerk_id     = t.clerk_id
         WHERE a.employee_id    = :employee_id
           AND t.business_date >= :week_start
           AND t.business_date <= :week_finish
        """,
        {
            "employee_id": employee_id,
            "week_start": week_start,
            "week_finish": week_finish,
        },
    )

    observed_hours = Decimal(rows[0][0] or 0)
    null_shifts = int(rows[0][1] or 0)

    regular_hours, overtime_hours = split_weekly_hours(observed_hours)
    rate = rate_in_force(employee_id, week_finish)

    if rate is None or null_shifts:
        log.info(
            "week_not_costed",
            employee_id=employee_id,
            week_start=week_start.isoformat(),
            reason="no_rate_in_force" if rate is None else "null_hours_present",
            null_shifts=null_shifts,
        )
        return WeekCost(
            regular_hours=regular_hours,
            overtime_hours=overtime_hours,
            dollars=None,
            is_costed=False,
        )

    return WeekCost(
        regular_hours=regular_hours,
        overtime_hours=overtime_hours,
        dollars=cost_hours(regular_hours, overtime_hours, rate),
        is_costed=True,
    )
