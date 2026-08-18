"""Tests for weekly cost — SPEC-PPL-001 AC-015, AC-016, AC-017, CON-005.

The overtime boundary tests are PURE and need no database, which is the point of
factoring ``split_weekly_hours`` and ``cost_hours`` out of the query. The
DB-backed half exercises the join to ``stg_timeclock`` and the two uncosted
conditions.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from decimal import Decimal

import pytest

from subway_ops.calendar import business_date_now, business_week_of
from subway_ops.config import (
    OVERTIME_MULTIPLIER,
    OVERTIME_THRESHOLD_HOURS,
    settings,
)
from subway_ops.db.connection import execute_sql
from subway_ops.db.migrate import apply_migrations
from subway_ops.people.cost import WeekCost, cost_hours, cost_week, split_weekly_hours
from subway_ops.people.wages import record_wage

MARK = "t0007-cost-selftest"
CLERK_A = "t0007:clerk-a"
CLERK_B = "t0007:clerk-b"

requires_db = pytest.mark.skipif(
    not settings.database_url, reason="DB integration test: needs DATABASE_URL"
)


# ===========================================================================
#  PURE — the overtime arithmetic. No database.
# ===========================================================================


class TestSplitWeeklyHours:
    @pytest.mark.parametrize(
        ("total", "regular", "overtime"),
        [
            ("0", "0", "0"),
            ("39.99", "39.99", "0"),
            ("40", "40", "0"),
            ("40.01", "40", "0.01"),
            ("50", "40", "10"),
            ("168", "40", "128"),
        ],
    )
    def test_overtime_split_at_boundaries(self, total: str, regular: str, overtime: str) -> None:
        """AC-016 — 40.00 exactly is ALL regular; 40.01 is one cent of premium.

        The boundary is where this gets silently wrong. "Beyond 40" excludes 40
        itself, and a ``>=`` in place of ``>`` would pay a premium on an hour
        nobody is owed one for — on 250 people, every week, forever.
        """
        assert split_weekly_hours(Decimal(total)) == (
            Decimal(regular),
            Decimal(overtime),
        )

    def test_threshold_constant_is_forty(self) -> None:
        assert Decimal("40") == OVERTIME_THRESHOLD_HOURS

    def test_split_preserves_total_hours(self) -> None:
        """Nothing is lost or invented in the split, at any magnitude."""
        for total in ("0", "13.37", "40", "40.0001", "99.9999"):
            regular, overtime = split_weekly_hours(Decimal(total))
            assert regular + overtime == Decimal(total)


class TestCostHours:
    def test_overtime_uses_1_5_multiplier(self) -> None:
        """AC-016 / B-0017 — 1.5x beyond 40 is WA and OR statutory."""
        assert Decimal("1.5") == OVERTIME_MULTIPLIER
        # 40h regular + 10h overtime at $20: 800 + 10 * 30 = 1100
        assert cost_hours(Decimal("40"), Decimal("10"), Decimal("20")) == Decimal("1100")

    def test_no_overtime_is_plain_multiplication(self) -> None:
        assert cost_hours(Decimal("38.5"), Decimal("0"), Decimal("18.25")) == Decimal("702.625")

    def test_arithmetic_is_exact_and_unrounded(self) -> None:
        """No quantization: nothing in the spec names a rounding mode.

        A rate of 18.7777 over 40.5 hours does not land on a cent, and this
        returns the exact product rather than picking a rounding rule the spec
        never stated. Whoever stores or displays it owns that decision.
        """
        exact = cost_hours(Decimal("40"), Decimal("0.5"), Decimal("18.7777"))
        assert exact == Decimal("40") * Decimal("18.7777") + Decimal("0.5") * Decimal(
            "18.7777"
        ) * Decimal("1.5")

    def test_no_float_anywhere_in_the_money_path(self) -> None:
        """codex 02 — Decimal only. A float here would round in binary, silently."""
        result = cost_hours(Decimal("40"), Decimal("10"), Decimal("20"))
        assert isinstance(result, Decimal)
        assert not isinstance(result, float)


# ===========================================================================
#  DB-BACKED — the join, and the two uncosted conditions.
# ===========================================================================


def _wipe() -> None:
    execute_sql(
        "DELETE FROM stg_timeclock WHERE clerk_id IN (:a, :b)", {"a": CLERK_A, "b": CLERK_B}
    )
    execute_sql(
        "DELETE FROM ref_employee_wages WHERE employee_id IN "
        "(SELECT employee_id FROM ref_employees WHERE display_name = :m)",
        {"m": MARK},
    )
    execute_sql(
        "DELETE FROM ref_employee_assignments WHERE employee_id IN "
        "(SELECT employee_id FROM ref_employees WHERE display_name = :m)",
        {"m": MARK},
    )
    execute_sql("DELETE FROM ref_employees WHERE display_name = :m", {"m": MARK})


@pytest.fixture
def worker() -> Iterator[tuple[int, list[str]]]:
    """A person with assignments at up to two real stores, and a clean slate."""
    apply_migrations()
    _wipe()
    stores = [
        str(r[0])
        for r in execute_sql("SELECT store_number FROM ref_stores ORDER BY store_number LIMIT 2")
    ]
    rows = execute_sql(
        "INSERT INTO ref_employees (display_name) VALUES (:m) RETURNING employee_id",
        {"m": MARK},
    )
    employee_id = int(rows[0][0])
    for store, clerk in zip(stores, (CLERK_A, CLERK_B), strict=False):
        execute_sql(
            "INSERT INTO ref_employee_assignments "
            "(employee_id, store_number, clerk_id) VALUES (:e, :s, :c)",
            {"e": employee_id, "s": store, "c": clerk},
        )
    yield employee_id, stores
    _wipe()


def _punch(
    store: str, clerk: str, business_date: object, after_adj: str | None, before_adj: str = "8.00"
) -> None:
    """One timeclock row. ``after_adj=None`` is the AC-017 case."""
    execute_sql(
        """
        INSERT INTO stg_timeclock
            (restaurant_number, clerk_id, clock_in, business_date,
             hours_before_adj, hours_after_adj)
        VALUES (:s, :c, :ci, :bd, :before, :after)
        """,
        {
            "s": store,
            "c": clerk,
            "ci": f"{business_date} 09:00:00",
            "bd": business_date,
            "before": Decimal(before_adj),
            "after": None if after_adj is None else Decimal(after_adj),
        },
    )


@requires_db
def test_cost_uses_hours_after_adj(worker: tuple[int, list[str]]) -> None:
    """AC-015 / B-0016 — the POS's final word, not the raw figure.

    The two columns differ on 1,369 of 19,089 real rows. This punch says 8.00
    before adjustment and 6.00 after; costing must produce 6 hours of pay.
    """
    employee_id, stores = worker
    week_start, _ = business_week_of(business_date_now())
    _punch(stores[0], CLERK_A, week_start, after_adj="6.00", before_adj="8.00")
    record_wage(
        employee_id=employee_id,
        effective_date=week_start - timedelta(days=1),
        hourly_rate=Decimal("10.0000"),
        set_by=MARK,
        actor_role="office",
    )

    result = cost_week(employee_id, week_start)
    assert result.regular_hours == Decimal("6.00")
    assert result.dollars == Decimal("60.0000"), "6h x $10 — not 8h"
    assert result.is_costed is True


@requires_db
def test_hours_sum_across_assignments_before_overtime(
    worker: tuple[int, list[str]],
) -> None:
    """AC-016 — 25h at one store plus 25h at another is 50h and 10h of premium.

    This is the case no store-scoped view can ever see, and the reason
    ``split_weekly_hours`` takes a person's summed total rather than a shift.
    """
    employee_id, stores = worker
    if len(stores) < 2:
        pytest.skip("needs two stores")
    week_start, _ = business_week_of(business_date_now())
    _punch(stores[0], CLERK_A, week_start, after_adj="25.00")
    _punch(stores[1], CLERK_B, week_start + timedelta(days=1), after_adj="25.00")
    record_wage(
        employee_id=employee_id,
        effective_date=week_start - timedelta(days=1),
        hourly_rate=Decimal("20.0000"),
        set_by=MARK,
        actor_role="office",
    )

    result = cost_week(employee_id, week_start)
    assert result.regular_hours == Decimal("40")
    assert result.overtime_hours == Decimal("10")
    assert result.dollars == Decimal("1100.0000")


@requires_db
def test_null_hours_marks_aggregate_partially_costed(
    worker: tuple[int, list[str]],
) -> None:
    """AC-017 / CON-005 — one NULL shift and dollars is None, never a partial number.

    Because the NULL shift's hours are unknown, the person's weekly total is
    unknown, and so is whether they crossed 40. A confident-looking figure here
    would be wrong in the one place overtime is decided. The hours that WERE
    observed are still returned, so hours-based metrics keep working (AC-021).
    """
    employee_id, stores = worker
    week_start, _ = business_week_of(business_date_now())
    _punch(stores[0], CLERK_A, week_start, after_adj="30.00")
    _punch(stores[0], CLERK_A, week_start + timedelta(days=1), after_adj=None)
    record_wage(
        employee_id=employee_id,
        effective_date=week_start - timedelta(days=1),
        hourly_rate=Decimal("20.0000"),
        set_by=MARK,
        actor_role="office",
    )

    result = cost_week(employee_id, week_start)
    assert result.is_costed is False
    assert result.dollars is None
    assert result.dollars != Decimal("0")
    assert result.regular_hours == Decimal("30.00"), "observed hours still reported"


@requires_db
def test_missing_rate_returns_dollars_none_not_zero(
    worker: tuple[int, list[str]],
) -> None:
    """INV-007 / INV-008 — no wage on file means unknown, not free.

    A ``Decimal("0")`` here flows into a labor-cost mart and understates it
    invisibly, which is the exact failure INV-008 exists to prevent.
    """
    employee_id, stores = worker
    week_start, _ = business_week_of(business_date_now())
    _punch(stores[0], CLERK_A, week_start, after_adj="20.00")

    result = cost_week(employee_id, week_start)
    assert result.dollars is None
    assert result.dollars != Decimal("0")
    assert result.is_costed is False
    assert result.regular_hours == Decimal("20.00")


@requires_db
def test_rate_is_resolved_for_the_week_not_today(
    worker: tuple[int, list[str]],
) -> None:
    """AC-012 inside costing — a later raise must not re-price an old week."""
    employee_id, stores = worker
    old_week_day = business_date_now() - timedelta(days=60)
    old_week_start, _ = business_week_of(old_week_day)
    _punch(stores[0], CLERK_A, old_week_start, after_adj="10.00")
    record_wage(
        employee_id=employee_id,
        effective_date=old_week_start - timedelta(days=1),
        hourly_rate=Decimal("15.0000"),
        set_by=MARK,
        actor_role="office",
    )
    record_wage(
        employee_id=employee_id,
        effective_date=business_date_now(),
        hourly_rate=Decimal("30.0000"),
        set_by=MARK,
        actor_role="office",
    )

    result = cost_week(employee_id, old_week_start)
    assert result.dollars == Decimal("150.0000"), "10h at the OLD rate of $15"


@requires_db
def test_shifts_outside_the_business_week_are_excluded(
    worker: tuple[int, list[str]],
) -> None:
    """codex 01 — the week is Wed-Tue, resolved by business_week_of.

    A punch the day before the week starts must not be counted. This is what
    ``timedelta(days=7)`` arithmetic gets wrong for two days out of seven.
    """
    employee_id, stores = worker
    week_start, week_finish = business_week_of(business_date_now())
    _punch(stores[0], CLERK_A, week_start - timedelta(days=1), after_adj="8.00")
    _punch(stores[0], CLERK_A, week_start, after_adj="5.00")
    _punch(stores[0], CLERK_A, week_finish + timedelta(days=1), after_adj="8.00")
    record_wage(
        employee_id=employee_id,
        effective_date=week_start - timedelta(days=10),
        hourly_rate=Decimal("10.0000"),
        set_by=MARK,
        actor_role="office",
    )

    result = cost_week(employee_id, week_start)
    assert result.regular_hours == Decimal("5.00"), "only the in-week punch counts"


@requires_db
def test_a_week_with_no_shifts_costs_zero_when_a_rate_exists(
    worker: tuple[int, list[str]],
) -> None:
    """No hours worked is a known zero — distinct from an unknown."""
    employee_id, _ = worker
    week_start, _ = business_week_of(business_date_now())
    record_wage(
        employee_id=employee_id,
        effective_date=week_start - timedelta(days=1),
        hourly_rate=Decimal("20.0000"),
        set_by=MARK,
        actor_role="office",
    )

    result = cost_week(employee_id, week_start)
    assert result.is_costed is True
    assert result.dollars == Decimal("0")


@requires_db
def test_week_cost_is_frozen(worker: tuple[int, list[str]]) -> None:
    """CON-005 — a frozen dataclass; a mart must not mutate a costing result."""
    employee_id, _ = worker
    result = cost_week(employee_id, business_date_now())
    assert isinstance(result, WeekCost)
    with pytest.raises(Exception, match=r"frozen|immutable|cannot assign"):
        result.dollars = Decimal("1")  # type: ignore[misc]
