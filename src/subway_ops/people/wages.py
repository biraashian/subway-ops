"""Effective-dated wages — SPEC-PPL-001 REQ-003, AC-011…AC-014.

Wages exist in no upstream system (D-020). FreshConnect has none, and this is
the missing input that has left ``mart_store_weekly.labor_cost_pct`` NULL since
the column was written. Every row here was typed by a human, which is why
``set_by`` and ``set_at`` are not decoration.

Anchors: AC-011 (insert, never modify), AC-012 (the rate in force for a DATE),
AC-013 (office/owner only), AC-014 (positive rates only), CON-002, CON-003,
INV-005, INV-006, INV-007.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import structlog

from subway_ops.db.connection import execute_sql

log = structlog.get_logger(__name__)

#: Roles permitted to set a wage. INV-006 and AC-013. Not `ROLE_ORDER`-derived:
#: this is an explicit allow-list of two, and expressing it as "everything at or
#: above store_manager" would silently widen the moment the ladder changed.
WAGE_ROLES: frozenset[str] = frozenset({"office", "owner"})


def record_wage(
    *,
    employee_id: int,
    effective_date: date,
    hourly_rate: Decimal,
    set_by: str,
    actor_role: str,
) -> None:
    """Record a wage. INSERT only — AC-011, INV-005.

    **This function is the only thing standing between the system and a
    rewritten pay history**, and that is not rhetoric. The T-0004 audit
    demonstrated that a raw ``UPDATE ref_employee_wages SET hourly_rate = 99``
    succeeds against the live table. ``PRIMARY KEY (employee_id,
    effective_date)`` refuses a second ROW for the same date; it says nothing
    about mutating the row already sitting there. So INV-005 — "no UPDATE is
    ever issued" — is a property of this code and of nothing else.

    Accordingly there is no update path, no ``ON CONFLICT DO UPDATE``, and no
    ``force`` parameter. A correction is a new row on a new effective date. An
    attempt to re-record the same date raises rather than overwriting, because
    the alternative is that last month's labor cost quietly changes and no
    report that already went out can be reproduced.

    ``actor_role`` is checked before anything else (AC-013). It is passed in
    rather than read from session state so the guard sits at the library
    boundary and is testable without a request context — a view that forgets to
    check cannot get past this, and a background job has to say who it is acting
    as.

    Raises:
        PermissionError: ``actor_role`` is not ``office`` or ``owner``. The
            message names the role and the employee, and deliberately **never**
            the rate — AC-013's second clause says a refused request must not
            include the rate in any response body, and an exception message is
            a response body the moment it reaches a log or an API error.
        ValueError: ``hourly_rate`` is zero or negative (AC-014). The database
            CHECK enforces this too; it is checked here as well so the caller
            gets a clear Python error rather than an IntegrityError, and so the
            rule survives anyone testing this function against a stub.
    """
    if actor_role not in WAGE_ROLES:
        raise PermissionError(
            f"role {actor_role!r} may not set wages for employee {employee_id}; "
            f"wages are restricted to {sorted(WAGE_ROLES)}"
        )

    if hourly_rate <= 0:
        raise ValueError(
            f"hourly_rate must be positive, got {hourly_rate}; a missing or "
            "zero rate must be absent, never a rate of zero (INV-007)"
        )

    execute_sql(
        """
        INSERT INTO ref_employee_wages
            (employee_id, effective_date, hourly_rate, set_by)
        VALUES (:employee_id, :effective_date, :hourly_rate, :set_by)
        """,
        {
            "employee_id": employee_id,
            "effective_date": effective_date,
            "hourly_rate": hourly_rate,
            "set_by": set_by,
        },
    )
    log.info(
        "wage_recorded",
        employee_id=employee_id,
        effective_date=effective_date.isoformat(),
        set_by=set_by,
        actor_role=actor_role,
    )


def rate_in_force(employee_id: int, on: date) -> Decimal | None:
    """The rate in force on ``on`` — not the current rate. AC-012, CON-002.

    "The row with the greatest ``effective_date`` less than or equal to that
    date" (REQ-003). Costing a week in March must use March's rate even if a
    raise landed in June, or every historical report silently changes the next
    time somebody gets a raise.

    Returns ``None`` when no row is in force, **never** ``Decimal("0")``
    (INV-007). The distinction is the difference between "we do not know what
    this person is paid" and "this person is paid nothing", and a zero flows
    into a labor-cost mart and understates it invisibly. `None` forces the
    caller to decide, which is what INV-008 and AC-017 are for.

    Note what is NOT here: no ``actor_role`` guard. CON-002 specifies this
    signature exactly, and INV-006 ("a wage rate is readable only by office and
    owner") is therefore not enforced at this boundary — see the journal. Adding
    an unspecified parameter would be structure past the licensed shape.
    """
    rows = execute_sql(
        """
        SELECT hourly_rate
          FROM ref_employee_wages
         WHERE employee_id = :employee_id
           AND effective_date <= :on
         ORDER BY effective_date DESC
         LIMIT 1
        """,
        {"employee_id": employee_id, "on": on},
    )
    if not rows:
        return None
    return Decimal(rows[0][0])
