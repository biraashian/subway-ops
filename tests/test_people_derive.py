"""Tests for roster derivation — SPEC-PPL-001 AC-001…AC-006, AC-028.

Two of these encode decisions rather than code, and a regression in either is
silent and expensive:

* ``test_same_pin_different_name_is_two_persons`` is B-0014's answer. If it
  breaks, two unrelated humans are fused into one record and their hours, wages
  and certificates merge, with no downstream signal at all.
* ``test_rerun_creates_no_new_rows`` is INV-002. This job runs nightly forever;
  a non-idempotent version grows the roster without bound.

Stores are synthetic and seeded ``is_active=false`` (D-039, codex 13) so the
ingests cannot pick them up and no real store is ever written to.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest

from subway_ops.calendar import business_date_now
from subway_ops.config import settings
from subway_ops.db.connection import execute_sql
from subway_ops.db.migrate import apply_migrations
from subway_ops.people import derive as derive_module
from subway_ops.people.derive import DeriveResult, derive_roster
from tests.conftest import ns

STORE_A = ns("T-PPL-A")
STORE_B = ns("T-PPL-B")
#: D-042 — every call in this file is scoped to these. Passing nothing means
#: "every store in stg_timeclock", and this suite previously did that 25 times,
#: deriving the real roster into production. The parameter exists so a caller
#: can say what it meant; this constant is the file saying it once.
STORES = [STORE_A, STORE_B]
CLERK = ns("t0006:pin-1998")
CLERK_OTHER = ns("t0006:pin-8")
MARK_PREFIX = ns("t0006:")
requires_db = pytest.mark.skipif(
    not settings.database_url, reason="DB integration test: needs DATABASE_URL"
)


def _wipe() -> None:
    """Remove everything these tests create, persons included.

    The persons must be found through their assignments, not by name: this
    module's people are created BY the derivation, so their `display_name` is
    whatever `derive_display_name` produced ("Bir Singh") and carries no test
    marker at all. An earlier version of this filtered on a marker in the name,
    matched nothing, and left persons behind — so the next test found them via
    the `(clerk_id, normalized_name)` index and reported `persons_created == 0`.
    A teardown that silently deletes nothing is worse than none, because the
    suite still passes in isolation.
    """
    stores = {"a": STORE_A, "b": STORE_B}
    employee_ids = [
        r[0]
        for r in execute_sql(
            "SELECT DISTINCT employee_id FROM ref_employee_assignments "
            "WHERE store_number IN (:a, :b)",
            stores,
        )
    ]
    execute_sql("DELETE FROM stg_timeclock WHERE restaurant_number IN (:a, :b)", stores)
    execute_sql("DELETE FROM ref_employee_assignments WHERE store_number IN (:a, :b)", stores)
    for employee_id in employee_ids:
        execute_sql(
            "DELETE FROM ref_employees WHERE employee_id = :e AND employee_id NOT IN "
            "(SELECT employee_id FROM ref_employee_assignments)",
            {"e": employee_id},
        )
    execute_sql("DELETE FROM ref_stores WHERE store_number IN (:a, :b)", stores)


@pytest.fixture
def synthetic_stores() -> Iterator[None]:
    """Two stores that do not exist in the business. D-039, codex 13.

    ``is_active=false`` is the second half of the convention: an active
    synthetic store would be picked up by the ingests.
    """
    apply_migrations()
    _wipe()
    for store in (STORE_A, STORE_B):
        execute_sql(
            """
            INSERT INTO ref_stores
                (store_number, store_name, city, state, is_active)
            VALUES (:n, :n, 'Testville', 'WA', false)
            """,
            {"n": store},
        )
    yield
    _wipe()


def _punch(store: str, clerk: str, name: str, days_ago: int = 0, hour: int = 9) -> None:
    """One timeclock punch.

    ``hour`` exists because `stg_timeclock`'s primary key is
    `(restaurant_number, clerk_id, clock_in)` — two punches for the same person,
    same store, same day need different clock-in times, which is also true of
    real split shifts.
    """
    business_date = business_date_now() - timedelta(days=days_ago)
    execute_sql(
        """
        INSERT INTO stg_timeclock
            (restaurant_number, clerk_id, clock_in, business_date,
             employee_name, hours_before_adj, hours_after_adj)
        VALUES (:s, :c, :ci, :bd, :n, 8.00, 8.00)
        """,
        {
            "s": store,
            "c": clerk,
            "ci": f"{business_date} {hour:02d}:00:00",
            "bd": business_date,
            "n": name,
        },
    )


def _assignments(store: str | None = None) -> list[Any]:
    sql = (
        "SELECT assignment_id, employee_id, store_number, clerk_id, "
        "observed_name, normalized_name FROM ref_employee_assignments "
        "WHERE store_number IN (:a, :b)"
    )
    params: dict[str, Any] = {"a": STORE_A, "b": STORE_B}
    if store:
        sql += " AND store_number = :s"
        params["s"] = store
    return list(execute_sql(sql + " ORDER BY assignment_id", params))


# --- AC-001, AC-002 — the assignment, and the job record -------------------


@requires_db
def test_new_pair_creates_assignment(synthetic_stores: None) -> None:
    """AC-001 — one assignment, carrying the most recently seen name."""
    _punch(STORE_A, CLERK, "singh, bir")
    result = derive_roster(stores=STORES)

    assert isinstance(result, DeriveResult)
    assert result.assignments_created == 1
    rows = _assignments()
    assert len(rows) == 1
    assert rows[0][2] == STORE_A
    assert rows[0][3] == CLERK
    assert rows[0][4] == "singh, bir"
    assert rows[0][5] == "singh, bir"


@requires_db
def test_assignment_carries_the_most_recent_name(synthetic_stores: None) -> None:
    """AC-001 — "most recently seen", not the first or an arbitrary one.

    A name corrected at the terminal in March must not be overridden by the
    January spelling just because January sorts first.
    """
    _punch(STORE_A, CLERK, "sigh, bir", days_ago=30)
    _punch(STORE_A, CLERK, "singh, bir", days_ago=1)
    derive_roster(stores=STORES)
    assert _assignments()[0][4] == "singh, bir"


@requires_db
def test_derive_wraps_in_track_job_and_sets_rows_written(
    synthetic_stores: None,
) -> None:
    """AC-002 — the run is recorded, with rows_written populated."""
    _punch(STORE_A, CLERK, "singh, bir")
    _punch(STORE_B, CLERK_OTHER, "flores, maria")
    derive_roster(stores=STORES)

    rows = execute_sql(
        "SELECT status, rows_written FROM ops_job_runs "
        "WHERE job_name = 'derive_roster' ORDER BY started_at DESC LIMIT 1"
    )
    assert rows, "no ops_job_runs row for derive_roster"
    assert rows[0][0] == "success"
    assert rows[0][1] == 2


# --- AC-003, AC-004 — an existing pair -------------------------------------


@requires_db
def test_existing_assignment_keeps_its_person_link(synthetic_stores: None) -> None:
    """AC-003 / INV-004 — a link changes only by office merge or split."""
    _punch(STORE_A, CLERK, "singh, bir")
    derive_roster(stores=STORES)
    original = _assignments()[0][1]

    _punch(STORE_A, CLERK, "singh, bir", hour=17)
    derive_roster(stores=STORES)
    assert _assignments()[0][1] == original


@requires_db
def test_changed_observed_name_updates_assignment_only(
    synthetic_stores: None,
) -> None:
    """AC-004 — observed_name moves; the person's display_name does not.

    The terminal is where names get retyped. A person's display name is a
    separate fact, and AC-028 protects it once office has set it.
    """
    _punch(STORE_A, CLERK, "sigh, bir", days_ago=1)
    derive_roster(stores=STORES)
    employee_id = _assignments()[0][1]
    before = execute_sql(
        "SELECT display_name FROM ref_employees WHERE employee_id = :e",
        {"e": employee_id},
    )[0][0]

    _punch(STORE_A, CLERK, "singh, bir")
    derive_roster(stores=STORES)

    row = _assignments()[0]
    assert row[4] == "singh, bir", "observed_name updated"
    assert row[5] == "singh, bir", "normalized_name updated with it"
    after = execute_sql(
        "SELECT display_name FROM ref_employees WHERE employee_id = :e",
        {"e": employee_id},
    )[0][0]
    assert after == before, "display_name must not move"


@requires_db
def test_explicit_display_name_survives_rederivation(
    synthetic_stores: None,
) -> None:
    """AC-028 — office types the right thing once and it stays.

    B-0018 paired automatic derivation with a human override precisely because
    the derivation is predictably wrong for some names. An override the nightly
    job silently reverted would make the pairing worthless.
    """
    _punch(STORE_A, CLERK, "singh, bir", days_ago=1)
    derive_roster(stores=STORES)
    employee_id = _assignments()[0][1]

    execute_sql(
        "UPDATE ref_employees SET display_name = :n, display_name_is_manual = true "
        "WHERE employee_id = :e",
        {"n": "Bir Singh (Kitchen)", "e": employee_id},
    )

    _punch(STORE_A, CLERK, "SINGH, BIRINDER")
    derive_roster(stores=STORES)

    assert (
        execute_sql(
            "SELECT display_name FROM ref_employees WHERE employee_id = :e",
            {"e": employee_id},
        )[0][0]
        == "Bir Singh (Kitchen)"
    )


# --- INV-002 — idempotency -------------------------------------------------


@requires_db
def test_rerun_creates_no_new_rows(synthetic_stores: None) -> None:
    """INV-002 — the guarantee that lets this run nightly forever.

    A non-idempotent derivation adds a row per night per person, and the roster
    grows without bound while every count downstream inflates with it.
    """
    _punch(STORE_A, CLERK, "singh, bir")
    _punch(STORE_B, CLERK_OTHER, "flores, maria")
    first = derive_roster(stores=STORES)
    assert (first.assignments_created, first.persons_created) == (2, 2)

    second = derive_roster(stores=STORES)
    assert (second.assignments_created, second.persons_created) == (0, 0)
    assert len(_assignments()) == 2


@requires_db
def test_absence_from_a_run_deactivates_nothing(synthetic_stores: None) -> None:
    """INV-001 — absence means "did not work", not "gone".

    A derivation that read absence as departure would deactivate every seasonal
    worker every winter.
    """
    _punch(STORE_A, CLERK, "singh, bir", days_ago=30)
    derive_roster(stores=STORES)

    derive_roster(since=business_date_now(), stores=STORES)  # a window with no punches at all

    rows = execute_sql(
        "SELECT is_active FROM ref_employee_assignments WHERE store_number = :s",
        {"s": STORE_A},
    )
    assert rows[0][0] is True


# --- AC-005, AC-006 — B-0014's linking rule --------------------------------


@requires_db
def test_same_pin_same_name_two_stores_is_one_person(
    synthetic_stores: None,
) -> None:
    """AC-005 — one human, two store assignments (codex 06, 6.2A)."""
    _punch(STORE_A, CLERK, "singh, bir")
    _punch(STORE_B, CLERK, "singh, bir")
    result = derive_roster(stores=STORES)

    assert result.assignments_created == 2
    assert result.persons_created == 1
    rows = _assignments()
    assert rows[0][1] == rows[1][1], "both assignments point at one person"


@requires_db
def test_same_pin_different_name_is_two_persons(synthetic_stores: None) -> None:
    """AC-006 — B-0014's answer, and the most expensive test to lose.

    PIN 8 appears under five different names at five stores. If matching ever
    loosens to clerk_id alone, five unrelated people become one record and
    their hours, wages and certificates merge with no downstream signal.
    """
    _punch(STORE_A, CLERK_OTHER, "flores, maria")
    _punch(STORE_B, CLERK_OTHER, "redwan, shah")
    result = derive_roster(stores=STORES)

    assert result.persons_created == 2
    rows = _assignments()
    assert rows[0][1] != rows[1][1], "different names must NOT be fused"


@requires_db
def test_under_linking_is_accepted_not_repaired(synthetic_stores: None) -> None:
    """The stated cost of B-0014 — `singh, bir` and `bir` stay apart.

    Same PIN, same human, two rows. This test asserts the system does NOT do
    the clever thing, on the exact data where the clever thing is right.
    """
    _punch(STORE_A, CLERK, "singh, bir")
    _punch(STORE_B, CLERK, "bir")
    result = derive_roster(stores=STORES)

    assert result.persons_created == 2
    rows = _assignments()
    assert rows[0][1] != rows[1][1]


@requires_db
def test_name_matching_ignores_case_and_whitespace(synthetic_stores: None) -> None:
    """Exact means exact AFTER normalization — the three noise differences only."""
    _punch(STORE_A, CLERK, "singh, bir")
    _punch(STORE_B, CLERK, "  SINGH,   BIR ")
    result = derive_roster(stores=STORES)

    assert result.persons_created == 1
    rows = _assignments()
    assert rows[0][1] == rows[1][1]


# --- D-042 / D-043 / D-044 — the rework -----------------------------------


@requires_db
def test_derive_scoped_to_stores_touches_nothing_else(synthetic_stores: None) -> None:
    """D-042 / CON-001 — `stores` means only those stores.

    This test FAILS if `stores` is ignored: `stg_timeclock` carries 19,339 real
    punches across 13 real stores, so an unscoped run creates several hundred
    assignments and the count assertion below misses by two orders of magnitude.
    That is not hypothetical — it is what this suite did before D-042, twice.
    """
    _punch(STORE_A, CLERK, "singh, bir")
    result = derive_roster(stores=STORES)

    assert result.assignments_created == 1
    assert (
        execute_sql(
            "SELECT count(*) FROM ref_employee_assignments WHERE store_number NOT LIKE 'T-%'"
        )[0][0]
        == 0
    ), "D-042 — a scoped run must not create a single real-store assignment"


@requires_db
def test_rename_earlier_in_the_run_is_visible_to_a_later_link(
    synthetic_stores: None,
) -> None:
    """D-043 / AC-005 — two passes, renames before resolution.

    Store A holds `singh, b` for PIN 1998. In ONE run the terminal corrects it
    to `singh, bir` AND the same PIN first appears at store B already spelled
    `singh, bir`.

    Under a run-start snapshot the index still says `singh, b`, store B misses,
    and a second person is created — leaving two assignments with an identical
    `(clerk_id, normalized_name)` pointing at two people. That state is
    permanent: on the next run both assignments exist and AC-003 leaves their
    links alone. This test fails under that reading and passes under D-043's.
    """
    _punch(STORE_A, CLERK, "singh, b", days_ago=30)
    derive_roster(stores=STORES)
    person = _assignments()[0][1]

    _punch(STORE_A, CLERK, "singh, bir", days_ago=1)
    _punch(STORE_B, CLERK, "singh, bir", days_ago=1)
    result = derive_roster(stores=STORES)

    assert result.persons_created == 0, (
        "D-043 — store B must see store A's rename and link, not create a person"
    )
    rows = _assignments()
    assert len(rows) == 2
    assert {r[1] for r in rows} == {person}, "both assignments, one person"


@requires_db
def test_blank_name_falls_back_to_the_last_real_one(synthetic_stores: None) -> None:
    """D-044 / AC-001 — one nameless punch must not erase a known name.

    Fails under the old behaviour, which took the most recent name outright and
    would carry `''` here.
    """
    _punch(STORE_A, CLERK, "singh, bir", days_ago=10)
    _punch(STORE_A, CLERK, "", days_ago=1)
    derive_roster(stores=STORES)

    row = _assignments()[0]
    assert row[4] == "singh, bir", "the last NON-BLANK name wins"
    display = execute_sql(
        "SELECT display_name FROM ref_employees WHERE employee_id = :e", {"e": row[1]}
    )[0][0]
    assert display == "Bir Singh"


@requires_db
def test_never_named_pair_gets_a_clerk_placeholder(synthetic_stores: None) -> None:
    """D-044 / AC-001a — a pair with no name ever still gets an assignment.

    And a display_name a human can find. `''` satisfies the NOT NULL column and
    is invisible on every screen that will show this row; the placeholder names
    the PIN so office can search for it.
    """
    _punch(STORE_A, CLERK, "", days_ago=5)
    _punch(STORE_A, CLERK, "   ", days_ago=1)
    result = derive_roster(stores=STORES)

    assert result.assignments_created == 1, "a nameless worker still worked"
    row = _assignments()[0]
    display = execute_sql(
        "SELECT display_name FROM ref_employees WHERE employee_id = :e", {"e": row[1]}
    )[0][0]
    assert display == f"Clerk {CLERK} (unnamed)"
    assert display.strip() != ""


@requires_db
def test_two_nameless_pairs_with_one_pin_link_like_any_other(
    synthetic_stores: None,
) -> None:
    """D-044 — the empty key links, so AC-005 holds uniformly.

    The old code skipped empty normalized names when building the index, so
    AC-005 silently did not apply to them. Nothing in the spec carved that out.
    """
    _punch(STORE_A, CLERK, "")
    _punch(STORE_B, CLERK, "")
    result = derive_roster(stores=STORES)

    assert result.assignments_created == 2
    assert result.persons_created == 1, "same PIN, same (empty) name — one person"


# --- AC-024 — a returning person is the same row ---------------------------


def _terminate(employee_id: int, days_ago: int = 60) -> None:
    execute_sql(
        "UPDATE ref_employees SET is_active = false, termination_date = :d WHERE employee_id = :e",
        {"d": business_date_now() - timedelta(days=days_ago), "e": employee_id},
    )


def _person_state(employee_id: int) -> tuple[bool, object]:
    row = execute_sql(
        "SELECT is_active, termination_date FROM ref_employees WHERE employee_id = :e",
        {"e": employee_id},
    )[0]
    return (row[0], row[1])


@requires_db
def test_terminated_person_clocking_in_is_reactivated(
    synthetic_stores: None,
) -> None:
    """AC-024 / D-041 — the SAME row, reactivated, with the termination cleared.

    The assertion on ``termination_date IS NULL`` is the point of this test, not
    decoration. Option B of B-0037 would have set ``is_active = true`` and left
    the date in place, and a test checking only ``is_active`` passes under BOTH
    readings — proving nothing about the decision it claims to cover. That is
    the blind spot D-036 and D-038 each recorded, written the other way round.
    """
    _punch(STORE_A, CLERK, "singh, bir", days_ago=90)
    derive_roster(stores=STORES)
    employee_id = _assignments()[0][1]
    persons_before = execute_sql("SELECT count(*) FROM ref_employees")[0][0]

    _terminate(employee_id)
    assert _person_state(employee_id)[0] is False

    _punch(STORE_A, CLERK, "singh, bir", days_ago=0)
    derive_roster(stores=STORES)

    is_active, termination_date = _person_state(employee_id)
    assert is_active is True
    assert termination_date is None, "D-041 — the termination is cleared, not kept"

    assert execute_sql("SELECT count(*) FROM ref_employees")[0][0] == persons_before, (
        "AC-024 — the same row, never a new one"
    )
    assert len(_assignments()) == 1


@requires_db
def test_reactivation_reaches_a_person_found_by_the_linking_rule(
    synthetic_stores: None,
) -> None:
    """The second branch point — a NEW assignment linking to a terminated person.

    Someone who left store A and turns up at store B under the same PIN and name
    is resolved through AC-005, not through an existing assignment. Both paths
    must reactivate, and only one of them is the obvious one.
    """
    _punch(STORE_A, CLERK, "singh, bir", days_ago=90)
    derive_roster(stores=STORES)
    employee_id = _assignments()[0][1]
    _terminate(employee_id)

    _punch(STORE_B, CLERK, "singh, bir")
    result = derive_roster(stores=STORES)

    assert result.persons_created == 0, "AC-005 linked rather than creating"
    is_active, termination_date = _person_state(employee_id)
    assert is_active is True
    assert termination_date is None


@requires_db
def test_an_active_person_is_not_rewritten(synthetic_stores: None) -> None:
    """The guard — a normal night must not touch every person's row.

    Reactivation is a rare event; the WHERE clause exists so the overwhelmingly
    common path writes nothing at all.
    """
    _punch(STORE_A, CLERK, "singh, bir", days_ago=1)
    derive_roster(stores=STORES)
    employee_id = _assignments()[0][1]
    before = execute_sql(
        "SELECT updated_at FROM ref_employees WHERE employee_id = :e",
        {"e": employee_id},
    )[0][0]

    _punch(STORE_A, CLERK, "singh, bir")
    derive_roster(stores=STORES)

    after = execute_sql(
        "SELECT updated_at FROM ref_employees WHERE employee_id = :e",
        {"e": employee_id},
    )[0][0]
    assert after == before
    assert _person_state(employee_id) == (True, None)


@requires_db
def test_a_person_who_did_not_clock_in_stays_terminated(
    synthetic_stores: None,
) -> None:
    """Reactivation follows the punch, not the run.

    AC-024's trigger is "clocks in again". A terminated person with no punch in
    the window must still be terminated afterwards — otherwise a nightly job
    would quietly un-terminate the entire roster.
    """
    _punch(STORE_A, CLERK, "singh, bir", days_ago=90)
    _punch(STORE_B, CLERK_OTHER, "flores, maria", days_ago=90)
    derive_roster(stores=STORES)
    rows = _assignments()
    absent = next(r[1] for r in rows if r[3] == CLERK_OTHER)
    present = next(r[1] for r in rows if r[3] == CLERK)
    _terminate(absent)
    _terminate(present)

    _punch(STORE_A, CLERK, "singh, bir")
    derive_roster(since=business_date_now(), stores=STORES)

    assert _person_state(present)[0] is True, "clocked in — reactivated"
    assert _person_state(absent)[0] is False, "did not clock in — still terminated"
    assert _person_state(absent)[1] is not None


# --- Failure behaviour -----------------------------------------------------


@requires_db
def test_unknown_store_fails_loudly(synthetic_stores: None) -> None:
    """REQ-001's precondition — the FK rejects, loudly.

    Worth recording what this test found: the case is **unreachable through the
    derivation**, because `stg_timeclock.restaurant_number` carries its own
    foreign key to `ref_stores`. A punch for a store that does not exist cannot
    be staged in the first place, so the derivation never sees one. §6's edge
    row ("Assignment for an unknown store — FK rejects; derivation fails
    loudly") is satisfied one layer earlier than it reads.

    So this asserts the guarantee itself rather than staging an impossible
    input: an assignment for an unknown store is refused by the database.

    The person is created here rather than borrowed from the table. An earlier
    version read `MIN(employee_id) FROM ref_employees`, which passed only
    because the production roster happened to be sitting there — the same
    false-green D-042 was raised about, in a test nobody had looked at twice.
    On an empty table it fails for the wrong reason entirely.
    """
    _punch(STORE_A, CLERK, "singh, bir")
    derive_roster(stores=STORES)
    employee_id = _assignments()[0][1]

    with pytest.raises(Exception, match="ref_employee_assignments_store_number_fkey"):
        execute_sql(
            "INSERT INTO ref_employee_assignments "
            "(employee_id, store_number, clerk_id) "
            "VALUES (:e, 'T-PPL-NOPE', :c)",
            {"e": employee_id, "c": CLERK + "-fk"},
        )

    # And the upstream half: staging cannot hold one either.
    with pytest.raises(Exception, match="stg_timeclock_restaurant_number_fkey"):
        _punch("T-PPL-NOPE", CLERK, "singh, bir")


@requires_db
def test_derive_is_transactional_on_failure(
    synthetic_stores: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One transaction — a crash never leaves a person with no assignment.

    An orphaned `ref_employees` row is a person nobody can reach and nothing
    will ever clean up.

    The failure is injected rather than staged, because the database will not
    accept a genuinely bad input here (see `test_unknown_store_fails_loudly`).
    `derive_display_name` is made to raise on the SECOND person, so the first
    person and assignment are already written when the run dies — exactly the
    state a non-transactional implementation would commit.
    """
    _punch(STORE_A, CLERK, "singh, bir")
    _punch(STORE_B, CLERK_OTHER, "flores, maria")

    calls = {"n": 0}
    real = derive_module.derive_display_name

    def exploding(observed: str) -> str:
        calls["n"] += 1
        if calls["n"] > 1:
            raise RuntimeError("injected mid-run failure")
        return real(observed)

    monkeypatch.setattr(derive_module, "derive_display_name", exploding)

    before = execute_sql("SELECT count(*) FROM ref_employees")[0][0]
    with pytest.raises(RuntimeError, match="injected mid-run failure"):
        derive_roster(stores=STORES)
    after = execute_sql("SELECT count(*) FROM ref_employees")[0][0]

    assert calls["n"] == 2, "the failure must land after the first person exists"
    assert after == before, "no person survives a failed run"
    assert _assignments() == [], "and no assignment either"


@requires_db
def test_failed_run_is_recorded_as_failed(
    synthetic_stores: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """track_job marks the row failed and re-raises (AC-002's other half)."""
    _punch(STORE_A, CLERK, "singh, bir")
    monkeypatch.setattr(
        derive_module,
        "derive_display_name",
        lambda observed: (_ for _ in ()).throw(RuntimeError("injected")),
    )
    with pytest.raises(RuntimeError):
        derive_roster(stores=STORES)

    rows = execute_sql(
        "SELECT status FROM ops_job_runs WHERE job_name = 'derive_roster' "
        "ORDER BY started_at DESC LIMIT 1"
    )
    assert rows[0][0] == "failed"
