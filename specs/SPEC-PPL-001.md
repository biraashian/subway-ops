# === SPEC: Employee roster and wages ===

## 0 · Metadata

```yaml
spec_id:        SPEC-PPL-001
feature:        Employee roster and wages
version:        1.6.0
status:         tasked
owner:          amitoj
inherits:       codex@2026-08-11
source:         codex/06-PEOPLE (greenfield; reads the existing stg_timeclock)
phase:          tasks
interview:      6 Qs asked 2026-08-11, 6 decided — see §10
bound_by:
  - codex/06-PEOPLE            # the whole chapter — this spec is its implementation
  - codex/02-DATA-MODEL        # money is NUMERIC(12,4); idempotent upsert; track_job
  - codex/00-INSTITUTION       # the role ladder; "own scope and nothing above"
  - codex/03-MEASUREMENT       # the person is the employee grain
  - codex/08-SCHEDULING-AND-HOURS   # the 40-hour threshold (draft; only the threshold is used)
  - D-020                      # wages are hand-kept; FreshConnect has none
open_questions: 0              # Q-007/Q-008 decided 2026-08-13 (B-0020, B-0021);
                               # Q-009/Q-010 decided 2026-08-17 (B-0032, B-0033);
                               # Q-011 decided 2026-08-17 (B-0034);
                               # Q-012 decided 2026-08-18 (B-0037);
                               # Q-013/Q-014/Q-015 decided 2026-08-18 (B-0038/39/40)
                               # AC-018 amended 2026-08-13 by D-029 (B-0025)
l1_plan:        design/PLAN-SPEC-PPL-001.md
build_sheet:    T-0003 … T-0009 (7 tasks)
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
    carrying `clerk_id`, `store_number`, and the most recently seen **non-blank**
    `employee_name` as `observed_name` (D-044). Ties within a business date are
    broken by `clock_in`, latest first.
  - `AC-001a` — IF a pair has never carried a non-blank `employee_name`, THEN the
    roster service SHALL set `display_name` to `Clerk <clerk_id> (unnamed)`,
    leave `normalized_name` empty, and link on that empty key like any other
    value (D-044). A blank display name is never written.
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
    assignment to that assignment's person. **"Existing" means the state after
    every rename in this run has been applied** (D-043): the derivation runs two
    passes, renames first and resolution second, so a name corrected at one
    store earlier in a run is visible to a link at another store later in it.
    Resolution SHALL be deterministic when more than one assignment matches.
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
  - `INV-006` — a wage rate is readable only by `office` and `owner` **through
    the library's guarded accessor `read_wage` (CON-006)**. Scoped by D-037:
    `rate_in_force` is an unguarded internal resolver and `cost_week` exposes
    the rate by division, so any human-facing surface must call `read_wage` or
    enforce the role itself. The invariant states what the library actually
    guarantees rather than more.
  - `INV-007` — an absent rate resolves to `None`, never `Decimal("0")`.
- **Acceptance criteria (EARS)**
  - `AC-011` — WHEN a wage is recorded, the roster service SHALL insert a new
    row carrying `set_by` and `set_at` and SHALL NOT modify any existing row.
  - `AC-012` — WHEN a rate is requested for a business date, the roster service
    SHALL resolve the rate in force **for that date**, not the current rate.
  - `AC-012a` — WHEN costing a business week, the roster service SHALL resolve
    the rate **per shift**, at the rate in force on that shift's own
    `business_date`, and SHALL NOT price the whole week at a single date's rate
    (D-036). A raise landing mid-week therefore prices the hours before it at
    the old rate and the hours after it at the new one.
  - `AC-013` — IF a caller whose role is not `office` or `owner` calls a
    **guarded wage entry point** — `record_wage` (CON-003) or `read_wage`
    (CON-006) — THEN the roster service SHALL refuse and SHALL NOT include the
    rate in any response body. Amended by D-037: the guard names specific entry
    points because `rate_in_force` (CON-002) is an internal resolver whose
    signature carries no actor, and `cost_week` is a mart path from which the
    rate is recoverable by division regardless.
  - `AC-014` — IF `hourly_rate` is zero or negative, THEN the roster service
    SHALL reject the row.
  - `AC-015` — WHEN costing a shift, the roster service SHALL use
    `stg_timeclock.hours_after_adj` as the hours basis.
  - `AC-016` — WHILE a person's summed hours for a business week exceed 40, the
    roster service SHALL cost the hours beyond 40 at `hourly_rate × 1.5` and
    the first 40 at `hourly_rate`. Per D-036 the applicable `hourly_rate` is
    per shift, and the hours beyond 40 are identified as in Q-007 — the hours
    after the 40th, ordered by `clock_in`. Only Q-007's **ordering** is used
    here; its store attribution stays fenced out by NG-007.
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
    duplicate while an item for that person is in a suppressing state. Per
    **D-029** the suppressing states are `open`, `in_progress` and `dismissed`;
    `resolved` does not suppress, so a person who becomes incomplete again
    raises a fresh item. Office dismissing an item is durable — the sweep does
    not overrule it — and reopening is SPEC-APP-001's.
  - `AC-019` — WHEN a **per-person, per-business-week** labor-dollar figure
    includes hours from an incomplete person, the roster service SHALL exclude
    those hours from the dollar total and SHALL mark that figure
    `partially_costed` with a count of excluded persons. Store- and
    territory-level rollups of `partially_costed` are the labor-dollar mart's
    concern, not this spec's.
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
    SHALL reactivate the **same** person row — setting `is_active = true` and
    **clearing `termination_date`** (D-041) — and SHALL NOT create a new one.
    Clearing the date is deliberate: it keeps `termination_date IS NULL` a
    truthful test for "currently employed". The accepted cost is that the
    previous departure date is overwritten and not recoverable from the row.
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

- **CON-001 — `people.derive.derive_roster(*, since: date | None = None, stores: list[str] | None = None) -> DeriveResult`**
  - `stores` restricts the scan to the named `restaurant_number`s; `None` scans
    all (D-042). DB-integration tests pass their synthetic stores, which is what
    makes codex 13's isolation rule enforceable rather than aspirational.
  - Returns frozen `DeriveResult(assignments_created, persons_created, incomplete_opened)`.
  - Errors: FK violation on unknown `restaurant_number`; wrapped by `track_job`.
- **CON-002 — `people.wages.rate_in_force(employee_id, on: date) -> Decimal | None`**
  - Returns `None` when no wage row is in force — never `Decimal("0")` (INV-007).
  - **Unguarded and internal** (D-037): no actor, for marts and `cost_week`.
    Human-facing reads use CON-006.
- **CON-003 — `people.wages.record_wage(*, employee_id, effective_date, hourly_rate, set_by) -> None`**
  - `ValueError` on non-positive rate; `PermissionError` if caller role is not
    `office` or `owner`.
- **CON-004 — `people.identity.merge(source, target, *, by, reason) -> employee_id`**
  and **`split(assignment_id, *, by, reason) -> employee_id`**
  - `ConflictError` when AC-010's overlapping-wage condition holds.
- **CON-006 — `people.wages.read_wage(employee_id, on: date, *, actor_role: str) -> Decimal | None`**
  - The guarded human-facing read (D-037). `PermissionError` for any role other
    than `office` or `owner`; the message never contains the rate (AC-013).
  - Same resolution as CON-002 otherwise, including `None` for an absent rate.
- **CON-005 — `people.cost.cost_week(employee_id, week_end: date) -> WeekCost`**
  - Returns frozen `WeekCost(regular_hours, overtime_hours, dollars, is_costed)`.
  - Costs **per shift** at each shift's own in-force rate (D-036, AC-012a).
  - Unguarded: a mart path with no human actor (D-037).
  - `is_costed = False` when the rate is absent or any shift's
    `hours_after_adj` is NULL; `dollars` is then `None`, never zero.
  - **`is_costed = True` asserts that the rate is known** (D-038), not merely
    that nothing contradicted it. A week with **no shifts at all** therefore
    still resolves a rate — at `week_finish` — and is `is_costed = False` with
    `dollars = None` when none is in force, even though zero hours would cost
    zero at any rate.
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
| **Raise effective mid-week, hours worked either side** | Each shift costed at the rate in force on its own `business_date`; the week is never priced at one date's rate | AC-012a, D-036 |
| **A business week with no shifts at all** | Rate still resolved at `week_finish`; no rate in force ⇒ `dollars=None`, `is_costed=False` — never a confident `$0` | CON-005, D-038 |
| **Crew or store manager calls a guarded wage entry point** | `PermissionError`; the rate appears nowhere in the message | AC-013, CON-006 |
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
| Terminated person clocks in again | Same person reactivated: `is_active=true`, `termination_date` cleared | AC-024, D-041 |
| Derivation re-run over the same window | No new rows | INV-002 |
| Name corrected at store A, same PIN+name first seen at store B, one run | One person — resolution sees the rename (two passes) | AC-005, D-043 |
| `employee_name` blank or absent | Last non-blank name used; never-named pairs get `Clerk <id> (unnamed)` | AC-001a, D-044 |
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

| Story | Requirement | Acceptance | Task | Status |
|---|---|---|---|---|
| US-001 | REQ-001 | AC-001…AC-004 | T-0006 | queued |
| US-003 | REQ-002 | AC-005, AC-006 | T-0006 | queued |
| US-003 | REQ-002 | AC-007…AC-010 | T-0008 | queued |
| US-002 | REQ-003 | AC-011, AC-014 | T-0004 (schema), T-0007 (code) | **merged** — T-0004 2026-08-13 (schema), T-0007 2026-08-17 (code) |
| US-002 | REQ-003 | AC-012, AC-012a, AC-013, AC-015…AC-017 | T-0007 | **merged 2026-08-17** |
| US-004 | REQ-004 | AC-018, AC-020 | T-0003 (mechanism), T-0009 (people) | **T-0003 merged 2026-08-13** — mechanism only; the people half is T-0009 |
| US-004 | REQ-004 | AC-019, AC-021 | T-0009 | queued |
| US-005 | REQ-005 | AC-022 | T-0004 | **merged 2026-08-13** |
| US-005 | REQ-005 | AC-023, AC-025 | T-0008 | queued |
| US-005 | REQ-005 | AC-024 | T-0006 | queued |
| US-003 | REQ-006 | AC-026, AC-027, AC-029, AC-030 | T-0005 | **merged 2026-08-17** |
| US-003 | REQ-006 | AC-028 | T-0006 | queued |
| US-003 | REQ-006 | AC-031 | T-0004 | **merged 2026-08-13** |

Coverage verified both ways: 31 of 31 ACs land in at least one task; every task
carries at least one AC; no task cites an AC this spec does not define. Tests
are named in each task file.

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

- `Q-009` → **decided A (B-0025) 2026-08-13.** Raised by the `/audit` of T-0003
  rather than by the interview: AC-018 said "while one is already open" without
  saying which of codex 02's four states count as open. `dismissed` now
  suppresses alongside `open` and `in_progress`; `resolved` does not. Folded into
  AC-018. Policy is **D-029**, because the state machine belongs to the worklist
  table rather than to this spec.
- `Q-010` → **decided C (B-0026) 2026-08-13.** Also from the T-0003 audit: the
  worklist shape carries `resolved_at` but not `resolved_by`, and
  `resolve_item(kind, subject_ref) -> int` takes no actor. Policy is **D-030**;
  codex 02's stated shape was amended to match.

**Still open:**

- `Q-013` — **How do DB-integration tests avoid deriving the real roster?**
  Raised by the `/audit` of T-0006 after the suite ran the real derivation
  against production — 405 assignments and 342 persons, written by a job the
  task file had explicitly deferred to T-0009. **DECIDED 2026-08-18 → A
  (B-0038):** `CON-001` gains a `stores` filter. The rows were deleted on
  founder instruction so T-0009 performs the first real run as designed.
  Recorded as D-042.

- `Q-014` — **Does AC-005 resolve against the run-start state or the current
  one?** **DECIDED 2026-08-18 → C (B-0039):** two passes, renames before
  resolution, plus a deterministic ordering. Recorded as D-043. A run-start
  snapshot left two assignments sharing an identity key pointing at two people,
  permanently.

- `Q-015` — **What happens when `employee_name` is blank?** **DECIDED
  2026-08-18 → C over B (B-0040):** carry the last non-blank name; a
  never-named pair becomes `Clerk <id> (unnamed)`. Recorded as D-044. The build
  had invented three defaults here without flagging them.

- `Q-012` — **On rehire, is `termination_date` cleared?** Raised by T-0006's
  build, which halted rather than choosing. AC-024 said "reactivate the same
  row" and named no columns; codex 06 "Leaving" confirms the row identity and is
  equally silent. **DECIDED 2026-08-18 → A (B-0037):** clear it, as the inverse
  of AC-022. Recorded as D-041. Option C (log the reactivation) was declined by
  Burst on the grounds that `ops_employee_identity_log` is shaped for identity
  repair, not lifecycle.

- `Q-011` — **What does a week with no shifts cost?** Raised by the second
  `/audit` of T-0007. `cost_week` consulted the wage table only for dates
  carrying shifts, so an empty week returned `Decimal("0")` with
  `is_costed=True` — including for an `employee_id` that does not exist.
  **DECIDED 2026-08-17 → B (B-0034):** resolve at `week_finish` even with no
  shifts; absent rate ⇒ `None` / `False`. Recorded as D-038. The flag now means
  "the rate is known".

- `Q-009` — **Which date inside a business week resolves the wage rate?**
  Raised by the `/audit` of T-0007, not by the interview: AC-012 defined
  resolution for a *date* and nothing said which date stood for a *week*. The
  build filled it with `week_finish`, overstating a mid-week-raise week by 50%
  on a live probe. **DECIDED 2026-08-17 → A (B-0032): pro-rate per shift.**
  Recorded as D-036; AC-012a added. Which rate the premium multiplies follows
  from Q-007's `clock_in` ordering, so no new question was opened.

- `Q-010` — **Is the wage guard on the write, the read, or both?** Also from the
  T-0007 audit: AC-013 and INV-006 name a read, and CON-002 gave it no actor to
  check. **DECIDED 2026-08-17 → C (B-0033): two accessors.** `rate_in_force`
  stays unguarded and internal; `read_wage` (CON-006) is the guarded
  human-facing read. `cost_week` stays unguarded because the rate is recoverable
  from it by division either way, and INV-006 is scoped to say so. Recorded as
  D-037.

- `Q-007` — **Which store bears the overtime premium when a person crosses 40
  hours across two stores?** Created by Q-005 combined with codex 06's
  one-person-many-assignments rule: 25h at store A and 25h at store B is 10
  overtime hours, and the premium has to land somewhere. Candidates:
  chronological (the hours after the 40th, wherever worked), pro-rata by hours,
  or wholly to the store where the crossing occurred. **DECIDED 2026-08-13 → A
  (B-0020): chronological.** The premium lands on whichever store the person
  was working when the hours past the 40th occurred, ordered by `clock_in`.
  It is the only rule that survives a store manager asking "why is my store
  carrying that?", and the data already supports it because `clock_in` orders
  shifts across assignments.

  Still fenced out of *this* spec by NG-007: `CON-005` returns a per-person
  weekly figure, and the allocation is applied by the labor-dollar mart. The
  decision is recorded here so that mart's spec inherits it rather than
  re-deciding.

**Assumptions**

- `A-001` — `employee_name` is always present. **Verified**: 0 NULL of 19,089.
- `A-002` — Roster derivation runs nightly after `ingest_timeclock`. *Assumed*;
  low risk.
- `A-003` — `stg_timeclock.clock_in` is naive `TIMESTAMP` while codex 02
  requires `TIMESTAMPTZ` UTC. A genuine code/codex disagreement, recorded as
  **B-0019** rather than resolved. This spec does not depend on it — it keys on
  `business_date` — but codex 08's clock-versus-schedule comparison will, across
  a DST boundary.

- `Q-008` — **DECIDED 2026-08-13 → B (B-0021).** AC-019 now names its grain
  explicitly: per person, per business week. Same behavior as the L1 plan
  already assumed; the AC is no longer ambiguous to the next reader.
