"""Roster derivation — SPEC-PPL-001 REQ-001, REQ-002.

19,089 timeclock rows land nightly and nobody is going to type in 250 people.
This is the job that makes the roster build itself (codex 06, 6.1A): it walks
`stg_timeclock`, creates an assignment for every `(restaurant_number, clerk_id)`
it has not seen, and decides which *person* each assignment belongs to.

The deciding is the hard part, and B-0014 settled it after measurement: link on
**exact `clerk_id` plus exact normalized name**, nothing looser. 56 of 250
clerk_ids carry more than one name; PIN `8` appears under five different names
at five stores. So this under-links on purpose — `singh, bir` and `bir` are one
human under PIN 1998 and will become two rows until office merges them.

The asymmetry is the whole argument, and it is worth restating at the top of the
module that implements it: **over-linking silently fuses two people's hours,
wages and certificates and nothing downstream detects it. Under-linking makes
two rows that office merges in seconds, with the merge recorded.**

Anchors: AC-001…AC-006 (derivation and resolution), AC-024 (a returning person
is the same row), AC-028 (an office-set display name survives), INV-001…INV-004,
CON-001.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import structlog
from sqlalchemy import text

from subway_ops.db.connection import get_session
from subway_ops.db.job_runs import track_job
from subway_ops.people.names import derive_display_name, normalize_name

log = structlog.get_logger(__name__)

JOB_NAME = "derive_roster"


@dataclass(frozen=True)
class DeriveResult:
    """What one derivation run did. CON-001.

    ``incomplete_opened`` is always 0 in this task. The completeness sweep that
    raises `employee_incomplete` worklist items is AC-018/AC-019 and belongs to
    T-0009; this task's FORBIDDEN_ACTIONS say so explicitly. The field exists
    here because CON-001 names it and T-0009 fills it, not because it is
    unimplemented by oversight.
    """

    assignments_created: int
    persons_created: int
    incomplete_opened: int


def _observed_pairs(session: Any, since: date | None) -> list[dict[str, Any]]:
    """Every `(restaurant_number, clerk_id)` in the window, with its latest name.

    AC-001 says the assignment carries "the **most recently seen**
    `employee_name`". `DISTINCT ON` ordered by `business_date DESC, clock_in
    DESC` is that, in one pass. `clock_in` is in the ordering deliberately:
    business_date alone leaves two punches on the same day tied, and which name
    won would then be whatever the planner happened to return. A person whose
    name was corrected at the terminal in March should be carried under the
    March spelling, not the January one, and on the same day the later punch
    wins.

    Ordered by the pair so a run is deterministic — two runs over the same rows
    do the same work in the same order, which matters when reading a job log
    beside a diff.
    """
    sql = """
        SELECT DISTINCT ON (t.restaurant_number, t.clerk_id)
               t.restaurant_number,
               t.clerk_id,
               t.employee_name
          FROM stg_timeclock t
         WHERE (
                   CAST(:since AS DATE) IS NULL
                   OR t.business_date >= CAST(:since AS DATE)
               )
         ORDER BY t.restaurant_number, t.clerk_id,
                  t.business_date DESC, t.clock_in DESC
    """
    rows = session.execute(text(sql), {"since": since}).fetchall()
    return [
        {
            "store_number": r[0],
            "clerk_id": r[1],
            "employee_name": r[2] or "",
        }
        for r in rows
    ]


def derive_roster(*, since: date | None = None) -> DeriveResult:
    """Build roster stubs from timeclock activity. CON-001, AC-001…AC-006.

    Wrapped in ``track_job("derive_roster")`` (AC-002) and run inside **one
    transaction**: a crash must not leave a `ref_employees` row with no
    assignment, which is a person nobody can reach and nothing will ever clean
    up.

    What this never does (INV-001): it does not delete or deactivate an
    assignment that is absent from the window. Absence means "did not work this
    period", not "gone". A cleanup that reads absence as departure would
    deactivate every seasonal worker every winter.

    What it never does (INV-004): it does not re-point an existing assignment at
    a different person. Once a link exists, only an explicit office merge or
    split (T-0008) changes it — so a name corrected at the terminal updates
    `observed_name` and nothing else (AC-004).
    """
    assignments_created = 0
    persons_created = 0
    # Every person this run saw clock in, new or existing. AC-024 acts on the
    # terminated ones at the end, in a single statement.
    seen_employee_ids: set[int] = set()

    with track_job(JOB_NAME) as meta, get_session() as session:
        pairs = _observed_pairs(session, since)

        # Existing assignments, keyed both ways: by the store/clerk pair (to
        # decide "have I seen this before") and by (clerk_id, normalized_name)
        # (AC-005's linking key). Loaded once rather than queried per pair —
        # 399 pairs against a few hundred assignments is a join, not a loop.
        existing = session.execute(
            text(
                """
                SELECT assignment_id, employee_id, store_number, clerk_id,
                       observed_name, normalized_name
                  FROM ref_employee_assignments
                """
            )
        ).fetchall()

        by_pair = {(r[2], r[3]): r for r in existing}
        by_identity: dict[tuple[str, str], int] = {}
        for r in existing:
            if r[5]:
                by_identity.setdefault((r[3], r[5]), r[1])

        for pair in pairs:
            store_number = pair["store_number"]
            clerk_id = pair["clerk_id"]
            observed_name = pair["employee_name"]
            normalized = normalize_name(observed_name)

            found = by_pair.get((store_number, clerk_id))

            if found is not None:
                # AC-003 — the person link is left alone, always.
                # AC-004 — only observed_name (and its normalized form) move,
                # and display_name is not touched here at all, which is half of
                # what makes AC-028 hold.
                seen_employee_ids.add(int(found[1]))
                if observed_name != found[4]:
                    session.execute(
                        text(
                            """
                            UPDATE ref_employee_assignments
                               SET observed_name   = :observed_name,
                                   normalized_name = :normalized_name
                             WHERE assignment_id = :assignment_id
                            """
                        ),
                        {
                            "observed_name": observed_name,
                            "normalized_name": normalized,
                            "assignment_id": found[0],
                        },
                    )
                    log.info(
                        "assignment_name_updated",
                        assignment_id=found[0],
                        store_number=store_number,
                        clerk_id=clerk_id,
                    )
                continue

            # A pair never seen before. AC-005 first, AC-006 only on a miss.
            employee_id = by_identity.get((clerk_id, normalized))

            if employee_id is None:
                # AC-006 — a new person. INSERT ... RETURNING rather than
                # upsert_rows, because ref_employees deliberately has no natural
                # key (PLAN §6, B-0014): no field or combination of fields
                # identifies a human in this data, so there is nothing to
                # upsert on.
                employee_id = int(
                    session.execute(
                        text(
                            """
                            INSERT INTO ref_employees (display_name)
                            VALUES (:display_name)
                            RETURNING employee_id
                            """
                        ),
                        {"display_name": derive_display_name(observed_name)},
                    ).scalar_one()
                )
                persons_created += 1
                if normalized:
                    by_identity[(clerk_id, normalized)] = employee_id
                log.info("person_created", employee_id=employee_id, clerk_id=clerk_id)

            seen_employee_ids.add(employee_id)
            session.execute(
                text(
                    """
                    INSERT INTO ref_employee_assignments
                        (employee_id, store_number, clerk_id,
                         observed_name, normalized_name)
                    VALUES (:employee_id, :store_number, :clerk_id,
                            :observed_name, :normalized_name)
                    """
                ),
                {
                    "employee_id": employee_id,
                    "store_number": store_number,
                    "clerk_id": clerk_id,
                    "observed_name": observed_name,
                    "normalized_name": normalized,
                },
            )
            assignments_created += 1

        # AC-024, D-041 — a returning person is the SAME row reactivated.
        #
        # One statement over everyone who clocked in, rather than a check per
        # person: the guard in the WHERE clause means an already-active person
        # is not written to at all, so this costs nothing on the overwhelmingly
        # common path where nobody has been terminated.
        #
        # `termination_date` is cleared as well as `is_active` set (D-041).
        # That is the inverse of AC-022 and keeps `termination_date IS NULL` a
        # truthful test for "currently employed" — the alternative ships a row
        # reading active alongside a termination date, which every consumer
        # filtering on the date misreads. The accepted cost, recorded in D-041:
        # the previous departure date is overwritten, and this table has no
        # history to recover it from.
        reactivated = 0
        if seen_employee_ids:
            reactivated = len(
                session.execute(
                    text(
                        """
                        UPDATE ref_employees
                           SET is_active        = true,
                               termination_date = NULL
                         WHERE employee_id = ANY(:employee_ids)
                           AND (is_active = false OR termination_date IS NOT NULL)
                        RETURNING employee_id
                        """
                    ),
                    {"employee_ids": sorted(seen_employee_ids)},
                ).fetchall()
            )
            if reactivated:
                log.info("persons_reactivated", count=reactivated)

        meta["rows_written"] = assignments_created  # AC-002
        meta["persons_reactivated"] = reactivated

    log.info(
        "derive_roster_complete",
        assignments_created=assignments_created,
        persons_created=persons_created,
    )
    return DeriveResult(
        assignments_created=assignments_created,
        persons_created=persons_created,
        incomplete_opened=0,
    )
