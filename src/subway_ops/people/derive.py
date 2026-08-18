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


def _display_for(observed_name: str, clerk_id: str) -> str:
    """The display name for a new person. AC-026 / AC-001a (D-044).

    A named pair goes through ``derive_display_name`` — `LAST, FIRST` becomes
    `First Last`, anything else passes through verbatim.

    A pair that has never carried a name gets ``Clerk <id> (unnamed)`` rather
    than an empty string. The empty string was the original behaviour and it was
    an invented default: `display_name` is NOT NULL, so `''` satisfies the
    column while being invisible on every roster screen, in T-0009's incomplete
    sweep and in T-0008's merge UI. A placeholder naming the PIN is something
    office can search for and rename; a blank is a row nobody knows to look at.
    """
    if observed_name.strip():
        return derive_display_name(observed_name)
    return f"Clerk {clerk_id} (unnamed)"


def _observed_pairs(
    session: Any, since: date | None, stores: list[str] | None
) -> list[dict[str, Any]]:
    """Every `(restaurant_number, clerk_id)` in the window, with its latest name.

    ``stores`` restricts the scan (D-042). ``None`` means every store, which is
    what a nightly run wants and what a test almost never does — this suite
    called it with no arguments 25 times and derived the real roster into
    production twice. A default meaning "everything" is not a mistake a caller
    makes only once.

    AC-001 says the assignment carries "the most recently seen **non-blank**
    `employee_name`" (D-044). The `WHERE` clause drops blank names before
    `DISTINCT ON` picks a winner, so one nameless punch cannot erase a name the
    pair has already shown. A pair that has NEVER carried a name returns no row
    here and is collected separately. `DISTINCT ON` ordered by `business_date DESC, clock_in
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
           AND (
                   CAST(:stores AS TEXT[]) IS NULL
                   OR t.restaurant_number = ANY(CAST(:stores AS TEXT[]))
               )
           AND COALESCE(BTRIM(t.employee_name), '') <> ''
         ORDER BY t.restaurant_number, t.clerk_id,
                  t.business_date DESC, t.clock_in DESC
    """
    rows = session.execute(text(sql), {"since": since, "stores": stores}).fetchall()
    named = [{"store_number": r[0], "clerk_id": r[1], "employee_name": r[2]} for r in rows]

    # AC-001a (D-044) — a pair whose every punch is nameless still worked, and
    # still needs an assignment. It produced no row above, so it is collected
    # here with an empty observed_name; ``_display_for`` turns that into
    # "Clerk <id> (unnamed)" rather than a blank nobody can see or search for.
    unnamed_sql = """
        SELECT DISTINCT t.restaurant_number, t.clerk_id
          FROM stg_timeclock t
         WHERE (
                   CAST(:since AS DATE) IS NULL
                   OR t.business_date >= CAST(:since AS DATE)
               )
           AND (
                   CAST(:stores AS TEXT[]) IS NULL
                   OR t.restaurant_number = ANY(CAST(:stores AS TEXT[]))
               )
         ORDER BY t.restaurant_number, t.clerk_id
    """
    every_pair = session.execute(text(unnamed_sql), {"since": since, "stores": stores}).fetchall()
    have = {(p["store_number"], p["clerk_id"]) for p in named}
    named.extend(
        {"store_number": r[0], "clerk_id": r[1], "employee_name": ""}
        for r in every_pair
        if (r[0], r[1]) not in have
    )
    named.sort(key=lambda p: (p["store_number"], p["clerk_id"]))
    return named


def derive_roster(*, since: date | None = None, stores: list[str] | None = None) -> DeriveResult:
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

    ``stores`` restricts the scan to the named stores (D-042, CON-001). Tests
    pass their synthetic stores; a nightly run passes nothing.

    **Two passes, not one (D-043).** Every AC-004 rename is applied first, and
    only then is any new assignment resolved to a person. With a single pass a
    name corrected at store A is invisible to a link at store B later in the
    same run, leaving two assignments carrying an identical
    `(clerk_id, normalized_name)` and pointing at two different people — a state
    the linking rule exists to prevent, permanent, and not repaired by
    re-running, because on the next run both assignments already exist and
    AC-003 leaves their links alone.
    """
    assignments_created = 0
    persons_created = 0
    # Every person this run saw clock in, new or existing. AC-024 acts on the
    # terminated ones at the end, in a single statement.
    seen_employee_ids: set[int] = set()

    with track_job(JOB_NAME) as meta, get_session() as session:
        pairs = _observed_pairs(session, since, stores)

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
                 ORDER BY assignment_id
                """
            )
        ).fetchall()

        by_pair = {(r[2], r[3]): r for r in existing}

        # ---- Pass 1 — AC-004 renames only. ------------------------------
        # Nothing is resolved here. Splitting the loop is D-043: a rename must
        # be visible to a link made later in the same run.
        unseen_pairs: list[dict[str, Any]] = []
        for pair in pairs:
            store_number = pair["store_number"]
            clerk_id = pair["clerk_id"]
            observed_name = pair["employee_name"]
            normalized = normalize_name(observed_name)

            found = by_pair.get((store_number, clerk_id))

            if found is None:
                unseen_pairs.append(pair)
                continue

            # AC-003 — the person link is left alone, always.
            # AC-004 — only observed_name (and its normalized form) move, and
            # display_name is not touched here at all, which is half of what
            # makes AC-028 hold.
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

        # ---- The identity index, built AFTER every rename (D-043). -------
        # Re-read rather than maintained incrementally: pass 1 may have moved
        # any number of normalized names, and rebuilding from the table inside
        # the same transaction is obviously correct where incremental
        # bookkeeping is merely probably correct.
        #
        # Empty normalized names are INCLUDED (D-044). The original skipped
        # them, which meant two nameless pairs sharing a clerk_id did not link
        # and AC-005 quietly did not hold uniformly. `setdefault` over an
        # `assignment_id`-ordered read makes the winner deterministic — the
        # oldest assignment wins, every run.
        by_identity: dict[tuple[str, str], int] = {}
        for r in session.execute(
            text(
                """
                SELECT employee_id, clerk_id, normalized_name
                  FROM ref_employee_assignments
                 ORDER BY assignment_id
                """
            )
        ).fetchall():
            by_identity.setdefault((r[1], r[2]), r[0])

        # ---- Pass 2 — resolution for pairs with no assignment yet. -------
        for pair in unseen_pairs:
            store_number = pair["store_number"]
            clerk_id = pair["clerk_id"]
            observed_name = pair["employee_name"]
            normalized = normalize_name(observed_name)

            # AC-005 first, AC-006 only on a miss.
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
                        {"display_name": _display_for(observed_name, clerk_id)},
                    ).scalar_one()
                )
                persons_created += 1
                # D-044 — registered whatever the normalized name is, empty
                # included, so two nameless pairs sharing a clerk_id link the
                # same way any other pair would.
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
