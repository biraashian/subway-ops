# === SPEC: Employee roster and wages ===

## 0 · Metadata

```yaml
spec_id:        SPEC-PPL-001
feature:        Employee roster and wages
version:        1.0.0
status:         planned
owner:          amitoj
inherits:       codex@2026-08-11
source:         codex/06-PEOPLE (greenfield; reads the existing stg_timeclock)
phase:          plan
interview:      6 Qs asked 2026-08-11, 6 decided — see §10
bound_by:
  - codex/06-PEOPLE            # the whole chapter — this spec is its implementation
  - codex/02-DATA-MODEL        # money is NUMERIC(12,4); idempotent upsert; track_job
  - codex/00-INSTITUTION       # the role ladder; "own scope and nothing above"
  - codex/03-MEASUREMENT       # the person is the employee grain
  - codex/08-SCHEDULING-AND-HOURS   # the 40-hour threshold (draft; only the threshold is used)
  - D-020                      # wages are hand-kept; FreshConnect has none
open_questions: 2              # Q-007 (labor-dollar mart), Q-008/B-0021 (AC-019 grain)
l1_plan:        design/PLAN-SPEC-PPL-001.md
```

## 1 · Intent

Make a **person** a first-class row. Today the system knows about stores and
about clerk PINs; it does not know about people. Scheduling, timecards,
training records, certificates, KPIs, bonuses and recognition all key on a
person, and none of them can be built until this exists.

Two things make this more than a CRUD table. First, the roster must **build
itself** from data already flowing — 19,089 timeclock rows land nightly and
nobody is going to type in 250 people. Second, it must carry **wages**, which
exist in no upstream system at all, and which are the missing input that has
left `mart_store_weekly.labor_cost_pct` NULL since it was written.

**Inherited non-negotiables.** A person is one record with many store
assignments (codex 06). Wages are effective-dated and never updated in place.
Money is `NUMERIC(12,4)` and `Decimal` (codex 02). Nothing is deleted on
termination (codex 00, 06). Wage visibility is office and owner only (codex 06).

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
Serves **US-001** · Governed by **codex/06-PEOPLE "the roster builds itself" (6.1A)**

- **Inputs** — `stg_timeclock`: `restaurant_number: TEXT`, `clerk_id: TEXT`,
  `employee_name: TEXT`, `business_date: DATE`.
- **Outputs** — `ref_employees`, `ref_employee_assignments`, and
  `ops_worklist_items` rows of type `employee_incomplete`.
- **I/O mapping** — a `(restaurant_number, clerk_id)` present in
  `stg_timeclock` and absent from `ref_employee_assignments` produces one
  assignment, attached to a person per REQ-002.
- **Preconditions** — `restaurant_number` exists in `ref_stores`.
- **Postconditions** — every `(restaurant_number, clerk_id)` in `stg_timeclock`
  has exactly one `ref_employee_assignments` row.
- **Invariants**
  - `INV-001` — the derivation never deletes or deactivates an assignment;
    absence from a run means "did not work", not "gone".
  - `INV-002` — re-running over the same input produces no new rows.
- **Sequential logic** — runs after `ingest_timeclock`, before mart refresh.
- **Acceptance criteria (EARS)**
  - `AC-001` — WHEN the derivation encounters a `(restaurant_number, clerk_id)`
    with no existing assignment, the roster service SHALL create one assignment
    carrying `clerk_id`, `store_number`, and the most recently seen
    `employee_name` as `observed_name`.
  - `AC-002` — WHEN the derivation runs, the roster service SHALL wrap its work
    in `track_job("derive_roster")` and set `meta["rows_written"]`.
  - `AC-003` — IF a `(restaurant_number, clerk_id)` already has an assignment,
    THEN the roster service SHALL leave its person link unchanged.
  - `AC-004` — IF `employee_name` differs from the assignment's
    `observed_name`, THEN the roster service SHALL update `observed_name` and
    SHALL NOT alter the person's `display_name`.
---

---
### REQ-002 — Resolve an assignment to a person
Serves **US-003** · Governed by **codex/06-PEOPLE "A person is one record" (6.2A)** · **Q-001 decided: B**

The linking rule is **exact `clerk_id` plus exact normalized name**. Normalized
name is `employee_name` lowercased, trimmed, with internal whitespace collapsed
to a single space.

This under-links by design. `singh, bir` and `bir` share PIN 1998 and are the
same human, and this rule will not join them — office merges them. That is the
accepted trade: **over-linking silently fuses two people's hours, wages and
certificates; under-linking is repairable by one action.** Measured basis: 56
of 250 clerk_ids carry more than one name, so `clerk_id` alone cannot identify
a person.

- **Inputs** — `(restaurant_number, clerk_id, employee_name)`.
- **Outputs** — an `employee_id`, existing or newly created.
- **Postconditions** — exactly one `ref_employees` row is associated.
- **Invariants**
  - `INV-003` — an assignment always references exactly one person.
  - `INV-004` — a person link, once established, changes only by an explicit
    office merge or split, never by a later derivation run.
- **Acceptance criteria (EARS)**
  - `AC-005` — WHEN a new assignment's `(clerk_id, normalized_name)` equals
    that of an existing assignment, the roster service SHALL link the new
    assignment to that assignment's person.
  - `AC-006` — IF no existing assignment matches on both `clerk_id` and
    `normalized_name`, THEN the roster service SHALL create a new person and
    link the assignment to it.
  - `AC-007` — WHEN office merges two persons, the roster service SHALL
    repoint every assignment of the source person at the target person, SHALL
    retain the source person's row marked merged, and SHALL append one
    `ops_employee_identity_log` row recording actor, time and reason.
  - `AC-008` — WHEN office splits an assignment from a person, the roster
    service SHALL create a new person for that assignment and SHALL append one
    `ops_employee_identity_log` row.
  - `AC-009` — WHILE a person has more than one active assignment, the roster
    service SHALL report their hours as the sum across all assignments.
  - `AC-010` — IF a merge would join two persons who each have a wage row in
    force on the same date, THEN the roster service SHALL refuse the merge and
    SHALL raise a worklist item for office, because silently discarding one
    rate would misstate historical labor cost.
---

---
### REQ-003 — Record wages, effective-dated, and resolve the costing rate
Serves **US-002** · Governed by **codex/06-PEOPLE "Wages"**, **D-020** · **Q-003/Q-004/Q-005 decided**

- **Inputs** — `employee_id`, `effective_date: DATE`,
  `hourly_rate: NUMERIC(12,4)`, `set_by: TEXT`.
- **Outputs** — a `ref_employee_wages` row; a resolved rate for a date.
- **I/O mapping** — the rate in force for a business date is the row with the
  greatest `effective_date` less than or equal to that date.
- **Preconditions** — the person exists; `hourly_rate > 0`.
- **Postconditions** — prior rows are unchanged.
- **Invariants**
  - `INV-005` — no `UPDATE` is ever issued against `ref_employee_wages`; a
    correction is a new row.
  - `INV-006` — a wage rate is readable only by `office` and `owner`.
  - `INV-007` — an absent rate resolves to `None`, never `Decimal("0")`.
- **Acceptance criteria (EARS)**
  - `AC-011` — WHEN a wage is recorded, the roster service SHALL insert a new
    row carrying `set_by` and `set_at` and SHALL NOT modify any existing row.
  - `AC-012` — WHEN a rate is requested for a business date, the roster service
    SHALL resolve the rate in force **for that date**, not the current rate.
  - `AC-013` — IF a caller whose role is not `office` or `owner` requests a
    wage, THEN the roster service SHALL refuse and SHALL NOT include the rate
    in any response body.
  - `AC-014` — IF `hourly_rate` is zero or negative, THEN the roster service
    SHALL reject the row.
  - `AC-015` — WHEN costing a shift, the roster service SHALL use
    `stg_timeclock.hours_after_adj` as the hours basis.
  - `AC-016` — WHILE a person's summed hours for a business week exceed 40, the
    roster service SHALL cost the hours beyond 40 at `hourly_rate × 1.5` and
    the first 40 at `hourly_rate`.
  - `AC-017` — IF `hours_after_adj` is NULL for a shift, THEN the roster
    service SHALL treat that shift as uncosted and SHALL mark the containing
    aggregate `partially_costed`.
---

---
### REQ-004 — Incomplete persons are visible and never costed at zero
Serves **US-004** · Governed by **codex/06-PEOPLE "A stub is incomplete"**

- **Inputs** — a `ref_employees` row and its wage history.
- **Outputs** — a completeness state; `ops_worklist_items`; a
  `partially_costed` marker on any labor-dollar aggregate.
- **I/O mapping** — a person missing any of wage, role or hire date is
  `incomplete`.
- **Invariants**
  - `INV-008` — an incomplete person's hours are **never** costed at zero.
    They are excluded from the labor-dollar sum and the sum is marked partial.
- **Acceptance criteria (EARS)**
  - `AC-018` — WHEN a person becomes incomplete, the roster service SHALL open
    one `ops_worklist_items` row assigned to `office`, and SHALL NOT open a
    duplicate while one is already open for that person.
  - `AC-019` — WHEN a labor-dollar aggregate includes hours from an incomplete
    person, the roster service SHALL exclude those hours from the dollar total
    and SHALL mark the aggregate `partially_costed` with a count of excluded
    persons.
  - `AC-020` — WHEN the last missing field is supplied, the roster service
    SHALL resolve the open worklist item.
  - `AC-021` — WHILE a person is incomplete, the roster service SHALL still
    include their hours in hours-based and throughput metrics.
---

---
### REQ-005 — Termination retains everything
Serves **US-005** · Governed by **codex/06-PEOPLE "Leaving" (6.3A)**, **codex/07 retention**

- **Invariants**
  - `INV-009` — termination never deletes a row from any table.
  - `INV-010` — a terminated person's historical hours remain in every mart.
- **Acceptance criteria (EARS)**
  - `AC-022` — WHEN a person is terminated, the roster service SHALL set
    `termination_date` and `is_active = false`.
  - `AC-023` — WHILE a person is terminated, the roster service SHALL exclude
    them from scheduling, active rosters and recognition, and SHALL continue to
    include their historical hours in past-period aggregates.
  - `AC-024` — IF a terminated person clocks in again, THEN the roster service
    SHALL reactivate the **same** person row and SHALL NOT create a new one.
  - `AC-025` — WHILE a person is terminated, the roster service SHALL serve
    their record read-only to the roles permitted by codex 07.
---

---
### REQ-006 — Identity, display name and role resolution
Serves **US-003** · Governed by **codex/06-PEOPLE "Identity and login", "Roles"** · **Q-002/Q-006 decided**

- **I/O mapping** — effective role is the highest across active assignments,
  ordered `crew < shift_lead < store_manager < field_manager < office < owner`.
- **Acceptance criteria (EARS)**
  - `AC-026` — WHEN a person is created, the roster service SHALL derive
    `display_name` as `First Last` from an `observed_name` of the form
    `LAST, FIRST`, and SHALL store the observed form unchanged on the
    assignment.
  - `AC-027` — IF `observed_name` does not parse as `LAST, FIRST`, THEN the
    roster service SHALL use it verbatim as `display_name`.
  - `AC-028` — WHEN office sets a `display_name` explicitly, the roster service
    SHALL retain it and SHALL NOT overwrite it on any later derivation run.
  - `AC-029` — WHEN a person's effective role is requested, the roster service
    SHALL return the highest role among their active assignments.
  - `AC-030` — WHILE a person holds different roles at different stores, the
    roster service SHALL apply the per-assignment role for store-scoped
    permissions and the effective role only where a single role is required.
  - `AC-031` — The roster service SHALL store `discord_user_id` and `phone` as
    nullable unique identifiers and SHALL NOT implement any authentication
    flow (see NG-004).
---

## 4 · Interface Contracts

- **CON-001 — `people.derive.derive_roster(*, since: date | None = None) -> DeriveResult`**
  - Returns frozen `DeriveResult(assignments_created, persons_created, incomplete_opened)`.
  - Errors: FK violation on unknown `restaurant_number`; wrapped by `track_job`.
- **CON-002 — `people.wages.rate_in_force(employee_id, on: date) -> Decimal | None`**
  - Returns `None` when no wage row is in force — never `Decimal("0")` (INV-007).
- **CON-003 — `people.wages.record_wage(*, employee_id, effective_date, hourly_rate, set_by) -> None`**
  - `ValueError` on non-positive rate; `PermissionError` if caller role is not
    `office` or `owner`.
- **CON-004 — `people.identity.merge(source, target, *, by, reason) -> employee_id`**
  and **`split(assignment_id, *, by, reason) -> employee_id`**
  - `ConflictError` when AC-010's overlapping-wage condition holds.
- **CON-005 — `people.cost.cost_week(employee_id, week_end: date) -> WeekCost`**
  - Returns frozen `WeekCost(regular_hours, overtime_hours, dollars, is_costed)`.
  - `is_costed = False` when the rate is absent or any shift's
    `hours_after_adj` is NULL; `dollars` is then `None`, never zero.
  - **Does not allocate the overtime premium across stores** — see NG-007.

## 5 · Data Model

- **`ref_employees`** — `employee_id: BIGSERIAL PK` · `display_name: TEXT NOT NULL`
  · `display_name_is_manual: BOOLEAN NOT NULL DEFAULT false` ·
  `phone: TEXT UNIQUE NULL` · `discord_user_id: TEXT UNIQUE NULL` ·
  `hire_date: DATE NULL` · `termination_date: DATE NULL` ·
  `is_active: BOOLEAN NOT NULL DEFAULT true` ·
  `merged_into: BIGINT NULL REFERENCES ref_employees` ·
  `user_email: TEXT NULL REFERENCES ref_users(email)` ·
  `created_at`, `updated_at: TIMESTAMPTZ`.
- **`ref_employee_assignments`** — `assignment_id: BIGSERIAL PK` ·
  `employee_id: BIGINT NOT NULL REFERENCES ref_employees` ·
  `store_number: TEXT NOT NULL REFERENCES ref_stores` · `clerk_id: TEXT NOT NULL` ·
  `observed_name: TEXT` · `normalized_name: TEXT` ·
  `role: TEXT NOT NULL DEFAULT 'crew'` · `is_active: BOOLEAN NOT NULL DEFAULT true` ·
  **`UNIQUE (store_number, clerk_id)`** — the join key back to `stg_timeclock` ·
  index on `(clerk_id, normalized_name)` for AC-005.
- **`ref_employee_wages`** — `employee_id` · `effective_date: DATE` ·
  `hourly_rate: NUMERIC(12,4) NOT NULL CHECK (hourly_rate > 0)` ·
  `set_by: TEXT NOT NULL` · `set_at: TIMESTAMPTZ NOT NULL DEFAULT now()` ·
  **PK `(employee_id, effective_date)`**.
- **`ops_employee_identity_log`** — append-only: `action` (`merge`|`split`),
  `from_employee_id`, `to_employee_id`, `assignment_id`, `actor`, `at`, `reason`.

`ref_users.role` CHECK expands to add `store_manager`, `office`, `crew`
(codex 06). New migration; migrations are append-only (codex 02).

**Overtime constant.** `OVERTIME_MULTIPLIER = Decimal("1.5")` and
`OVERTIME_THRESHOLD_HOURS = Decimal("40")` live in `subway_ops.config`, not
inline.

## 6 · Edge Cases

| Edge case | Expected behavior | Covered by |
|---|---|---|
| Clerk PIN reused by a different person at another store | Different normalized name ⇒ separate persons | AC-006 |
| Same person, same PIN and name, several stores | One person, many assignments | AC-005 |
| Same person, different PIN per store | Separate persons until office merges | AC-006, AC-007 |
| Same PIN, name spelled differently (`singh, bir` / `bir`) | Separate persons until merged — accepted under-link | AC-006, AC-007 |
| Merge would join two persons with overlapping wage rows | Refused; worklist item raised | AC-010 |
| Assignment for an unknown store | FK rejects; derivation fails loudly | REQ-001 precondition |
| Person has hours but no wage | Hours count; dollars excluded; aggregate partial | AC-019, AC-021 |
| `hours_after_adj` NULL on a shift | Shift uncosted; aggregate partial | AC-017 |
| Wage row back-dated before an existing row | Both stand; resolution is by date | AC-012 |
| Two wage rows for the same effective date | PK rejects the second | §5 PK |
| Person works 25h at each of two stores | 50h; 10h at 1.5× | AC-009, AC-016 |
| Terminated person clocks in again | Same person reactivated | AC-024 |
| Derivation re-run over the same window | No new rows | INV-002 |
| Crew member requests their own wage | Refused — office/owner only | AC-013 |
| `observed_name` not in `LAST, FIRST` form | Used verbatim | AC-027 |
| Office renamed a person, derivation runs again | Manual name retained | AC-028 |

## 7 · Non-Goals

- **NG-001** — Does NOT schedule anyone. Codex 08 / SPEC-SCH-001.
- **NG-002** — Does NOT compute or approve timecards. The custody chain is
  codex 08; this spec supplies only the person, the hours basis and the rate.
- **NG-003** — Does NOT store certificates or training. Codex 07 / SPEC-REC-001.
- **NG-004** — Does NOT authenticate anyone. It stores `discord_user_id` and
  `phone`; the Discord OAuth flow is SPEC-APP-001 (Q-002 → C).
- **NG-005** — Does NOT purge on a retention timer. Codex 07 states seven years
  as a minimum guarantee and builds no purge.
- **NG-006** — Does NOT support salaried employees. Q-004 established that all
  employees are hourly. A salaried hire is a schema change and a new spec.
- **NG-007** — Does NOT allocate the overtime premium across stores. It returns
  a per-person weekly cost. Splitting that across the stores a person worked is
  the labor-dollar mart's problem — see Q-007.

## 8 · Definition of Done

All `AC-###` pass · all `INV-###` hold · no `NG-###` crossed ·
`bash scripts/verify.sh <T-id> pre-merge` exits 0 · `/audit` GREEN against the
EARS lines above · §9 fully covered.

## 9 · Traceability Matrix

| Story | Requirement | Acceptance | Task | Test |
|---|---|---|---|---|
| US-001 | REQ-001 | AC-001…AC-004 | — | — |
| US-003 | REQ-002 | AC-005…AC-010 | — | — |
| US-002 | REQ-003 | AC-011…AC-017 | — | — |
| US-004 | REQ-004 | AC-018…AC-021 | — | — |
| US-005 | REQ-005 | AC-022…AC-025 | — | — |
| US-003 | REQ-006 | AC-026…AC-031 | — | — |

Tasks and tests are filled by `/tasks`.

## 10 · Open Questions & Assumptions

**Decided in the interview of 2026-08-11:**

- `Q-001` → **decided B.** Link on exact `clerk_id` + exact normalized name;
  everything else separate, merge available. Folded into REQ-002. B-0014 closed.
- `Q-002` → **decided C.** Discord OAuth, with phone as fallback for anyone not
  on Discord. PPL stores both identifiers; the flow is SPEC-APP-001. Folded
  into AC-031 and NG-004. B-0015 closed.
- `Q-003` → **decided A.** `hours_after_adj` is the costing basis. Folded into
  AC-015. B-0016 closed.
- `Q-004` → **decided: all hourly.** No salary support. Folded into NG-006.
- `Q-005` → **decided A.** 1.5× beyond 40 hours per person per business week,
  matching WA/OR law. Folded into AC-016. B-0017 closed.
- `Q-006` → **decided A.** Derive `First Last`, office may override. Folded
  into AC-026…AC-028. B-0018 closed.

**Still open:**

- `Q-007` — **Which store bears the overtime premium when a person crosses 40
  hours across two stores?** Created by Q-005 combined with codex 06's
  one-person-many-assignments rule: 25h at store A and 25h at store B is 10
  overtime hours, and the premium has to land somewhere. Candidates:
  chronological (the hours after the 40th, wherever worked), pro-rata by hours,
  or wholly to the store where the crossing occurred. **Blocks the labor-dollar
  mart, not this spec** — CON-005 returns a per-person weekly cost and NG-007
  fences the allocation out. Raised as **B-0020**.

**Assumptions**

- `A-001` — `employee_name` is always present. **Verified**: 0 NULL of 19,089.
- `A-002` — Roster derivation runs nightly after `ingest_timeclock`. *Assumed*;
  low risk.
- `A-003` — `stg_timeclock.clock_in` is naive `TIMESTAMP` while codex 02
  requires `TIMESTAMPTZ` UTC. A genuine code/codex disagreement, recorded as
  **B-0019** rather than resolved. This spec does not depend on it — it keys on
  `business_date` — but codex 08's clock-versus-schedule comparison will, across
  a DST boundary.

- `Q-008` — **What grain does AC-019's "labor-dollar aggregate" mark
  `partially_costed` at?** codex 03 says a metric without a stated grain is a
  gap. Read by the L1 plan as per person per business week, since `CON-005` is
  the only aggregate this spec produces; store-level marking rides with the
  labor-dollar mart. Blocks nothing — the design does not depend on the answer.
  Raised as **B-0021**.
