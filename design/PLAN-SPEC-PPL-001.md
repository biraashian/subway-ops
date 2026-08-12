# PLAN — SPEC-PPL-001 · Employee roster and wages

**L1 technical design.** The "how" for the approved spec. Anchors: every module
below names the REQ it serves; nothing here adds behavior the spec does not
license.

## 0 · Readiness check

| Gate | Result |
|---|---|
| Spec `status: approved` | yes |
| Zero open Qs | **one open — Q-007**, and it blocks no REQ in this spec |

Q-007 (which store bears the overtime premium) is fenced out of scope by NG-007.
`CON-005` returns a per-person weekly cost; allocation across stores belongs to
the labor-dollar mart. No REQ or AC here can be implemented differently
depending on how B-0020 resolves, so the Definition of Ready is met in substance.
Recording the judgement rather than waving it through: a rule that halts on an
explicitly-fenced question deadlocks permanently.

**One clarification raised, not resolved:** AC-019 says "a labor-dollar
aggregate" without naming a grain, and codex 03 says a metric without a stated
grain is a gap. Read here as **per person per business week**, because CON-005
is the only aggregate this spec produces. Store-level marking rides with the
mart. Raised as **B-0021**; the design does not depend on the answer.

## 1 · New dependency on a table that does not exist

`ops_worklist_items` is referenced by AC-013 and AC-018 but has never been
created. It was scoped to SPEC-APP-001, which is not written.

**Decision: SPEC-PPL-001 creates it**, in full, to codex 02's stated shape —
typed, role-assigned, state (`open` / `in_progress` / `resolved` / `dismissed`),
due date, and a reference back to whatever produced it. That definition is
complete in the codex, so this is not an invention; PPL is simply the first
consumer. SPEC-APP-001 will build the *screen*, not the table.

Noted as an ordering fact for `/spec SPEC-APP-001`: do not re-create it.

## 2 · Module layout

New package `src/subway_ops/people/`. Mirrors the existing
`ingest/` + `transform/` shape: pure helpers at module top, one public entry
point, `track_job` at the boundary.

| Path | Serves | Contents |
|---|---|---|
| `people/__init__.py` | — | re-exports the five public callables |
| `people/names.py` | REQ-002, REQ-006 | `normalize_name`, `derive_display_name` — pure, no I/O |
| `people/derive.py` | REQ-001, REQ-002 | `derive_roster()`, `DeriveResult`; the nightly job |
| `people/identity.py` | REQ-002 | `merge()`, `split()`, `ConflictError` |
| `people/wages.py` | REQ-003 | `record_wage()`, `rate_in_force()` |
| `people/cost.py` | REQ-003 | `cost_week()`, `WeekCost` |
| `people/roles.py` | REQ-006 | `effective_role()`, `ROLE_ORDER` |
| `people/completeness.py` | REQ-004 | `completeness_of()`, `sync_worklist()` |
| `db/worklist.py` | REQ-001, REQ-004 | `open_item()`, `resolve_item()` — generic, not people-specific |
| `db/migrations/020_worklist.sql` | REQ-001, REQ-004 | `ops_worklist_items` |
| `db/migrations/021_people.sql` | all | the three `ref_*` tables, `ops_employee_identity_log`, `ref_users.role` widening |
| `scripts/derive_roster.py` | REQ-001 | thin CLI, `main()` wraps `run_derive_roster(...)` |

`db/worklist.py` sits in `db/` rather than `people/` deliberately: codex 02
calls the worklist the system's spine, and every later phase writes to it.
Putting it under `people/` would make Phase B import from Phase A's package for
no reason.

## 3 · Signatures

```python
# people/names.py — pure
def normalize_name(raw: str) -> str: ...                    # lower, strip, collapse WS
def derive_display_name(observed: str) -> str: ...          # "LAST, FIRST" -> "First Last"

# people/derive.py
@dataclass(frozen=True)
class DeriveResult:
    assignments_created: int
    persons_created: int
    incomplete_opened: int

def derive_roster(*, since: date | None = None) -> DeriveResult: ...   # CON-001

# people/identity.py
class ConflictError(Exception): ...
def merge(source_id: int, target_id: int, *, by: str, reason: str) -> int: ...   # CON-004
def split(assignment_id: int, *, by: str, reason: str) -> int: ...

# people/wages.py
def record_wage(*, employee_id: int, effective_date: date,
                hourly_rate: Decimal, set_by: str, actor_role: str) -> None: ...  # CON-003
def rate_in_force(employee_id: int, on: date) -> Decimal | None: ...              # CON-002

# people/cost.py
@dataclass(frozen=True)
class WeekCost:
    regular_hours: Decimal
    overtime_hours: Decimal
    dollars: Decimal | None
    is_costed: bool

def cost_week(employee_id: int, week_end: date) -> WeekCost: ...                  # CON-005

# people/roles.py
ROLE_ORDER: tuple[str, ...] = ("crew", "shift_lead", "store_manager",
                               "field_manager", "office", "owner")
def effective_role(roles: Iterable[str]) -> str: ...

# people/completeness.py
def completeness_of(employee_id: int) -> frozenset[str]: ...   # missing field names
def sync_worklist() -> int: ...

# db/worklist.py
def open_item(*, kind: str, subject_ref: str, assigned_role: str,
              summary: str, due_date: date | None = None) -> int | None: ...
def resolve_item(kind: str, subject_ref: str) -> int: ...
```

`actor_role` on `record_wage` is how AC-013's `PermissionError` is enforced at
the library boundary rather than only in a view. Passing the role in keeps the
function pure of session state and testable without a request context.

## 4 · Data flow

```
stg_timeclock  ──(new (store, clerk_id) pairs)──►  derive_roster()
                                                        │
                          normalize_name(observed_name)  │
                                                        ▼
                    match on (clerk_id, normalized_name) in ref_employee_assignments
                          │ hit                              │ miss
                          ▼                                  ▼
              link to existing employee_id        INSERT ref_employees (AC-006)
                          │                                  │
                          └──────────┬───────────────────────┘
                                     ▼
                    upsert ref_employee_assignments  (UNIQUE store_number, clerk_id)
                                     ▼
                          completeness_of(employee_id)
                                     ▼
                    open_item(kind="employee_incomplete", ...)   [idempotent]
```

Costing is a separate read path, invoked by the mart, never by the derive job:

```
cost_week(employee, week_end)
   → business_week_of(week_end) from subway_ops.calendar   ← codex 01, not timedelta
   → SUM(hours_after_adj) over that person's assignments   ← AC-015
   → rate_in_force(employee, week_end)                     ← AC-012
   → split at OVERTIME_THRESHOLD_HOURS, premium ×1.5       ← AC-016
   → dollars=None, is_costed=False if rate missing or any hours NULL  ← AC-017, INV-007
```

## 5 · REQ → module mapping

| REQ | Modules | Key ACs |
|---|---|---|
| REQ-001 derive stubs | `derive.py`, `names.py`, `db/worklist.py` | AC-001…AC-004 |
| REQ-002 resolve to person | `derive.py`, `identity.py`, `names.py` | AC-005…AC-010 |
| REQ-003 wages + costing | `wages.py`, `cost.py`, `config.py` | AC-011…AC-017 |
| REQ-004 incompleteness | `completeness.py`, `db/worklist.py` | AC-018…AC-021 |
| REQ-005 termination | `identity.py` (status transitions), `derive.py` (AC-024 reactivation) | AC-022…AC-025 |
| REQ-006 identity + roles | `names.py`, `roles.py`, migration `021` | AC-026…AC-031 |

## 6 · Constitution check

| Rule (source) | Compliance |
|---|---|
| Money `NUMERIC(12,4)`, `Decimal` never float (codex 02) | `hourly_rate NUMERIC(12,4)`; `WeekCost.dollars: Decimal \| None`. `check_money_types.py` covers the migration. |
| Timestamps `TIMESTAMPTZ` UTC (codex 02) | All new `*_at` columns `TIMESTAMPTZ`. Does **not** fix `stg_timeclock` — B-0019, out of scope. |
| Dates are business dates (codex 01) | `cost_week` uses `business_week_of`; no raw `timedelta(days=7)`. |
| Idempotent upsert on a natural key (codex 02) | `ref_employee_assignments` via `upsert_rows` on `(store_number, clerk_id)`. **`ref_employees` has no natural key** — see below. |
| `track_job` on scheduled work (codex 02) | `derive_roster` wraps in `track_job("derive_roster")`, AC-002. Enforced by `check_track_job.py`. |
| Migrations append-only (codex 02) | Two new files, `020` and `021`. Nothing edited. `check_migrations_append_only.py` covers it. |
| Parameter-bound SQL (codex 02) | All through `execute_sql` / `upsert_rows`. |
| No `print()` outside `__main__` (codex 13) | structlog; `check_no_print.py` covers it. |
| Existing patterns over new (this skill) | `people/` mirrors `transform/`: pure helpers, one entry point, `track_job` at the edge. `upsert_rows` reused, not reimplemented. |
| Tests travel with the unit (codex 13) | §7. |
| No test against a real store number or hardcoded date (codex 13) | Fixtures use `T-PPL-*` synthetic stores and `previous_business_week()`. |

**One deviation, stated rather than worked around.** `upsert_rows` requires a
natural key backed by a unique constraint. `ref_employees` has a surrogate
`BIGSERIAL` and deliberately **no** natural key — that is the whole point of
B-0014's answer, since no field or combination identifies a person. So person
creation uses a plain `INSERT ... RETURNING employee_id` inside the same
transaction as the assignment upsert, not `upsert_rows`.

This is not a new pattern, it is the absence of an applicable one, and it does
not weaken idempotency: INV-002 is preserved because a person is only ever
created when the `(clerk_id, normalized_name)` lookup misses, and that lookup is
against a committed unique index. Re-running finds the assignment and skips.
The whole derive runs in one transaction so a crash cannot leave a person
without an assignment.

## 7 · Test strategy

Pure modules unit-test with no database: `names.py`, `roles.py`, and the
overtime split in `cost.py` (factored so the arithmetic is a pure function of
hours and rate).

| Test file | Covers | Shape |
|---|---|---|
| `tests/test_people_names.py` | AC-026, AC-027 | table-driven over real observed names incl. `singh, bir` / `bir`, `samir, samir`, single-token, empty |
| `tests/test_people_roles.py` | AC-029, AC-030 | ordering, ties, unknown role rejected |
| `tests/test_people_cost.py` | AC-015…AC-017 | pure split at 39.99 / 40 / 40.01 / 50 h; `None` rate → `is_costed=False`, `dollars is None`; NULL hours → uncosted |
| `tests/test_people_derive.py` | AC-001…AC-006, INV-002 | synthetic `stg_timeclock` rows; **re-run asserts zero new rows**; PIN reused with a different name → two persons; same PIN+name at two stores → one person |
| `tests/test_people_identity.py` | AC-007, AC-008, AC-010 | merge repoints assignments and logs; overlapping wage rows → `ConflictError` + worklist item; split restores |
| `tests/test_people_wages.py` | AC-011…AC-014 | effective-dating across a raise; back-dated insert; non-positive rejected; non-office role → `PermissionError`; `rate_in_force` returns `None` not zero |
| `tests/test_people_completeness.py` | AC-018…AC-021 | no duplicate open item; resolve on completion; hours still counted while incomplete |
| `tests/test_worklist.py` | REQ-001/004 support | open/resolve idempotency |

**Two tests worth naming because they encode the decisions rather than the
code:** the derive test asserting that PIN `8` under two different names
produces two persons (that is B-0014's answer, and a regression here silently
fuses two people); and the cost test asserting `dollars is None` rather than
`Decimal("0")` when a rate is missing (INV-007 — a zero would flow into a mart
and understate labor cost invisibly).

DB-backed tests use synthetic stores `T-PPL-A` / `T-PPL-B` seeded
`is_active=false`, and derive every date from `previous_business_week()`. Both
rules come from codex 13, and both exist because they were broken before.

## 8 · Dependency and ordering

- `020_worklist.sql` before `021_people.sql` — the people migration's worklist
  writes assume the table.
- `people/names.py` before `derive.py` — derive imports it.
- `cost.py` depends on `wages.py` but nothing else; can be built in parallel
  with `identity.py`.
- Nothing here depends on SPEC-APP-001, SPEC-TGT-001, or codex 08. `cost_week`
  is consumed by the labor-dollar mart, which is a later task in another spec.
- **B-0019 is not touched.** `stg_timeclock` timestamps stay naive; this spec
  keys on `business_date`.

## 9 · Task forecast

| Task | Title | Size | Notes |
|---|---|---|---|
| T-0003 | `ops_worklist_items` migration + `db/worklist.py` + tests | 60 min | The spine. Standalone; nothing else blocks on it landing first except by import. |
| T-0004 | People migration `021` — three tables, identity log, `ref_users.role` widening | 60 min | `schema_snapshot.py` will show the drift; that is the point. |
| T-0005 | `people/names.py` + `people/roles.py` + tests | 45 min | Pure. `[P]` — no DB, parallel-safe. |
| T-0006 | `people/derive.py` — stub derivation and person resolution | 90 min | The heart. AC-001…AC-006 + INV-002. Depends on T-0003, T-0004, T-0005. |
| T-0007 | `people/wages.py` + `people/cost.py` — effective dating, overtime split | 90 min | AC-011…AC-017. Depends on T-0004. `[P]` with T-0006. |
| T-0008 | `people/identity.py` — merge, split, the overlapping-wage refusal | 75 min | AC-007, AC-008, AC-010. Depends on T-0006, T-0007. |
| T-0009 | `people/completeness.py` + `scripts/derive_roster.py` + wire into `daily_pull` | 60 min | AC-018…AC-021. `check_ingest_registered.py` will fail until the wiring lands. |

Seven tasks, none over 90 minutes. T-0006 and T-0007 are at the ceiling and
were considered for splitting; both were kept whole because their ACs are
mutually dependent — splitting T-0007 would put the overtime split in one task
and the rate resolution it consumes in another, and neither half would pass its
own ACs.

**First backfill note:** the first `derive_roster` run over 19,089 existing rows
will create roughly 399 assignments and somewhere near 250–399 persons
(exact count depends on how many of the 51 matching pairs collapse), and open
one worklist item per incomplete person. That is a large first worklist. T-0009
should log the count rather than let office discover it.
