# === SPEC: Employee roster and wages ===

## 0 · Metadata

```yaml
spec_id:        SPEC-PPL-001
feature:        Employee roster and wages
version:        0.1.0
status:         draft            # draft | interview open | approved | planned | tasked | building | complete
owner:          amitoj
inherits:       codex@2026-08-11
source:         codex/06-PEOPLE (greenfield; reads the existing stg_timeclock)
phase:          specify
bound_by:
  - codex/06-PEOPLE            # the whole chapter — this spec is its implementation
  - codex/02-DATA-MODEL        # money is NUMERIC(12,4); TIMESTAMPTZ UTC; idempotent upsert; track_job
  - codex/00-INSTITUTION       # the role ladder; scope rule "own scope and nothing above"
  - codex/03-MEASUREMENT       # the person is the employee grain
  - D-020                      # wages are hand-kept; FreshConnect has none
open_questions: 6              # Q-001 … Q-006 — see §10
```

## 1 · Intent

Make a **person** a first-class row. Today the system knows about stores and
about clerk PINs; it does not know about people. Scheduling, timecards,
training records, certificates, KPIs, bonuses and recognition all key on a
person, and none of them can be built until this exists.

Two things make this more than a CRUD table. First, the roster must **build
itself** from data already flowing — 19,089 timeclock rows are already landing
nightly and nobody is going to type 250 people in. Second, it must carry
**wages**, which exist in no upstream system at all, and which are the missing
input that has left `mart_store_weekly.labor_cost_pct` NULL since it was
written.

**Inherited non-negotiables.** A person is one record with many store
assignments (codex 06). Wages are effective-dated and never updated in place
(codex 06, mirroring codex 04's target discipline). Money is `NUMERIC(12,4)`
and `Decimal` (codex 02). Nothing is deleted on termination (codex 00, 06).
Wage visibility is office and owner only (codex 06).

## 2 · User Stories

- **US-001** — As **office**, I want the roster to populate itself from
  timeclock activity, so that I never type in an employee who is already
  working.
- **US-002** — As **office**, I want to record each person's wage with an
  effective date, so that labor dollars are computable and a raise does not
  rewrite last month.
- **US-003** — As the **owner**, I want one person to be one record even when
  they work several stores, so that their hours, KPIs and certificates are not
  split.
- **US-004** — As **office**, I want to see which roster rows are incomplete,
  so that missing wages are visible rather than silently costing zero.
- **US-005** — As the **owner**, I want a departed employee's records to
  survive their departure, so that an inspection or a claim can still be
  answered.

## 3 · Behavioral Specification

---
### REQ-001 — Derive roster stubs from timeclock activity
Serves **US-001** · Governed by **codex/06-PEOPLE "Onboarding: the roster builds itself" (6.1A)**

- **Inputs** — `stg_timeclock` rows: `restaurant_number: TEXT`, `clerk_id: TEXT`,
  `employee_name: TEXT NOT NULL in practice`, `business_date: DATE`.
- **Outputs** — `ref_employees` rows; `ref_employee_assignments` rows;
  `ops_worklist_items` rows of type `employee_incomplete`.
- **I/O mapping** — a `(restaurant_number, clerk_id)` pair present in
  `stg_timeclock` and absent from `ref_employee_assignments` produces one
  assignment, attached to a person per REQ-002, plus one worklist item if the
  resulting person is incomplete per REQ-004.
- **Preconditions** — `restaurant_number` exists in `ref_stores`.
- **Postconditions** — every `(restaurant_number, clerk_id)` in `stg_timeclock`
  has exactly one `ref_employee_assignments` row.
- **Invariants**
  - `INV-001` — the derivation never deletes or deactivates an existing
    assignment; absence from a run means "did not work", not "gone".
  - `INV-002` — re-running the derivation over the same input produces no new
    rows (idempotent upsert, codex 02).
- **Sequential logic** — runs after `ingest_timeclock`, before mart refresh.
- **Acceptance criteria (EARS)**
  - `AC-001` — WHEN the derivation encounters a `(restaurant_number, clerk_id)`
    with no existing assignment, the roster service SHALL create one assignment
    row carrying `clerk_id`, `restaurant_number`, and the `employee_name` most
    recently seen for that pair.
  - `AC-002` — WHEN the derivation runs, the roster service SHALL wrap its work
    in `track_job("derive_roster")` and set `meta["rows_written"]`.
  - `AC-003` — IF a `(restaurant_number, clerk_id)` already has an assignment,
    THEN the roster service SHALL leave the existing person link unchanged.
  - `AC-004` — IF `employee_name` differs from the name recorded on the
    assignment, THEN the roster service SHALL update the assignment's observed
    name and SHALL NOT alter the person's display name.
---

---
### REQ-002 — Resolve a timeclock assignment to a person
Serves **US-003** · Governed by **codex/06-PEOPLE "A person is one record" (6.2A)**

> **BLOCKED — Q-001.** The linking rule is undecided and cannot be inferred.
> The ACs below cover only what holds under every candidate rule; the rule
> itself is the open question. See §10 and B-0014.

- **Inputs** — a `(restaurant_number, clerk_id, employee_name)` triple.
- **Outputs** — an `employee_id`, either existing or newly created.
- **Preconditions** — none.
- **Postconditions** — exactly one `ref_employees` row is associated.
- **Invariants**
  - `INV-003` — an assignment always references exactly one person.
  - `INV-004` — a person link, once established, is only changed by an
    explicit office merge or split, never by a subsequent derivation run.
- **Acceptance criteria (EARS)**
  - `AC-005` — WHEN no linking rule matches, the roster service SHALL create a
    new person and link the assignment to it.
  - `AC-006` — IF two assignments are later determined to be the same person,
    THEN the roster service SHALL support an office-initiated **merge** that
    repoints both assignments at one person and records who merged and when.
  - `AC-007` — IF a merge was wrong, THEN the roster service SHALL support a
    **split** that restores separate persons, retaining both prior links in
    history.
  - `AC-008` — WHILE a person has more than one active assignment, the roster
    service SHALL report their hours as the sum across all assignments.
---

---
### REQ-003 — Record wages, effective-dated
Serves **US-002** · Governed by **codex/06-PEOPLE "Wages"**, **D-020**

- **Inputs** — `employee_id`, `effective_date: DATE`, `hourly_rate: NUMERIC(12,4)`,
  `set_by: TEXT`.
- **Outputs** — a `ref_employee_wages` row.
- **I/O mapping** — the rate in force for a business date is the row with the
  greatest `effective_date` less than or equal to that date.
- **Preconditions** — the person exists; `hourly_rate > 0`.
- **Postconditions** — prior rows are unchanged.
- **Invariants**
  - `INV-005` — no `UPDATE` is ever issued against `ref_employee_wages`; a
    correction is a new row.
  - `INV-006` — a wage rate is readable only by `office` and `owner`.
- **Acceptance criteria (EARS)**
  - `AC-009` — WHEN a wage is recorded, the roster service SHALL insert a new
    row carrying `set_by` and `set_at` and SHALL NOT modify any existing row.
  - `AC-010` — WHEN labor dollars are computed for a business date, the roster
    service SHALL resolve the rate in force **for that date**, not the current
    rate.
  - `AC-011` — IF a caller whose role is not `office` or `owner` requests a
    wage, THEN the roster service SHALL refuse and SHALL NOT include the rate
    in any response body.
  - `AC-012` — IF `hourly_rate` is zero or negative, THEN the roster service
    SHALL reject the row.
---

---
### REQ-004 — Incomplete persons are visible and excluded from labor dollars
Serves **US-004** · Governed by **codex/06-PEOPLE "A stub is incomplete"**

- **Inputs** — a `ref_employees` row and its wage history.
- **Outputs** — a completeness state; `ops_worklist_items`; a
  `partially_costed` flag on any labor-dollar aggregate.
- **I/O mapping** — a person missing any of wage, role or hire date is
  `incomplete`.
- **Invariants**
  - `INV-007` — an incomplete person's hours are **never** costed at zero. They
    are excluded from the labor-dollar sum and the sum is marked partial.
- **Acceptance criteria (EARS)**
  - `AC-013` — WHEN a person becomes incomplete, the roster service SHALL open
    one `ops_worklist_items` row assigned to `office`, and SHALL NOT open a
    duplicate while one is already open for that person.
  - `AC-014` — WHEN a labor-dollar aggregate includes hours from an incomplete
    person, the roster service SHALL exclude those hours from the dollar total
    and SHALL mark the aggregate `partially_costed` with a count of excluded
    persons.
  - `AC-015` — WHEN the last missing field is supplied, the roster service
    SHALL resolve the open worklist item.
  - `AC-016` — IF a person is incomplete, THEN the roster service SHALL still
    include their hours in hours-based and throughput metrics.
---

---
### REQ-005 — Termination retains everything
Serves **US-005** · Governed by **codex/06-PEOPLE "Leaving" (6.3A)**, **codex/07 retention**

- **Inputs** — `employee_id`, `termination_date: DATE`.
- **Outputs** — updated person status.
- **Invariants**
  - `INV-008` — termination never deletes a row from any table.
  - `INV-009` — a terminated person's historical hours remain in every mart.
- **Acceptance criteria (EARS)**
  - `AC-017` — WHEN a person is terminated, the roster service SHALL set
    `termination_date` and `is_active = false`.
  - `AC-018` — WHILE a person is terminated, the roster service SHALL exclude
    them from scheduling, active rosters and recognition, and SHALL continue to
    include their historical hours in past-period aggregates.
  - `AC-019` — IF a terminated person clocks in again, THEN the roster service
    SHALL reactivate the **same** person row and SHALL NOT create a new one.
  - `AC-020` — WHILE a person is terminated, the roster service SHALL serve
    their record read-only to the roles permitted by codex 07.
---

---
### REQ-006 — Role resolution
Serves **US-003** · Governed by **codex/06-PEOPLE "Roles"**, **codex/00 role ladder**

- **Inputs** — a person's active assignments, each carrying a role.
- **Outputs** — an effective role.
- **I/O mapping** — the highest role across active assignments, ordered
  `crew < shift_lead < store_manager < field_manager < office < owner`.
- **Acceptance criteria (EARS)**
  - `AC-021` — WHEN a person's effective role is requested, the roster service
    SHALL return the highest role among their active assignments.
  - `AC-022` — WHILE a person holds different roles at different stores, the
    roster service SHALL apply the per-assignment role for store-scoped
    permissions and the effective role only where a single role is required.
---

## 4 · Interface Contracts

- **CON-001 — `subway_ops.people.derive.derive_roster(*, since: date | None = None) -> DeriveResult`**
  - Expects: optional lower bound on `business_date`; defaults to all time.
  - Returns: frozen `DeriveResult(assignments_created, persons_created, incomplete_opened)`.
  - Errors: raises on unknown `restaurant_number` (FK); wrapped by `track_job`.
- **CON-002 — `subway_ops.people.wages.rate_in_force(employee_id, on: date) -> Decimal | None`**
  - Returns `None` when no wage row is in force — never `Decimal("0")`.
- **CON-003 — `subway_ops.people.wages.record_wage(*, employee_id, effective_date, hourly_rate, set_by) -> None`**
  - Error contract: `ValueError` on non-positive rate; `PermissionError` if the
    caller role is not `office` or `owner`.
- **CON-004 — `subway_ops.people.identity.merge(a, b, *, by) -> employee_id`** and
  **`split(employee_id, assignment_id, *, by) -> employee_id`**
  - Both record actor and timestamp. Shape depends on Q-001.

## 5 · Data Model

- **`ref_employees`** — `employee_id: BIGSERIAL PK` · `display_name: TEXT NOT NULL`
  · `phone: TEXT UNIQUE NULL` · `hire_date: DATE NULL` · `termination_date: DATE NULL`
  · `is_active: BOOLEAN NOT NULL DEFAULT true` · `user_email: TEXT NULL REFERENCES ref_users(email)`
  · `created_at`, `updated_at: TIMESTAMPTZ`.
- **`ref_employee_assignments`** — `assignment_id: BIGSERIAL PK` ·
  `employee_id: BIGINT NOT NULL REFERENCES ref_employees` ·
  `store_number: TEXT NOT NULL REFERENCES ref_stores` · `clerk_id: TEXT NOT NULL` ·
  `observed_name: TEXT` · `role: TEXT NOT NULL DEFAULT 'crew'` ·
  `is_active: BOOLEAN NOT NULL DEFAULT true` ·
  **`UNIQUE (store_number, clerk_id)`** — the join key back to `stg_timeclock`.
- **`ref_employee_wages`** — `employee_id` · `effective_date: DATE` ·
  `hourly_rate: NUMERIC(12,4) NOT NULL CHECK (hourly_rate > 0)` · `set_by: TEXT NOT NULL`
  · `set_at: TIMESTAMPTZ NOT NULL DEFAULT now()` · **PK `(employee_id, effective_date)`**.
- **`ops_employee_identity_log`** — append-only record of every merge and split:
  `action`, `from_employee_id`, `to_employee_id`, `assignment_id`, `actor`, `at`, `reason`.

`ref_users.role` CHECK expands to add `store_manager`, `office`, `crew`
(codex 06). This is a new migration; migrations are append-only (codex 02).

## 6 · Edge Cases

| Edge case | Expected behavior | Covered by |
|---|---|---|
| Clerk PIN reused by a different person at another store | Separate persons | Q-001 |
| Same person, same PIN, several stores | One person, many assignments | Q-001 |
| Same person, different PIN per store | One person — requires a manual merge | AC-006, Q-001 |
| Name spelling varies across stores (`singh, bir` / `bir`) | Assignment keeps observed name; person keeps display name | AC-004, Q-006 |
| Assignment appears for an unknown store | FK rejects; derivation fails loudly | REQ-001 precondition |
| Person has hours but no wage | Hours count; dollars exclude; aggregate marked partial | AC-014, AC-016 |
| Wage recorded with an earlier effective date than an existing row | Both rows stand; resolution is by date | AC-010 |
| Two wage rows for the same effective date | PK rejects the second | §5 PK |
| Terminated person clocks in again | Same person reactivated | AC-019 |
| Derivation re-run over the same window | No new rows | INV-002 |
| Crew member requests their own wage | Refused — wage is office/owner only | AC-011, Q-002 |
| Person works two stores in one week, 25h each | Reported as 50h | AC-008 |
| POS-adjusted shift (`hours_after_adj` ≠ `hours_before_adj`) | Undecided which hours cost | Q-003 |
| Salaried manager | Undecided — hourly rate may not apply | Q-004 |

## 7 · Non-Goals

- **NG-001** — Does NOT schedule anyone. Scheduling is codex 08 / SPEC-SCH-001.
- **NG-002** — Does NOT compute or approve timecards. The custody chain is
  codex 08; this spec supplies only the person and the rate.
- **NG-003** — Does NOT store certificates or training. Codex 07 / SPEC-REC-001.
- **NG-004** — Does NOT authenticate anyone. It records a phone and a nullable
  `user_email`; the login flow is SPEC-APP-001.
- **NG-005** — Does NOT purge on a retention timer. Codex 07 states seven years
  as a minimum guarantee and builds no purge.
- **NG-006** — Does NOT backfill wage history for periods before a wage was
  first recorded. Those weeks stay `partially_costed`.

## 8 · Definition of Done

All `AC-###` pass · all `INV-###` hold · no `NG-###` crossed ·
`bash scripts/verify.sh <T-id> pre-merge` exits 0 · `/audit` GREEN against the
EARS lines above · §9 fully covered.

## 9 · Traceability Matrix

| Story | Requirement | Acceptance | Task | Test |
|---|---|---|---|---|
| US-001 | REQ-001 | AC-001…AC-004 | — | — |
| US-003 | REQ-002 | AC-005…AC-008 | *blocked Q-001* | — |
| US-002 | REQ-003 | AC-009…AC-012 | — | — |
| US-004 | REQ-004 | AC-013…AC-016 | — | — |
| US-005 | REQ-005 | AC-017…AC-020 | — | — |
| US-003 | REQ-006 | AC-021, AC-022 | — | — |

Tasks and tests are filled by `/tasks` after approval.

## 10 · Open Questions & Assumptions

- `Q-001` — **How is a `(store, clerk_id)` assignment resolved to a person?**
  Blocks REQ-002, and therefore US-003 and every downstream grain. Raised as
  **B-0014**. The measured evidence is in the interview below.
- `Q-002` — **How do crew authenticate?** codex 06 says phone is the login
  identifier, but `ref_users` is email-keyed with `password_hash NOT NULL`.
  Blocks REQ-006's permission checks and SPEC-APP-001. Raised as **B-0015**.
- `Q-003` — **Which hours field costs?** `stg_timeclock` carries
  `hours_before_adj`, `hours_after_adj` and `adj_amount`; 1,369 of 19,089 rows
  (7%) differ, one by −2.48 h on an 7.98 h shift. Blocks REQ-003's labor-dollar
  contract. Raised as **B-0016**.
- `Q-004` — **Are any employees salaried?** `hourly_rate` assumes not. Blocks
  REQ-003's schema. Raised as **B-0017**.
- `Q-005` — **Is an overtime rate needed on the wage row?** codex 08 sets a
  40-hour threshold; if overtime is paid at a premium, labor dollars need a
  multiplier. Blocks REQ-003's schema. Raised as **B-0017**.
- `Q-006` — **How is a display name chosen and normalized?** Observed names are
  `LAST, FIRST` and inconsistent (`singh, bir` vs `bir`). Blocks AC-004. Raised
  as **B-0018**.

**Assumptions**

- `A-001` — `employee_name` is always present. **Verified**: 0 NULL of 19,089.
- `A-002` — Roster derivation runs nightly after `ingest_timeclock`.
  *Assumed* — depends on REQ-001's sequential logic; low risk.
- `A-003` — `stg_timeclock.clock_in` is naive `TIMESTAMP` while codex 02
  requires `TIMESTAMPTZ` UTC. **This is a code/codex disagreement**, recorded
  as **B-0019** rather than resolved. This spec does not depend on it — it uses
  `business_date` — but the deviation is real and must not be normalised by
  silence.
