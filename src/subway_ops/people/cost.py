"""Weekly labor cost for one person — SPEC-PPL-001 REQ-003, AC-015…AC-017.

`cost_week` is a READ path, invoked by a mart, never by the nightly derive job
(PLAN §4). It answers one question: what did this person cost for this business
week, and can we trust the number.

The arithmetic at the centre of it is pure and lives at the top of this module,
deliberately separated from the query. The boundary cases that matter — 40.00
exactly, 40.01, hours summed across two stores — are the ones most worth
testing, and none of them should need a database to test.

Anchors: AC-012a (per-shift rate resolution), AC-015 (hours basis), AC-016
(overtime split), AC-017 (uncosted shifts), CON-005 (the returned shape),
INV-007 (an absent rate is None).
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


def allocate_overtime(
    shift_hours: list[Decimal],
) -> list[tuple[Decimal, Decimal]]:
    """Split each shift's hours into (regular, overtime), chronologically. Pure.

    ``shift_hours`` must already be ordered by ``clock_in``. Returns one
    (regular, overtime) pair per shift, in the same order.

    **Why per shift rather than one weekly split (D-036).** Each shift may be
    priced at a different rate now, so it is no longer enough to know that 10 of
    50 hours were overtime — we have to know *which* 10. Q-007 answers that and
    was decided long before this arose: the overtime hours are "the hours after
    the 40th, wherever worked, ordered by ``clock_in``". This walks the week in
    that order and lets the 40-hour line fall wherever it falls, including
    through the middle of a single shift.

    Only Q-007's ORDERING is used here. Its attribution of the premium to a
    particular store stays fenced out by NG-007, and ``cost_week`` still returns
    a per-person weekly figure.
    """
    allocation: list[tuple[Decimal, Decimal]] = []
    running = Decimal("0")
    for hours in shift_hours:
        remaining_regular = OVERTIME_THRESHOLD_HOURS - running
        regular = Decimal("0") if remaining_regular <= 0 else min(hours, remaining_regular)
        allocation.append((regular, hours - regular))
        running += hours
    return allocation


def cost_week(employee_id: int, week_end: date) -> WeekCost:
    """Cost one person's business week. CON-005, AC-012a.

    ``week_end`` is any date inside the wanted week; ``business_week_of``
    resolves the Wed-Tue span (codex 01). Never ``timedelta(days=7)`` — the
    business week does not start on Monday and arithmetic that assumes it does
    is wrong for two days out of every seven.

    Hours come from ``stg_timeclock.hours_after_adj`` (AC-015, B-0016): the
    POS's own final word. 1,369 of 19,089 rows differ from ``hours_before_adj``,
    and each difference is already somebody's decision.

    **Each shift is priced at the rate in force on its own ``business_date``**
    (AC-012a, D-036). Pricing the whole week at one date's rate was the defect
    this replaced: a raise landing mid-week paid every hour before it at the new
    rate, overstating the week by 50% on a measured probe while ``is_costed``
    stayed True. A rate is resolved once per distinct business date in the week
    — at most seven lookups — rather than once per shift, since two shifts on
    the same day cannot have different rates.

    Two conditions make the week uncosted, both producing ``dollars=None``
    rather than a zero (CON-005, INV-007):

    * **Any shift with no rate in force.** Under per-shift pricing this is now
      per shift rather than per week: a person hired mid-week has no rate for
      the days before they were hired, and a partial figure would understate
      the week rather than admit it does not know.
    * **Any shift with NULL ``hours_after_adj``.** AC-017 treats that shift as
      uncosted; because its hours are unknown, so is the weekly total, and so is
      where the 40-hour line falls for every other shift.

    The hours that WERE observed are still returned and still split, so an
    hours-based metric keeps working (AC-021) while the dollar figure abstains.
    """
    week_start, week_finish = business_week_of(week_end)

    shifts = execute_sql(
        """
        SELECT t.business_date, t.hours_after_adj
          FROM stg_timeclock t
          JOIN ref_employee_assignments a
            ON a.store_number = t.restaurant_number
           AND a.clerk_id     = t.clerk_id
         WHERE a.employee_id    = :employee_id
           AND t.business_date >= :week_start
           AND t.business_date <= :week_finish
         ORDER BY t.clock_in, t.business_date
        """,
        {
            "employee_id": employee_id,
            "week_start": week_start,
            "week_finish": week_finish,
        },
    )

    null_shifts = sum(1 for row in shifts if row[1] is None)
    hours = [Decimal(row[1]) for row in shifts if row[1] is not None]
    allocation = allocate_overtime(hours)
    regular_hours = sum((r for r, _ in allocation), Decimal("0"))
    overtime_hours = sum((o for _, o in allocation), Decimal("0"))

    def _uncosted(reason: str) -> WeekCost:
        log.info(
            "week_not_costed",
            employee_id=employee_id,
            week_start=week_start.isoformat(),
            reason=reason,
            null_shifts=null_shifts,
        )
        return WeekCost(
            regular_hours=regular_hours,
            overtime_hours=overtime_hours,
            dollars=None,
            is_costed=False,
        )

    if null_shifts:
        return _uncosted("null_hours_present")

    # One lookup per distinct business date, not per shift.
    rates: dict[date, Decimal | None] = {}
    for row in shifts:
        business_date = row[0]
        if business_date not in rates:
            rates[business_date] = rate_in_force(employee_id, business_date)

    if any(rate is None for rate in rates.values()):
        return _uncosted("no_rate_in_force")

    dollars = Decimal("0")
    dated = [row[0] for row in shifts]
    for business_date, (regular, overtime) in zip(dated, allocation, strict=True):
        rate = rates[business_date]
        assert rate is not None  # guarded immediately above
        dollars += cost_hours(regular, overtime, rate)

    return WeekCost(
        regular_hours=regular_hours,
        overtime_hours=overtime_hours,
        dollars=dollars,
        is_costed=True,
    )
