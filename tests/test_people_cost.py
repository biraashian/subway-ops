"""Tests for weekly cost — SPEC-PPL-001 AC-015, AC-016, AC-017, CON-005.

The overtime boundary tests are PURE and need no database, which is the point of
factoring ``allocate_overtime`` and ``cost_hours`` out of the query. The
DB-backed half exercises the join to ``stg_timeclock``, the two uncosted
conditions, and the per-shift rate resolution D-036 requires.
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
from subway_ops.people.cost import (
    WeekCost,
    allocate_overtime,
    cost_hours,
    cost_week,
)
from subway_ops.people.wages import record_wage
from tests.conftest import ns

MARK = ns("t0007-cost-selftest")
CLERK_A = ns("t0007:clerk-a")
CLERK_B = ns("t0007:clerk-b")
#: Synthetic stores, created and dropped by the fixture (D-039, codex 13).
#: `is_active=false` is the second half of the rule and not decoration: an active
#: store is one the ingests pick up, so a crashed run would leave this one in
#: their path as well as in the database.
STORE_A = ns("T-PPL-1")
STORE_B = ns("T-PPL-2")


def _weekly_split(total: Decimal) -> tuple[Decimal, Decimal]:
    """Weekly regular/overtime totals for a single-shift week.

    D-036 replaced the one-rate-per-week split with a per-shift chronological
    allocation, so the weekly totals are now a SUM over shifts rather than a
    function of the total. This keeps the boundary cases expressed as weekly
    figures, which is how AC-016 states them.
    """
    allocation = allocate_overtime([total])
    return (
        sum((r for r, _ in allocation), Decimal("0")),
        sum((o for _, o in allocation), Decimal("0")),
    )


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
        assert _weekly_split(Decimal(total)) == (
            Decimal(regular),
            Decimal(overtime),
        )

    def test_threshold_constant_is_forty(self) -> None:
        assert Decimal("40") == OVERTIME_THRESHOLD_HOURS

    def test_split_preserves_total_hours(self) -> None:
        """Nothing is lost or invented in the split, at any magnitude."""
        for total in ("0", "13.37", "40", "40.0001", "99.9999"):
            regular, overtime = _weekly_split(Decimal(total))
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
    execute_sql(
        "DELETE FROM ref_stores WHERE store_number IN (:a, :b)",
        {"a": STORE_A, "b": STORE_B},
    )


@pytest.fixture
def worker() -> Iterator[tuple[int, list[str]]]:
    """A person assigned to two SYNTHETIC stores, and a clean slate.

    The stores are created here rather than read out of `ref_stores` (D-039).
    codex 13 says never to point a test at a real store number, and these tests
    write `stg_timeclock` punches — up to 35 hours inside the current business
    week — which is precisely the hazard the convention was written after.
    Teardown removes them, and `is_active=false` means the ingests would ignore
    them even if a crashed run left one behind.
    """
    apply_migrations()
    _wipe()
    for store in (STORE_A, STORE_B):
        execute_sql(
            """
            INSERT INTO ref_stores (store_number, store_name, city, state, is_active)
            VALUES (:n, :n, 'Testville', 'WA', false)
            ON CONFLICT (store_number) DO NOTHING
            """,
            {"n": store},
        )
    stores = [STORE_A, STORE_B]
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


# ===========================================================================
#  D-036 — per-shift rates, and the chronological 40-hour line
# ===========================================================================


class TestAllocateOvertime:
    """Pure. Which shifts carry the premium — Q-007's clock_in ordering."""

    def test_the_line_can_fall_through_the_middle_of_a_shift(self) -> None:
        allocation = allocate_overtime([Decimal("20"), Decimal("25"), Decimal("10")])
        assert allocation == [
            (Decimal("20"), Decimal("0")),
            (Decimal("20"), Decimal("5")),
            (Decimal("0"), Decimal("10")),
        ]

    def test_exactly_forty_leaves_the_next_shift_wholly_overtime(self) -> None:
        assert allocate_overtime([Decimal("40"), Decimal("5")]) == [
            (Decimal("40"), Decimal("0")),
            (Decimal("0"), Decimal("5")),
        ]

    def test_under_forty_is_all_regular(self) -> None:
        assert allocate_overtime([Decimal("10"), Decimal("29.99")]) == [
            (Decimal("10"), Decimal("0")),
            (Decimal("29.99"), Decimal("0")),
        ]

    def test_allocation_preserves_every_hour(self) -> None:
        shifts = [Decimal("13.5"), Decimal("9"), Decimal("22.25"), Decimal("8")]
        allocation = allocate_overtime(shifts)
        assert sum(r + o for r, o in allocation) == sum(shifts)
        assert sum(r for r, _ in allocation) == Decimal("40")

    def test_order_matters_and_that_is_the_point(self) -> None:
        """Reversing the week moves which shift carries the premium.

        Under one weekly rate this was invisible. Under D-036 each shift may be
        priced differently, so the ORDER decides which rate the premium
        multiplies — which is exactly why Q-007's clock_in ordering had to be
        the answer rather than something chosen here.
        """
        forward = allocate_overtime([Decimal("35"), Decimal("15")])
        backward = allocate_overtime([Decimal("15"), Decimal("35")])
        assert forward == [(Decimal("35"), Decimal("0")), (Decimal("5"), Decimal("10"))]
        assert backward == [(Decimal("15"), Decimal("0")), (Decimal("25"), Decimal("10"))]


@requires_db
def test_midweek_raise_prices_each_shift_at_its_own_rate(
    worker: tuple[int, list[str]],
) -> None:
    """AC-012a / D-036 — the defect this rework exists to fix.

    10h before a mid-week raise at $10 and 10h after at $30 is $400. The old
    code resolved one rate at week_finish and returned $600 — every pre-raise
    hour paid at the post-raise rate, a 50% overstatement, with is_costed True.
    """
    employee_id, stores = worker
    week_start, _ = business_week_of(business_date_now())
    raise_day = week_start + timedelta(days=3)

    _punch(stores[0], CLERK_A, week_start, after_adj="10.00")
    _punch(stores[0], CLERK_A, raise_day, after_adj="10.00")

    record_wage(
        employee_id=employee_id,
        effective_date=week_start - timedelta(days=1),
        hourly_rate=Decimal("10.0000"),
        set_by=MARK,
        actor_role="office",
    )
    record_wage(
        employee_id=employee_id,
        effective_date=raise_day,
        hourly_rate=Decimal("30.0000"),
        set_by=MARK,
        actor_role="office",
    )

    result = cost_week(employee_id, week_start)
    assert result.is_costed is True
    assert result.dollars == Decimal("400.0000"), "10h x $10 + 10h x $30"
    assert result.dollars != Decimal("600.0000"), "the pre-rework answer"


@requires_db
def test_midweek_cut_is_not_backdated_either(worker: tuple[int, list[str]]) -> None:
    """The mirror case — a rate CUT must not re-price the hours before it.

    Pinned separately because the two failure directions are not symmetric in
    consequence: an overstatement inflates labor cost and gets noticed, an
    understatement quietly flatters the store's numbers.
    """
    employee_id, stores = worker
    week_start, _ = business_week_of(business_date_now())
    cut_day = week_start + timedelta(days=3)

    _punch(stores[0], CLERK_A, week_start, after_adj="10.00")
    _punch(stores[0], CLERK_A, cut_day, after_adj="10.00")

    record_wage(
        employee_id=employee_id,
        effective_date=week_start - timedelta(days=1),
        hourly_rate=Decimal("30.0000"),
        set_by=MARK,
        actor_role="office",
    )
    record_wage(
        employee_id=employee_id,
        effective_date=cut_day,
        hourly_rate=Decimal("10.0000"),
        set_by=MARK,
        actor_role="office",
    )

    result = cost_week(employee_id, week_start)
    assert result.dollars == Decimal("400.0000"), "10h x $30 + 10h x $10"


@requires_db
def test_a_shift_with_no_rate_in_force_makes_the_week_uncosted(
    worker: tuple[int, list[str]],
) -> None:
    """Per-shift pricing makes this per shift — e.g. someone hired mid-week.

    The first shift predates every wage row, so its rate is unknown. A partial
    dollar figure would understate the week rather than admit it cannot say.
    """
    employee_id, stores = worker
    week_start, _ = business_week_of(business_date_now())
    hire_day = week_start + timedelta(days=2)

    _punch(stores[0], CLERK_A, week_start, after_adj="8.00")
    _punch(stores[0], CLERK_A, hire_day, after_adj="8.00")
    record_wage(
        employee_id=employee_id,
        effective_date=hire_day,
        hourly_rate=Decimal("20.0000"),
        set_by=MARK,
        actor_role="office",
    )

    result = cost_week(employee_id, week_start)
    assert result.is_costed is False
    assert result.dollars is None
    assert result.regular_hours == Decimal("16.00"), "hours still reported (AC-021)"


@requires_db
def test_overtime_premium_uses_the_rate_of_the_shift_that_crossed_forty(
    worker: tuple[int, list[str]],
) -> None:
    """D-036 + Q-007 together — the premium follows the shift, not the week.

    35h at $10, then 15h at $20 after a raise. The 40-hour line falls 5h into
    the second shift: 35h + 5h regular, 10h overtime, all of the overtime at the
    NEW rate because those hours were worked after the raise.
        35*10 + 5*20 + 10*20*1.5 = 350 + 100 + 300 = 750
    """
    employee_id, stores = worker
    week_start, _ = business_week_of(business_date_now())
    raise_day = week_start + timedelta(days=2)

    _punch(stores[0], CLERK_A, week_start, after_adj="35.00")
    _punch(stores[0], CLERK_A, raise_day, after_adj="15.00")
    record_wage(
        employee_id=employee_id,
        effective_date=week_start - timedelta(days=1),
        hourly_rate=Decimal("10.0000"),
        set_by=MARK,
        actor_role="office",
    )
    record_wage(
        employee_id=employee_id,
        effective_date=raise_day,
        hourly_rate=Decimal("20.0000"),
        set_by=MARK,
        actor_role="office",
    )

    result = cost_week(employee_id, week_start)
    assert result.regular_hours == Decimal("40.00")
    assert result.overtime_hours == Decimal("10.00")
    assert result.dollars == Decimal("750.0000")


# ===========================================================================
#  D-038 — an empty week still has to know the rate
# ===========================================================================


@requires_db
def test_empty_week_with_no_wage_row_is_not_costed(worker: tuple[int, list[str]]) -> None:
    """D-038 / CON-005 — no shifts AND no wage row means we cannot claim to know.

    Deliberately constructed so the two candidate answers DIFFER. The previous
    version of this test recorded a wage first, which made `$0 costed` and
    `None uncosted` indistinguishable — the same blind spot D-036 recorded about
    `test_rate_is_resolved_for_the_week_not_today`. Here no wage row exists at
    all, so ratifying the old behaviour would fail this and the new behaviour
    passes it.

    The $0 the old code returned was arithmetically true — zero hours cost zero
    at any rate. It was `is_costed=True` that was the lie.
    """
    employee_id, _ = worker
    week_start, _ = business_week_of(business_date_now())

    result = cost_week(employee_id, week_start)
    assert result.regular_hours == Decimal("0")
    assert result.is_costed is False, "is_costed asserts the rate is KNOWN"
    assert result.dollars is None
    assert result.dollars != Decimal("0"), "the pre-rework answer"


@requires_db
def test_empty_week_with_a_wage_row_costs_zero(worker: tuple[int, list[str]]) -> None:
    """The other side of D-038 — a known rate and no hours is a real, costed $0."""
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
def test_a_nonexistent_employee_is_not_costed() -> None:
    """The case that made the old behaviour indefensible.

    `employee_id 999999999` is not in `ref_employees`. It has no shifts and no
    wage row, so under the old code it answered `dollars=Decimal("0")`,
    `is_costed=True` — a confident price for a person who does not exist.

    No fixture: this must hold with nothing set up, which is the point.
    """
    result = cost_week(999999999, business_date_now())
    assert result.is_costed is False
    assert result.dollars is None


# ===========================================================================
#  D-039 — the fixture's stores are synthetic
# ===========================================================================


@requires_db
def test_cost_fixtures_use_a_synthetic_store(worker: tuple[int, list[str]]) -> None:
    """codex 13 / D-039 — never point a test at a real store number.

    These tests write `stg_timeclock` punches, so a crashed run would otherwise
    leave phantom hours on a live store inside the open business week — the
    exact incident codex 13 was written after. Both halves are asserted: the
    stores are ours, and they are inactive so no ingest would touch them even if
    teardown never ran.
    """
    _, stores = worker
    assert stores == [STORE_A, STORE_B]

    rows = execute_sql(
        "SELECT store_number, is_active FROM ref_stores "
        "WHERE store_number IN (:a, :b) ORDER BY store_number",
        {"a": STORE_A, "b": STORE_B},
    )
    assert len(rows) == 2
    assert all(row[1] is False for row in rows), "is_active=false, or ingests pick it up"

    real = execute_sql(
        "SELECT count(*) FROM ref_stores WHERE store_number IN (:a, :b) AND is_active",
        {"a": STORE_A, "b": STORE_B},
    )
    assert real[0][0] == 0
