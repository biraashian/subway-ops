"""Schema tests for the people tables — SPEC-PPL-001 AC-011, AC-014, AC-022, AC-031.

T-0004 ships schema and nothing else, so these tests exercise the DATABASE's
guarantees rather than any Python behavior: constraints that must reject bad
rows, keys that must refuse duplicates, and the column shape SPEC §5 states.
The roster service that uses all of this arrives in T-0006 through T-0009.

DB-backed and, per B-0001, running against the live database until D-025's
containerised Postgres lands (T-0011). Every row these tests create is
namespaced with a synthetic prefix no real producer emits, and teardown removes
exactly those rows in dependency order. No real store number and no hardcoded
date (codex/13-BUILD/CONVENTIONS.md) — the store is looked up at runtime.
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal

import pytest

from subway_ops.calendar import business_date_now
from subway_ops.config import settings
from subway_ops.db.connection import execute_sql
from subway_ops.db.migrate import apply_migrations

# Namespaced so teardown deletes exactly what these tests made, and so a stray
# row is instantly identifiable as test residue rather than a real person.
MARK = "t0004-selftest"
CLERK_A = "t0004:clerk-a"
CLERK_B = "t0004:clerk-b"
TEST_EMAIL_PREFIX = "t0004-role-"

requires_db = pytest.mark.skipif(
    not settings.database_url,
    reason="DB integration test: needs DATABASE_URL",
)


def _wipe() -> None:
    """Delete in dependency order: log → wages → assignments → persons → users."""
    execute_sql("DELETE FROM ops_employee_identity_log WHERE actor = :m", {"m": MARK})
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
    execute_sql("DELETE FROM ref_users WHERE email LIKE :p", {"p": f"{TEST_EMAIL_PREFIX}%"})


@pytest.fixture
def clean_people() -> Iterator[None]:
    apply_migrations()
    _wipe()
    yield
    _wipe()


def _a_real_store() -> str:
    """An existing store number, looked up rather than hardcoded."""
    rows = execute_sql("SELECT store_number FROM ref_stores ORDER BY store_number LIMIT 1")
    assert rows, "ref_stores is empty; the FK tests cannot run"
    return str(rows[0][0])


def _make_person() -> int:
    rows = execute_sql(
        "INSERT INTO ref_employees (display_name) VALUES (:m) RETURNING employee_id",
        {"m": MARK},
    )
    return int(rows[0][0])


# ---------------------------------------------------------------------------
# AC-014 — a wage is never zero and never negative
# ---------------------------------------------------------------------------


@requires_db
@pytest.mark.parametrize("bad_rate", ["0", "-0.0001", "-15.5000"])
@pytest.mark.usefixtures("clean_people")
def test_hourly_rate_must_be_positive(bad_rate: str) -> None:
    """AC-014 — the CHECK rejects zero and negative, in the database.

    This lives in SQL rather than in Python because INV-007 turns on it: a
    missing wage must read as absent, never as a rate of zero. A zero that slips
    through does not raise anywhere — it silently costs an incomplete person's
    hours at nothing, and the labor-dollar total is quietly wrong instead of
    loudly partial.
    """
    employee_id = _make_person()
    with pytest.raises(Exception, match="hourly_rate"):
        execute_sql(
            "INSERT INTO ref_employee_wages "
            "(employee_id, effective_date, hourly_rate, set_by) "
            "VALUES (:e, :d, :r, :m)",
            {
                "e": employee_id,
                "d": business_date_now(),
                "r": Decimal(bad_rate),
                "m": MARK,
            },
        )


@requires_db
def test_hourly_rate_accepts_a_positive_rate(clean_people: None) -> None:
    """The other half of AC-014 — the constraint must not reject valid pay."""
    employee_id = _make_person()
    execute_sql(
        "INSERT INTO ref_employee_wages "
        "(employee_id, effective_date, hourly_rate, set_by) "
        "VALUES (:e, :d, :r, :m)",
        {
            "e": employee_id,
            "d": business_date_now(),
            "r": Decimal("18.7500"),
            "m": MARK,
        },
    )
    rows = execute_sql(
        "SELECT hourly_rate FROM ref_employee_wages WHERE employee_id = :e",
        {"e": employee_id},
    )
    assert rows[0][0] == Decimal("18.7500")


# ---------------------------------------------------------------------------
# AC-011 — a wage is inserted, never modified in place
# ---------------------------------------------------------------------------


@requires_db
def test_wage_pk_rejects_duplicate_effective_date(clean_people: None) -> None:
    """AC-011 — one rate per person per effective date, enforced by the PK.

    "Never updated in place" has to be a property of the database rather than a
    habit of the caller. With the composite PK, a second rate for the same
    person on the same date is refused outright, so a raise cannot rewrite last
    month's labor cost.
    """
    employee_id = _make_person()
    today = business_date_now()
    execute_sql(
        "INSERT INTO ref_employee_wages "
        "(employee_id, effective_date, hourly_rate, set_by) "
        "VALUES (:e, :d, :r, :m)",
        {"e": employee_id, "d": today, "r": Decimal("18.0000"), "m": MARK},
    )
    with pytest.raises(Exception, match="ref_employee_wages_pkey"):
        execute_sql(
            "INSERT INTO ref_employee_wages "
            "(employee_id, effective_date, hourly_rate, set_by) "
            "VALUES (:e, :d, :r, :m)",
            {"e": employee_id, "d": today, "r": Decimal("19.0000"), "m": MARK},
        )


@requires_db
def test_wage_history_accumulates_across_dates(clean_people: None) -> None:
    """Effective dating: a raise is a NEW row, and the old rate survives it."""
    employee_id = _make_person()
    today = business_date_now()
    for offset, rate in ((-30, "17.0000"), (0, "18.5000")):
        execute_sql(
            "INSERT INTO ref_employee_wages "
            "(employee_id, effective_date, hourly_rate, set_by) "
            "VALUES (:e, :d + CAST(:o AS INT), :r, :m)",
            {
                "e": employee_id,
                "d": today,
                "o": offset,
                "r": Decimal(rate),
                "m": MARK,
            },
        )
    rows = execute_sql(
        "SELECT hourly_rate FROM ref_employee_wages WHERE employee_id = :e ORDER BY effective_date",
        {"e": employee_id},
    )
    assert [r[0] for r in rows] == [Decimal("17.0000"), Decimal("18.5000")]


# ---------------------------------------------------------------------------
# Assignments — the join key back to stg_timeclock
# ---------------------------------------------------------------------------


@requires_db
def test_assignment_unique_on_store_and_clerk(clean_people: None) -> None:
    """`stg_timeclock` keys on exactly this pair, so it must be unique here.

    INV-002's idempotency rests on it: re-running the derivation over the same
    timeclock rows must find the assignment already present rather than adding
    a second one.
    """
    store = _a_real_store()
    first = _make_person()
    second = _make_person()
    execute_sql(
        "INSERT INTO ref_employee_assignments (employee_id, store_number, clerk_id) "
        "VALUES (:e, :s, :c)",
        {"e": first, "s": store, "c": CLERK_A},
    )
    with pytest.raises(Exception, match="ref_employee_assignments_store_number_clerk_id_key"):
        execute_sql(
            "INSERT INTO ref_employee_assignments "
            "(employee_id, store_number, clerk_id) VALUES (:e, :s, :c)",
            {"e": second, "s": store, "c": CLERK_A},
        )


@requires_db
def test_same_clerk_id_at_a_different_store_is_allowed(clean_people: None) -> None:
    """The measured reality B-0014 was decided on: a PIN is per-store.

    PIN 8 appears under 5 different names at 5 stores. The UNIQUE is on the
    PAIR, so the same clerk_id at two stores must remain insertable — if it did
    not, the derivation would fail on real data every night.
    """
    stores = execute_sql("SELECT store_number FROM ref_stores ORDER BY store_number LIMIT 2")
    if len(stores) < 2:
        pytest.skip("needs two stores to prove the pair is what is unique")
    person = _make_person()
    for row in stores:
        execute_sql(
            "INSERT INTO ref_employee_assignments "
            "(employee_id, store_number, clerk_id) VALUES (:e, :s, :c)",
            {"e": person, "s": str(row[0]), "c": CLERK_B},
        )
    rows = execute_sql(
        "SELECT count(*) FROM ref_employee_assignments WHERE clerk_id = :c",
        {"c": CLERK_B},
    )
    assert rows[0][0] == 2


@requires_db
def test_assignment_store_fk_rejects_unknown_store(clean_people: None) -> None:
    """REQ-001's precondition — derivation must fail loudly on an unknown store.

    §6's edge table: "FK rejects; derivation fails loudly". A silently accepted
    assignment for a store that does not exist would attach hours to nothing.
    """
    person = _make_person()
    with pytest.raises(Exception, match="ref_employee_assignments_store_number_fkey"):
        execute_sql(
            "INSERT INTO ref_employee_assignments "
            "(employee_id, store_number, clerk_id) VALUES (:e, :s, :c)",
            {"e": person, "s": "t0004-no-such-store", "c": CLERK_A},
        )


# ---------------------------------------------------------------------------
# AC-031 — identifiers, nullable and unique, and no auth anywhere
# ---------------------------------------------------------------------------


@requires_db
def test_phone_is_unique_and_nullable(clean_people: None) -> None:
    """AC-031 — nullable because most of the 250 have neither identifier yet."""
    first = _make_person()
    execute_sql(
        "UPDATE ref_employees SET phone = :p WHERE employee_id = :e",
        {"p": "t0004:+15550100", "e": first},
    )
    second = _make_person()
    with pytest.raises(Exception, match="phone"):
        execute_sql(
            "UPDATE ref_employees SET phone = :p WHERE employee_id = :e",
            {"p": "t0004:+15550100", "e": second},
        )

    # Nullability is the half that matters operationally: two people with no
    # phone must not collide with each other.
    third = _make_person()
    rows = execute_sql(
        "SELECT count(*) FROM ref_employees WHERE display_name = :m AND phone IS NULL",
        {"m": MARK},
    )
    assert rows[0][0] >= 2, f"NULL phones must not collide (third={third})"


@requires_db
def test_discord_user_id_is_unique_and_nullable(clean_people: None) -> None:
    """AC-031 — B-0015 chose Discord OAuth, so this is the primary identifier.

    Still only an identifier. NG-004 fences the flow out: nothing in this
    migration or this task authenticates anybody.
    """
    first = _make_person()
    execute_sql(
        "UPDATE ref_employees SET discord_user_id = :d WHERE employee_id = :e",
        {"d": "t0004:discord-1", "e": first},
    )
    second = _make_person()
    with pytest.raises(Exception, match="discord_user_id"):
        execute_sql(
            "UPDATE ref_employees SET discord_user_id = :d WHERE employee_id = :e",
            {"d": "t0004:discord-1", "e": second},
        )

    rows = execute_sql(
        "SELECT count(*) FROM ref_employees WHERE display_name = :m AND discord_user_id IS NULL",
        {"m": MARK},
    )
    assert rows[0][0] >= 1


# ---------------------------------------------------------------------------
# AC-022 — termination retains everything
# ---------------------------------------------------------------------------


@requires_db
def test_termination_sets_date_and_flag_without_deleting(clean_people: None) -> None:
    """AC-022 and INV-009 — the schema must make termination a state, not a delete.

    Nothing here prevents a DELETE at the SQL level; what this pins is that the
    columns AC-022 needs exist and hold the terminated state, so the roster
    service in T-0008 has somewhere to put it.
    """
    person = _make_person()
    execute_sql(
        "UPDATE ref_employees SET termination_date = :d, is_active = false WHERE employee_id = :e",
        {"d": business_date_now(), "e": person},
    )
    rows = execute_sql(
        "SELECT termination_date IS NOT NULL, is_active FROM ref_employees WHERE employee_id = :e",
        {"e": person},
    )
    assert rows[0][0] is True
    assert rows[0][1] is False

    still_there = execute_sql(
        "SELECT count(*) FROM ref_employees WHERE employee_id = :e", {"e": person}
    )
    assert still_there[0][0] == 1, "INV-009 — termination never deletes a row"


# ---------------------------------------------------------------------------
# ref_users.role — the widened CHECK
# ---------------------------------------------------------------------------


@requires_db
def test_ref_users_role_accepts_the_six_roles(clean_people: None) -> None:
    """SPEC §5 — the CHECK expands to add `store_manager`, `office`, `crew`.

    The resulting six are an ACCESS vocabulary, not codex 06's job ladder. See
    the divergence note in migration 021: `readonly` is a lender/mentor view and
    is nobody's job, which is why it stays.
    """
    six = ("owner", "field_manager", "office", "store_manager", "crew", "readonly")
    for i, role in enumerate(six):
        execute_sql(
            "INSERT INTO ref_users (email, display_name, role, password_hash) "
            "VALUES (:e, :n, :r, 'x')",
            {"e": f"{TEST_EMAIL_PREFIX}{i}@example.com", "n": MARK, "r": role},
        )
    rows = execute_sql(
        "SELECT count(DISTINCT role) FROM ref_users WHERE email LIKE :p",
        {"p": f"{TEST_EMAIL_PREFIX}%"},
    )
    assert rows[0][0] == 6


@requires_db
def test_ref_users_role_still_rejects_an_unknown_role(clean_people: None) -> None:
    """The CHECK must widen, not disappear.

    `shift_lead` is the deliberate case: it is a real role in codex 06's job
    ladder and in `ops_worklist_items.assigned_role`, and it is NOT licensed for
    `ref_users` by SPEC §5, which names three additions and only three. If this
    test ever starts failing, the two vocabularies have been merged by someone —
    which may be right, but is a spec decision and not a silent one.
    """
    for role in ("shift_lead", "wibble"):
        with pytest.raises(Exception, match="role"):
            execute_sql(
                "INSERT INTO ref_users (email, display_name, role, password_hash) "
                "VALUES (:e, :n, :r, 'x')",
                {"e": f"{TEST_EMAIL_PREFIX}bad@example.com", "n": MARK, "r": role},
            )


# ---------------------------------------------------------------------------
# Shape — money typing, and the column set SPEC §5 states
# ---------------------------------------------------------------------------


@requires_db
def test_money_columns_are_numeric_12_4(clean_people: None) -> None:
    """codex 02 — money is NUMERIC(12,4) and never a float."""
    rows = execute_sql(
        "SELECT data_type, numeric_precision, numeric_scale "
        "FROM information_schema.columns "
        "WHERE table_name = 'ref_employee_wages' AND column_name = 'hourly_rate'"
    )
    assert rows, "hourly_rate not found"
    data_type, precision, scale = rows[0]
    assert data_type == "numeric"
    assert (precision, scale) == (12, 4)


@requires_db
@pytest.mark.parametrize(
    ("table", "expected"),
    [
        (
            "ref_employees",
            {
                "employee_id",
                "display_name",
                "display_name_is_manual",
                "phone",
                "discord_user_id",
                "hire_date",
                "termination_date",
                "is_active",
                "merged_into",
                "user_email",
                "created_at",
                "updated_at",
            },
        ),
        (
            "ref_employee_assignments",
            {
                "assignment_id",
                "employee_id",
                "store_number",
                "clerk_id",
                "observed_name",
                "normalized_name",
                "role",
                "is_active",
            },
        ),
        (
            "ref_employee_wages",
            {"employee_id", "effective_date", "hourly_rate", "set_by", "set_at"},
        ),
        (
            "ops_employee_identity_log",
            {
                "log_id",
                "action",
                "from_employee_id",
                "to_employee_id",
                "assignment_id",
                "actor",
                "at",
                "reason",
            },
        ),
    ],
)
@pytest.mark.usefixtures("clean_people")
def test_table_columns_match_spec_section_5(table: str, expected: set[str]) -> None:
    """Equality, not containment — this catches gold-plating as well as gaps.

    B-0026 found T-0003 shipping two columns past the shape its spec stated, and
    a `>=` assertion would have passed happily. The only extra beyond SPEC §5's
    prose is `ops_employee_identity_log.log_id`, a surrogate key the spec omits
    and a log table cannot do without; it is named here so the exception is
    visible rather than absorbed.
    """
    rows = execute_sql(
        "SELECT column_name FROM information_schema.columns WHERE table_name = :t",
        {"t": table},
    )
    assert {str(r[0]) for r in rows} == expected


@requires_db
def test_identity_log_records_a_merge_and_a_split(clean_people: None) -> None:
    """AC-007 / AC-008 — both actions must fit the shape, with different subsets.

    A merge names from and to; a split names an assignment and the person it
    moved to. This is why those three columns are nullable, and the test exists
    so that the nullability reads as intended rather than as laxness.
    """
    source = _make_person()
    target = _make_person()
    store = _a_real_store()
    rows = execute_sql(
        "INSERT INTO ref_employee_assignments (employee_id, store_number, clerk_id) "
        "VALUES (:e, :s, :c) RETURNING assignment_id",
        {"e": target, "s": store, "c": CLERK_A},
    )
    assignment_id = int(rows[0][0])

    execute_sql(
        "INSERT INTO ops_employee_identity_log "
        "(action, from_employee_id, to_employee_id, actor, reason) "
        "VALUES ('merge', :f, :t, :m, 'same human, two PINs')",
        {"f": source, "t": target, "m": MARK},
    )
    execute_sql(
        "INSERT INTO ops_employee_identity_log "
        "(action, to_employee_id, assignment_id, actor, reason) "
        "VALUES ('split', :t, :a, :m, 'wrong person')",
        {"t": target, "a": assignment_id, "m": MARK},
    )

    logged = execute_sql(
        "SELECT action, at IS NOT NULL FROM ops_employee_identity_log "
        "WHERE actor = :m ORDER BY log_id",
        {"m": MARK},
    )
    assert [r[0] for r in logged] == ["merge", "split"]
    assert all(r[1] for r in logged), "every log row is stamped"


@requires_db
def test_identity_log_rejects_an_unknown_action(clean_people: None) -> None:
    """Only merge and split exist. A third verb is a spec change."""
    with pytest.raises(Exception, match="action"):
        execute_sql(
            "INSERT INTO ops_employee_identity_log (action, actor, reason) "
            "VALUES ('unmerge', :m, 'not a thing')",
            {"m": MARK},
        )
