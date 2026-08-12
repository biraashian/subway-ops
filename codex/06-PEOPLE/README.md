---
status: authoritative
source: founder interview 2026-08-11 (B-0006 §6)
---

# 06 — People

The widest prerequisite in the system. Scheduling, timecards, training records,
certificates, KPIs, bonuses and recognition all key on a person, and none of
them can be built until a person is a first-class row.

## A person is one record

**One person, many store assignments** (6.2).

This matters because `stg_timeclock`'s natural key is
`(clerk_id, restaurant_number)`, so an employee who covers shifts at two stores
currently appears as two unrelated clerks. Left alone, their KPI card splits in
two, their hours never sum for overtime, and their food handler card has to be
uploaded twice.

The model is therefore two tables, not one:

- `ref_employees` — the person. Stable internal id, name, phone, hire date,
  termination date, status.
- `ref_employee_assignments` — `(employee_id, store_number, clerk_id)`, one row
  per store the person works. This is the join back to `stg_timeclock`.

Everything downstream keys on the person. Hours sum across assignments; the
overtime threshold in
[08-SCHEDULING-AND-HOURS](../08-SCHEDULING-AND-HOURS/README.md) is a property of
the person, not of a store.

## Onboarding: the roster builds itself

**A stub row is auto-created on first clock-in** (6.1). An unknown `clerk_id`
appearing in `stg_timeclock` creates a `ref_employees` row plus its assignment,
populated with whatever the timeclock knows — which is the name and the store.

`stg_timeclock` already holds 250 distinct clerk ids, so the roster exists the
moment this runs. It does not have to be typed in.

A stub is **incomplete**, and incomplete is a visible state, not a silent one:
wage, role, hire date and phone are missing. Each stub raises a worklist item
(see [02-DATA-MODEL](../02-DATA-MODEL/README.md)) assigned to office. Until
completed, the person:

- counts in hours and throughput, because they genuinely worked;
- is **excluded from labor-dollar calculations**, because a missing wage is not
  a zero wage — and a store's labor cost that silently omits an employee is
  worse than one that reports "incomplete";
- cannot be scheduled, because scheduling needs a role.

Manual pre-add stays available for someone hired but not yet clocked in. The
auto-path is the default because it cannot be forgotten.

## Wages

`ref_employee_wages`, keyed `(employee_id, effective_date)`, hand-maintained
per D-020. Fresh Connect has no wage data in any of its fifteen endpoints, which
is why `mart_store_weekly.labor_cost_pct` has been NULL since it was written.

Effective-dated on the same principle as targets: a raise inserts a row, never
updates one. A week's labor dollars resolve against the rate in force that week,
so a March raise cannot rewrite February's labor cost.

A wage rate is visible to **office and owner only**. It never reaches a store
manager's view of their crew, and never reaches Discord — see
[11-COMMS](../11-COMMS/README.md).

## Identity and login

**Phone number** (6.4). Crew do not reliably have work email; they all have a
phone. Phone is the login identifier and the notification fallback.

The phone number is therefore a unique key on `ref_employees` and needs the
usual normalisation care — one canonical stored form, matched on digits.

`ref_users` (the existing dashboard-auth table, email-keyed) and
`ref_employees` are **different things**: a user is someone who signs in to
administer, an employee is someone who works. The owner, field managers and
office are both. Crew are employees who happen to get a login. The link is a
nullable `ref_employees.user_email`, not a merge.

`ref_users.role` CHECK expands to add `store_manager`, `office` and `crew` per
the ladder in [00-INSTITUTION](../00-INSTITUTION/README.md).

## Leaving

**Terminated, page read-only, records retained** (6.3).

- `termination_date` is set; `is_active` goes false.
- They stop appearing in scheduling, active rosters, and recognition.
- Their history stays in every mart. A terminated employee's hours are still
  part of last quarter's labor cost, and removing them would falsify it.
- Their page becomes read-only rather than disappearing, because the records on
  it — training, orientation, certificates — are exactly what an inspector or an
  employment claim asks for after someone has left.
- Retention is **7 years** — see
  [07-SAFETY-HEALTH-AND-RECORDS](../07-SAFETY-HEALTH-AND-RECORDS/README.md).

Nothing is deleted on termination. Per
[00-INSTITUTION](../00-INSTITUTION/README.md), corrections are new rows with a
reason.

A returning employee is the **same** `ref_employees` row reactivated, not a new
one. Their prior training and certificates are still theirs. This is another
reason the person, not the clerk id, is the identity.

## Roles

`crew` · `shift_lead` · `store_manager` · `field_manager` · `office` · `owner`.

Role is a property of an **assignment**, not of the person, because someone can
be a shift lead at one store and crew at another. Where a single role is needed
for a person — bonus eligibility, for instance — the highest role across their
active assignments wins.
