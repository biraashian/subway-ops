# Bench — Open Founder Decisions

Drained by `/bench`, one sitting per founder window. Decided policy-shaped
items also append to `DECISIONS.md`. Format: see root `CLAUDE.md`.

---

### B-0044 — `test_mart_field_manager_portfolio.py` was never namespaced; two concurrent runs still destroy each other
Task: T-0016 (audit) · Blocks: D-040's AC ("every DB-backed test file") · Raised: 2026-08-19

**Specified.** T-0016 `ACCEPTANCE_CRITERIA.behaviors`, quoting D-040: "every
DB-backed test file mixes a per-SESSION token into its namespace marker;
teardown deletes only rows carrying THIS run's token", and "two concurrent runs
of the full suite both pass".

**Observed.** `tests/test_mart_field_manager_portfolio.py` carries file-scoped
markers that were left untouched:

```python
FM_NAME = "TestPortfolioFM"        # not ns()-wrapped
for sn in ("T1", "T2", "T3"):      # not ns()-wrapped
...
execute_sql("DELETE FROM ref_stores WHERE store_number IN ('T1','T2','T3')")
```

The file WAS opened by this task — it received D-046's conditional field-manager
teardown — so this is a file the builder edited and did not namespace. The
journal names only the shared `TestFM` row as the remaining gap; this file uses
its own `TestPortfolioFM` and is a separate, unrecorded gap.

**Reproduced, 2026-08-19, at `e38f819`:**

```
serial      : 5 passed in 23.52s
concurrent  : run A  3 passed, 2 errors  (IntegrityError on the shared T1/T2/T3)
              run B  1 failed, 4 passed  (test_null_food_pct_does_not_drag_average_to_zero)
```

That is B-0036's signature unchanged, in a file T-0016 was scoped to fix.

**Also un-namespaced, not reproduced:** `tests/test_backfill.py` uses
`name = "_bf_test"` with a teardown deleting `ops_backfill_progress WHERE
endpoint = '_bf_test'`. Two concurrent runs passed when tried, so it is a latent
hazard rather than a demonstrated failure — but it is the same shape and it is
not named anywhere in the task's record. The seven ingest files are deliberately
excluded by D-045 and are not counted here.

Options:
  A) **Namespace both files in T-0016** — `ns()` on `FM_NAME`, `T1/T2/T3` and
     `_bf_test`, plus `is_active=false` on the three portfolio stores (they are
     seeded `true` today, see B-0043). Small, local, closes the AC as written.
  B) **Narrow the AC to the files T-0016 actually covered** and mint a follow-up
     for the rest. Honest, but leaves a gate that can still contradict itself,
     which is the failure D-040 exists to remove.
  C) **Defer both to T-0017** with the ingest seven and the shared-`TestFM`
     redesign (B-0042 option C), on the argument that they are one pass.
Burst recommends: **A** — it is two files and roughly six lines, the machinery
already exists, and shipping D-040 with a file that still fails concurrently
spends the decision's whole point. [recommendation, not a decision]
Status: OPEN

### B-0043 — T-0016 leaks an `is_active = true` synthetic store into production `ref_stores` on every run
Task: T-0016 (audit) · Blocks: T-0016 merge · Raised: 2026-08-19

**Specified.** T-0016 `FORBIDDEN_ACTIONS`: "do not seed a synthetic store with
`is_active=true` — the ingests would pick it up, which is the second half of the
convention and the reason it exists." `codex/13-BUILD/CONVENTIONS.md`: "Use a
synthetic identifier and seed it `is_active=false`." D-039's AC names
`is_active=false` explicitly.

**Observed.** Four files that T-0016 moved off real store `4092` seed their new
synthetic store **active**, and none of them delete it:

```
tests/test_mart_store_daily.py       tests/test_dashboard_recon_page.py
tests/test_mart_store_weekly.py      tests/test_dashboard_store_detail.py

  INSERT INTO ref_stores
    (store_number, ..., field_manager_name, is_active)
  VALUES (:s, ..., 'TestFM', true)          -- true
  ON CONFLICT (store_number) DO NOTHING
```

Their `_wipe()` deletes staging and mart rows scoped by store and date. **Not
one of the four contains a `DELETE FROM ref_stores`.**

**Why the change made this reachable.** On `main` these files used
`TEST_STORE = "4092"`, a store that already exists, so `ON CONFLICT DO NOTHING`
fired and the INSERT was a no-op — nothing was created, so nothing needed
removing. T-0016 changed the constant to `ns("T-4092")`, which does not exist,
so the INSERT now succeeds and creates a **new active store that no teardown
removes**. This is the same shape as B-0042: a real-store violation was holding
a latent defect shut, and correcting the violation opened it — except this one
writes to production and was not caught.

**Measured live, 2026-08-19, at `e38f819`:**

```
before   ref_stores LIKE 'T-%'  →  T-4092-85034129fdd  is_active = true
$ uv run pytest tests/test_mart_store_daily.py -q   →  4 passed
after    ref_stores LIKE 'T-%'  →  T-4092-85034129fdd  is_active = true
                                   T-4092-8915171b18   is_active = true   ← new

$ python -c "from subway_ops.ingest.daily_sales import _active_store_numbers; ..."
  ingest would call: ['T-4092-85034129fdd', 'T-4092-8915171b18']
```

The suite passes and leaves the row behind. `_active_store_numbers()` in all
five ingests is `SELECT store_number FROM ref_stores WHERE is_active = true`, so
the nightly pull will request these store numbers from the POS API from now on.
One row accrues per pytest process, forever; the task's own RESUME block
instructs a human to "clear residue... `ref_stores LIKE 'T-%'`" before running
the gate, which is the leak being worked around by hand rather than fixed.

**Second-order: it also invalidates D-046's accepted cost.** D-046 accepted that
`TestFM` "lingers whenever another file's store outlives the deleter" on the
grounds that "the next run that owns the last referencing store clears it".
Those leaked stores reference `TestFM` and are never deleted, so the
`NOT EXISTS` guard is now permanently false and `TestFM` can never be torn down:

```
ref_stores WHERE field_manager_name = 'TestFM'
  T-4092-8915171b18 | TestFM | true
  T-4092-85034129fdd | TestFM | true
```

The decision is not wrong, but the fact it rests on is no longer true.

**`test_synthetic_stores_are_inactive_and_removed` does not cover this.** It
exercises `conftest.synthetic_store_factory`, which does seed `false` and does
drop its stores. The four files hand-roll their own INSERT and never call the
factory, so the guard passes while the violation stands — a guard reading as
assurance for code it does not touch.

Options:
  A) **Flip the four to `is_active=false` and add `DELETE FROM ref_stores` to
     each teardown.** Four files, two lines each. Requires checking that nothing
     in those suites depends on the store being active (the mart refreshes are
     driven off staging rows, not `ref_stores.is_active` — worth confirming, not
     assuming).
  B) **A, plus route the four through `conftest.synthetic_store_factory`** so
     there is one place that knows how a test store is made and unmade, and the
     existing isolation test actually guards them.
  C) **Widen `test_synthetic_stores_are_inactive_and_removed`** into a guard that
     fails if any `test_*.py` inserts `ref_stores` with `is_active` true, so the
     next hand-rolled fixture cannot reintroduce this.
Burst recommends: **B + C** — B fixes the four sites and removes the duplicate
fixture that caused them to drift, C makes the guard cover what its name claims.
Whichever is chosen, the two rows now live in production `ref_stores`
(`T-4092-85034129fdd`, `T-4092-8915171b18`) need a founder-approved cleanup;
the audit did not delete them. [recommendation, not a decision]
Status: OPEN

### B-0042 — `TestFM` is a shared row with per-file teardown, and T-0016 unmasked it
Task: T-0016 (HALTED, R-503) · Blocks: T-0016 · Raised: 2026-08-18

**Observed.** Three consecutive pre-merge runs failed the same check with the
same seven errors in `test_mart_recon_weekly.py`:

```
ForeignKeyViolation: update or delete on table "ref_field_managers" violates
  constraint "ref_stores_field_manager_name_fkey" on table "ref_stores"
DETAIL: Key (name)=(TestFM) is still referenced from table ref_stores.
```

**Cause, and it is T-0016's own change.** About a dozen test files insert a
shared field manager `TestFM` (`ON CONFLICT (name) DO NOTHING`) and several
delete it in teardown. Four of them also inserted a store referencing it:

```sql
INSERT INTO ref_stores (store_number, ..., field_manager_name, ...)
VALUES ('4092', ..., 'TestFM', true)
ON CONFLICT (store_number) DO NOTHING
```

Store `4092` is real — it is Bothell, and its actual field manager is
**Sokhavy**. So `DO NOTHING` fired every time, **no row ever referenced
`TestFM`**, and deleting the field manager always succeeded. The dependency was
masked by the very codex 13 violation T-0016 was fixing.

D-039 replaced `4092` with a synthetic `T-4092-<token>`, which does not exist,
so the INSERT now succeeds — and a store referencing `TestFM` exists while
another file's teardown tries to delete it.

This is a correct fix surfacing a latent defect, not a new one. The teardown
ordering has been wrong since these files were written; nothing could reach it.

**Why this is benched and not pushed through.** R-503: three consecutive
failures of the same check. Each had a specific diagnosis — leftover rows, then
a unique index on `email` I had not looked at, then this — and I fixed two of
them. The third says the shape is wrong, not the attempt. Every remaining option
touches roughly a dozen files that no part of T-0016 was scoped to change, and
one of them overlaps B-0041's seven.

Options:
  A) **Teardown deletes the field manager only if unreferenced** —
     `DELETE ... WHERE NOT EXISTS (SELECT 1 FROM ref_stores WHERE
     field_manager_name = :f)`. One line per teardown site, no shared-state
     redesign, immediately unblocks T-0016. Leaves a `TestFM` row lingering
     whenever another file's store outlives the deleter, which is untidy but
     harmless and self-clears.
  B) **Each file owns its own namespaced field manager** — `TestFM-<token>`
     per file, email namespaced with it (the email has its own UNIQUE index;
     namespacing the name alone was failure #2). Correct and consistent with
     D-040. About a dozen files.
  C) **One shared fixture owns `TestFM`'s whole lifecycle** — session-scoped in
     `conftest.py`, created once, deleted at session end, never by an individual
     file. Removes the ordering problem by removing the per-file teardown.
     Cleanest long-term shape; touches every file that currently manages it.
  D) **Revert T-0016's store rename** for those four files, back to real `4092`.
     Restores the masking and unblocks immediately — and re-introduces the codex
     13 violation the task exists to remove. Recorded for completeness; I would
     not take it.
Burst recommends: **A now to unblock T-0016, C when B-0041's seven files are
addressed** — they are the same dozen files and the same shared-fixture problem,
and doing them twice is the only way to make this cost more than it already has.
[recommendation, not a decision]
Status: **DECIDED 2026-08-18 → A.** Teardown deletes the shared field manager
only when nothing references it:
`DELETE FROM ref_field_managers WHERE name = :f AND NOT EXISTS
 (SELECT 1 FROM ref_stores WHERE field_manager_name = :f)`.
One line per teardown site, no shared-state redesign, unblocks T-0016. Accepted
cost: a `TestFM` row lingers whenever another file's store outlives the deleter —
harmless, and the next run that owns the last store clears it. Recorded as
**D-046**; folded into T-0016's DELIVERABLES.
**C is still the right shape** and is deliberately deferred to sit with B-0041's
seven files, because they are the same dozen files and the same shared-fixture
problem. Doing them separately is the only way to pay for this twice.

### B-0041 — Seven ingest test files delete a real store's staging history on every run
Task: T-0016 (found during build; beyond its DELIVERABLES) · Blocks: nothing today; the deletions are already happening · Raised: 2026-08-18

**Specified.** `codex/13-BUILD/CONVENTIONS.md`: "**Never point a test at a real
store number.** Use a synthetic identifier and seed it `is_active=false`." The
chapter states why in the first person — it was written after
`test_mart_recon_weekly.py` was found hard-deleting a real store's history on
every run for three months.

**Observed.** Seven ingest test files hardcode real store **`4092` (Bothell,
`is_active = true`)**, seed `ref_stores` for it, and tear down with deletes that
are **not scoped by date**:

```
tests/test_ingest_controlsheet.py        tests/test_ingest_wisr.py
tests/test_ingest_daily_sales.py         tests/test_ingest_paidouts.py
tests/test_ingest_timeclock.py           tests/test_ingest_inventory_movement.py
tests/test_ingest_third_party_daily.py

  DELETE FROM stg_no_sales  WHERE restaurant_number = '4092'
  DELETE FROM stg_paid_outs WHERE restaurant_number = '4092'
```

No date predicate. Every run removes **all** of that store's rows in those
tables.

**What the data looks like now.** 4092 is a real store with real data — it has
453 rows in `stg_daily_sales`, whose test teardown *is* date-scoped. In the
tables whose teardown is not scoped, it has none, while all thirteen other
stores do:

```
stg_daily_sales   6097 rows   14 stores   4092: 453   (teardown scoped by date)
stg_timeclock    19339 rows   13 stores   4092:   0   (4092 absent entirely)
stg_no_sales     54675 rows   13 stores   4092:   0   (unscoped DELETE)
stg_paid_outs      387 rows   13 stores   4092:   0   (unscoped DELETE)
```

**Stated carefully: this is consistent with the tests having destroyed Bothell's
history, and it is not proof.** 4092 may never have had `no_sales` or
`paid_outs` data — the ingests may simply never have run for it. What *is*
certain is the mechanism: every execution of these tests deletes every row that
store has in those tables, and nothing anywhere records that it happened. The
absence pattern matching exactly the tables with unscoped deletes is why this is
worth your attention rather than a footnote.

**Why it is a bench item and not a rework note.** It is outside T-0016's
DELIVERABLES — seven files, each with its own staging tables, fixtures and date
constants — and the first question is not technical. If the data was lost, that
is a recovery question about a real store's operating history, not a test
cleanup.

Note also: T-0016's guard `test_no_db_test_selects_a_real_store_number` does
**not** catch this. It looks for `SELECT store_number FROM ref_stores`, and
these files hardcode the literal. The guard has been renamed and its docstring
now says what it does not cover, so it stops implying more than it enforces.

Options:
  A) **Fix the seven files** — synthetic store per file, `is_active=false`,
     namespaced per run like everything else T-0016 touched. Mechanical, roughly
     triples T-0016's size, and stops the deletions immediately.
  B) **Scope the deletes by date first** (a one-line change per site), then fix
     the files properly later. Stops the bleeding today for far less work; leaves
     seven files still pointing at a real store.
  C) **Wait for T-0011** (D-025, containerised Postgres) — the whole class
     disappears when tests stop touching production. Correct in the end state,
     but T-0011 is founder-paired and unscheduled, and the deletions continue
     every time the suite runs until it lands.
Burst recommends: **B now, A with or just before T-0011.** B is minutes of work
and removes the destructive property; A is the real fix but should not be
smuggled into a task scoped to something else. Separately, and independent of
which option you take: **someone should establish whether Bothell's `no_sales`
and `paid_outs` history ever existed**, because if it did, that is a data-loss
incident and this bench item is the wrong container for it.
[recommendation, not a decision]
Status: **DECIDED 2026-08-18 → B.** Every unscoped
`DELETE ... WHERE restaurant_number = '4092'` gains a date predicate now, so the
destructive property is gone today for minutes of work. The seven files still
point at a real store; that is **T-0017**, timed with or just before T-0011.
Recorded as **D-045**; the date-scoping is folded into T-0016's DELIVERABLES
because it is the same test-hygiene surface already open.
**Separately, and not a code question:** whether Bothell's `stg_no_sales` and
`stg_paid_outs` history ever existed is unresolved and is on the board under
"Needs you". If it did, this bench item is the wrong container for it.

### B-0038 — The test suite ran the real derivation against the live database; `derive_roster` has no way to be scoped to synthetic stores
Task: T-0006 (audit failed) · Blocks: REQ-001/AC-001, AC-005, AC-006, INV-002 — their evidence · Raised: 2026-08-18

**Specified.** T-0006's NOTES: "Do NOT run this against production during the
build. Use synthetic stores seeded `is_active=false` (codex 13). **The first real
run is T-0009's concern** and will create roughly 399 assignments and 250-399
persons." CON-001 is `derive_roster(*, since: date | None = None)` — `since` is
the only knob, and it narrows by date, not by store.

**Observed.** The first real run has already happened, from inside the test
suite, on 2026-08-18 at 18:29:18 UTC — twenty minutes before the pre-merge
sweep. `ops_job_runs` id **11410**, `job_name = 'derive_roster'`, `status =
success`, `rows_written = 406`. The live database now holds:

```
real-store assignments in ref_employee_assignments : 405   (13 real store numbers)
persons reachable from them                        : 322   (employee_id 2266..2587)
orphan ref_employees rows, no assignment at all     :  20   (employee_id 2588..2607)
ops_job_runs rows for derive_roster                 : 199 from the build
```

`derive_roster` is called from exactly one place in the repository —
`tests/test_people_derive.py`. There is no CLI, no cron entry, no orchestrator
wiring (T-0009 owns that). So the test suite is what wrote those rows.

The mechanism is that `_observed_pairs(session, since=None)` selects `DISTINCT
ON (restaurant_number, clerk_id)` over the whole of `stg_timeclock`, and 25 of
the 27 `derive_roster(` call sites in the test file pass no argument at all.
Measured directly against the live database:

```
_observed_pairs(since=None) -> 407 pairs
  distinct stores in scope: 13 real store numbers + T-PPL-A + T-PPL-B
```

**Why it is worth stopping for — the pre-merge green is not reproducible.**
The tests assert absolute counts off a global counter:

```python
assert result.assignments_created == 1                       # AC-001
assert (first.assignments_created, first.persons_created) == (2, 2)   # INV-002
assert result.persons_created == 2                           # AC-006
```

`DeriveResult` counts everything the run created, not what the test staged.
Reproduced on three isolated synthetic stores: staging one pair while two
unrelated pairs also sit unpicked in `stg_timeclock` returns
`assignments_created = 3`. On a database where the real roster has not already
been materialised, `test_new_pair_creates_assignment` sees **406**, not 1, and
`test_rerun_creates_no_new_rows` sees `(407, ~324)`, not `(2, 2)`. Those tests
pass today only because job 11410 exhausted the real pairs first — a one-time
side effect against production data, not a property of the code. Six of the
nineteen tests carry count assertions of this shape, and they cover AC-001,
AC-005, AC-006 and INV-002 — including
`test_same_pin_different_name_is_two_persons`, the test T-0006's own NOTES call
"the most expensive test to lose".

The behaviours themselves are correct — I re-derived AC-001…AC-006, AC-024,
AC-026, AC-028 and INV-001…INV-004 on isolated synthetic stores and every one
holds. What fails is the *evidence*: the suite cannot be re-run from a clean
database and stay green, and it cannot be run at all without writing to the
business's live roster.

**The gap.** T-0006 mandates synthetic-store isolation, but nothing in the
governing layers gives the derivation a way to honour it. `derive_roster` reads
every row of `stg_timeclock` by design (that is what a nightly roster build
does), the project has one database, and `since` cannot separate synthetic
punches from real ones because real punches exist on every date. Isolation is
not something the builder can invent inside T-0006's DELIVERABLES without
either changing CON-001 or standing up test infrastructure — both above this
task's line.

Two things need deciding, and the second is the real one:

**(a) What happens to the rows already written?**
  A) **Keep them.** They are what T-0009's first run would have produced, and
     re-deriving is idempotent. Costs: the first real run went unobserved, the
     20 orphan persons stay, and T-0009 loses its acceptance signal (it will
     report 0 created).
  B) **Delete the 405 assignments, the 322 persons and the 20 orphans**, so
     T-0009 performs and records the first real run as designed. Nothing else
     references these rows yet — no wage row, no worklist item, no mart.
Burst recommends: **B** — nothing depends on them, and T-0009's whole value is
that the first materialisation of 250-400 humans is watched.   [recommendation]

**(b) How do the DB-integration tests get isolation?**
  A) **A store filter on CON-001** — `derive_roster(*, since=None, stores=None)`.
     Smallest change, testable, and plausibly wanted in production anyway for a
     single-store re-derive. Costs a spec amendment: CON-001 and REQ-001 both
     change shape.
  B) **A separate test database**, with the suite pointed at it by fixture.
     Correct answer for every DB test in the repo, not just these — and the
     largest piece of work, `infrastructure`-TYPE, founder-paired.
  C) **Transactional test fixtures** — run each test in a transaction that is
     rolled back. Isolates writes without touching CON-001, but `derive_roster`
     opens its own session via `get_session()`, so this needs the session
     factory to be injectable, and `track_job` commits on a separate connection
     regardless.
  D) **Assert deltas, not absolutes** — have the tests measure before/after
     counts scoped to the synthetic stores. Cheapest by far, fixes the false
     green, and leaves the tests still writing the whole real roster on a clean
     database. Treats the symptom.
Burst recommends: **A** for T-0006 now, **B** as the standing fix — A is one
parameter, keeps every existing assertion meaningful, and makes the synthetic-
store convention actually enforceable rather than aspirational.   [recommendation]
Status: **DECIDED 2026-08-18 → (a) B, (b) A.** (a) The 405 assignments and 342
persons were **deleted**, on explicit founder instruction, after independently
reproducing the measurements and confirming nothing referenced them; a reversible
snapshot was taken first and `stg_timeclock` was untouched. T-0009 performs and
records the first real run as designed. (b) `CON-001` gains
`stores: list[str] | None`; the suite scopes all 27 call sites. Policy recorded
as **D-042**; SPEC-PPL-001 → v1.6.0. A separate test database (option B) remains
the standing fix — already **T-0011** under D-025, with **T-0016** as the
interim.

---

### B-0039 — AC-005: is "an existing assignment" the state at run start, or the state at the moment of resolution?
Task: T-0006 (audit failed) · Blocks: REQ-002/AC-005 · Raised: 2026-08-18

**Specified.** AC-005 — "WHEN a new assignment's `(clerk_id, normalized_name)`
equals that of an existing assignment, the roster service SHALL link the new
assignment to that assignment's person." AC-004 — "IF `employee_name` differs
from the assignment's `observed_name`, THEN the roster service SHALL update
`observed_name`". Both run in the same pass, and the spec never says which
snapshot AC-005 compares against.

**Observed.** `derive.py` builds `by_identity` once, from the assignments as
they stood before the loop, and never updates it when AC-004 rewrites a
`normalized_name` during the same run. Reproduced on synthetic stores:

```
run 1:  punch(A, PIN, "bir")                       -> assignment A -> person 2911
run 2:  punch(A, PIN, "singh, bir")                 (terminal corrects the name)
        punch(B, PIN, "singh, bir")                 (same human starts at store B)

after run 2:
  (A, PIN, observed "singh, bir", normalized "singh, bir") -> person 2911
  (B, PIN, observed "singh, bir", normalized "singh, bir") -> person 2912
  distinct (clerk_id, normalized_name) keys: 1
  distinct employee_ids:                     2
```

Two assignments now agree exactly on the linking key and point at two different
people. Re-running does not repair it — both assignments exist, so neither
branch of the loop reconsiders the link (INV-004 forbids it anyway). It is a
permanent split that only an office merge can close.

**Why it is worth stopping for.** This is the benign direction of B-0014's
asymmetry — an under-link, repairable by one merge, not a silent fusion — so
the damage is bounded. But it leaves `ref_employee_assignments` in a state the
schema's `(clerk_id, normalized_name)` index was added to make impossible, and
it makes a third store's assignment for the same person link to *whichever* of
the two rows the planner returns first: `by_identity` is built with
`setdefault` over a query with no `ORDER BY`. That is a nondeterministic person
link, which is a worse property than the split itself.

Reachability: a name corrected at one terminal in the same run in which the
same PIN and corrected name first appear at a second store. Rare per night,
certain over a backfill window — and T-0009's first real run is exactly a
backfill window. Currently zero occurrences in the live roster (checked: no
`(clerk_id, normalized_name)` maps to more than one person).

Options:
  A) **Resolution-time snapshot** — update `by_identity` when AC-004 rewrites a
     name, so a rename earlier in the run is visible to a link later in it.
     Matches the plainest reading of "an existing assignment" and removes the
     split. One line, plus an ordering guarantee on the `existing` query.
  B) **Run-start snapshot** — declare the current behaviour correct, on the
     grounds that a run should see one consistent view of the world. Then the
     split is expected, self-corrects on no run, and office merges it; AC-005
     needs a sentence saying so.
  C) **Two passes** — apply every AC-004 rename first, then resolve every new
     assignment against the updated table. Order-independent and the easiest to
     reason about; costs a second loop.
Burst recommends: **C**, or **A** if the second pass is thought too much for
one run — either way the nondeterministic `setdefault` needs an `ORDER BY`.
Whichever is chosen, AC-005 should state the snapshot explicitly; a spec that
does not say which one it means will be re-litigated at T-0008.   [recommendation]
Status: **DECIDED 2026-08-18 → C.** Two passes: every AC-004 rename is applied
first, the identity index is rebuilt from the table inside the same transaction,
and only then is any new assignment resolved. `ORDER BY assignment_id` makes the
`setdefault` winner deterministic. Policy recorded as **D-043**; AC-005 now
states which snapshot it means, so T-0008 does not re-litigate it.

---

### B-0040 — What is the roster's behaviour when `employee_name` is absent or blank?
Task: T-0006 (audit failed) · Blocks: REQ-001/AC-001, REQ-002/AC-005, REQ-006/AC-026 · Raised: 2026-08-18

**Specified.** `stg_timeclock.employee_name` is `TEXT` — **nullable** (migration
008). REQ-001's inputs list it without qualification; AC-001 says the assignment
carries "the most recently seen `employee_name`"; AC-005 keys on
`(clerk_id, normalized_name)`; AC-026/AC-027 derive `display_name` from the
observed name, and `ref_employees.display_name` is `TEXT NOT NULL`. No AC, no
edge-table row and no codex line says what any of this means when the name is
missing.

**Observed.** `derive.py` fills the gap three times without a decision behind
any of them:

1. `"employee_name": r[2] or ""` — NULL becomes the empty string.
2. `derive_display_name("")` returns `""`, so the person is created with
   `display_name = ''`. NOT NULL is satisfied and the row is meaningless.
3. `if normalized:` and `if r[5]:` keep empty normalized names out of the
   linking map, so two assignments that *do* agree on `(clerk_id, '')` are not
   linked — AC-005 says they SHALL be.

Reproduced on synthetic stores:

```
punch(A, PIN, "")  +  punch(B, PIN, "   ")   ->  persons_created = 2
  assignments: (A, PIN, observed '',    normalized '')  -> person 2914
               (B, PIN, observed '   ', normalized '')  -> person 2915
punch(A, PIN, NULL)  ->  person created with display_name = ''
```

**Why it is worth stopping for.** It is Rule 1 in the small: three defaults
invented where the spec is silent, each defensible, none licensed. The empty
`display_name` is the one that escapes — a person with a blank name reaches
every roster screen, the incomplete sweep (T-0009) and the merge UI (T-0008),
and none of them will have a reason to expect it.

Not currently reachable: **0** of 19,339 real `stg_timeclock` rows have a NULL
or blank `employee_name`. It becomes reachable the first time the POS emits one,
and the derivation runs nightly forever.

Options:
  A) **Refuse the row** — a pair whose latest name is blank raises a worklist
     item for office and creates no assignment. Loudest, and consistent with
     REQ-001's "fails loudly" posture for an unknown store. Costs a dependency
     on T-0009's worklist path.
  B) **Fall back to the clerk_id** — `display_name = "Clerk 1998 (unnamed)"`,
     `normalized_name` still empty, and link on the empty key like any other so
     AC-005 holds uniformly. Keeps the hours attributable; office renames.
  C) **Use the most recent non-blank name for the pair** instead of the most
     recent name outright — a single blank punch then costs nothing, and only a
     pair that has *never* had a name falls through to A or B.
  D) **Keep the current behaviour** and write it into the spec: blank names get
     a blank display name and never link.
Burst recommends: **C layered over B** — C removes almost every occurrence, B
gives the remainder a name a human can act on, and the AC-005 carve-out for
empty keys disappears in both cases.   [recommendation]
Status: **DECIDED 2026-08-18 → C layered over B.** The derivation carries the
most recent **non-blank** `employee_name`; a pair that has never had one gets
`display_name = "Clerk <clerk_id> (unnamed)"`, keeps an empty `normalized_name`,
and links on the empty key like any other value. Policy recorded as **D-044**;
AC-001 amended and AC-001a added. The carve-out that skipped empty keys is gone,
so AC-005 holds uniformly.

---

### B-0037 — When a terminated person clocks in again, what happens to `termination_date`?
Task: T-0006 (halted) · Blocks: REQ-005/AC-024 · Raised: 2026-08-18

**Specified.** AC-022 — "WHEN a person is terminated, the roster service SHALL
set `termination_date` and `is_active = false`." AC-024 — "IF a terminated person
clocks in again, THEN the roster service SHALL reactivate the **same** person row
and SHALL NOT create a new one." codex 06 "Leaving" agrees on the shape — "A
returning employee is the same `ref_employees` row reactivated, not a new one" —
and says nothing about the two columns. §6's edge row reads "Terminated person
clocks in again | Same person reactivated | AC-024", which settles *which row*
and not *what the row then says*.

**The gap.** "Reactivate" unambiguously means `is_active = true`. It does not say
whether `termination_date` is cleared. Both readings are defensible and I can
argue either, which is the signal this is not mine to settle:

* Clearing it reads AC-024 as the inverse of AC-022, and leaves a coherent row.
* Keeping it preserves the fact that the person once left, at the cost of a row
  that says `is_active = true` **and** `termination_date = 2025-03-01`
  simultaneously — which any consumer filtering on `termination_date IS NULL`
  will read as still-terminated.

**Why it is worth stopping for.** `ref_employees` has one `termination_date`
column and no history table, so whichever is chosen is the only record of the
event. codex 07's retention rule for the I-9 is a *later-of*: three years from
hire, or one year from termination. That rule reads `termination_date`. And
codex 00 — "corrections are new rows with a reason" — argues against silently
overwriting a fact, though a rehire is arguably a new event rather than a
correction.

Nothing sets `is_active = false` today (AC-022 is schema-only in T-0004), so
this is not yet reachable in production. It becomes reachable the moment
termination is implemented, and by then the derivation will have been running
nightly.

Options:
  A) **Clear both** — `is_active = true`, `termination_date = NULL`. The inverse
     of AC-022, coherent row, simplest consumer story. Loses the previous
     termination date; acceptable for the I-9 rule specifically, because the
     later-of clock only matters while someone is gone, and a subsequent
     departure writes a fresh date.
  B) **`is_active = true` only** — keep `termination_date`. Preserves the fact,
     but ships a self-contradicting row and quietly breaks any query that uses
     `termination_date IS NULL` as the activity test.
  C) **A, plus record the reactivation** in `ops_employee_identity_log`. Most
     faithful to codex 00's "new rows with a reason". Costs migration `022`: the
     log's `action` CHECK is `('merge','split')` and would need `'reactivate'`,
     and the columns are shaped for identity repair rather than lifecycle.
  D) **Employment spells** — a `ref_employee_spells` table, one row per stint.
     Correct modelling for anyone who leaves and returns more than once, and far
     beyond what any AC in this spec asks for.
Burst recommends: **A**, with **C** as the follow-up if the audit trail is
wanted — A is what AC-024 most plainly means and leaves no contradictory state,
and C can be added later without changing A's behaviour. **D** is the honest
long-term answer and should not be bought on the strength of one AC.
[recommendation, not a decision]
Status: **DECIDED 2026-08-18 → A.** Reactivation sets `is_active = true` **and**
clears `termination_date`. AC-024 is the inverse of AC-022; the row is coherent
and `termination_date IS NULL` remains a truthful activity test. Recorded as
**D-041**; AC-024 amended, SPEC-PPL-001 → v1.5.0.

**C was offered back to Burst as "a follow-up if you want the audit trail", and
Burst declined it — recorded as Burst's call, not the founder's.** Reasons:
`ops_employee_identity_log` is shaped for identity *repair* (its `action` CHECK
is `merge`/`split`, its columns are `from_employee_id`/`to_employee_id`/
`assignment_id`), and a lifecycle event fits none of that without overloading a
table whose purpose is different; a reactivation is already visible in the
`derive_roster` structlog line and in `ops_job_runs`; and D — employment spells —
is the correct long-term shape, which a half-step through the identity log would
make harder to reach rather than easier. Buying migration `022` now for an event
that cannot yet occur is speculative.

**Reopen if** termination gets implemented and anyone needs to answer "has this
person left before, and when" — that question is D's, and it should be bought as
D rather than bolted onto the identity log.

### B-0034 — A week with no shifts returns a confident `$0` even when no wage row exists anywhere
Task: T-0007 (audit RED, rework) · Blocks: REQ-003/CON-005, INV-007 · Raised: 2026-08-17

**Specified.** CON-005 — "`is_costed = False` when the rate is absent **or** any
shift's `hours_after_adj` is NULL; `dollars` is then `None`, never zero."
T-0007's own FORBIDDEN_ACTIONS — "do not return `Decimal("0")` when a rate is
missing — return `None`. A zero flows into a mart and understates labor cost
invisibly (INV-008)." Neither §6's edge table nor CON-005 says what a week with
**no shifts at all** costs, so "the rate is absent" has no date to be evaluated
at.

**Observed.** `cost_week` resolves rates only for the distinct `business_date`s
that have shifts (`src/subway_ops/people/cost.py:171-179`). With no shifts, the
wage table is never consulted, and the empty-week path falls through to the
costed branch. Probed against the live DB, current business week
2026-08-12 → 2026-08-18:

```
employee with no wage row and no punches
  cost_week(...) -> WeekCost(regular_hours=0, overtime_hours=0,
                             dollars=Decimal('0'), is_costed=True)

employee_id 999999999 — does not exist in ref_employees at all
  cost_week(...) -> WeekCost(0, 0, dollars=Decimal('0'), is_costed=True)
```

`is_costed=True` asserts a rate that was never looked up, and `dollars` is the
`Decimal("0")` the task forbids for a missing rate. **Materiality is low** — the
figure contributes zero to any aggregate and no hours are excluded, so AC-019's
`partially_costed` count is unaffected — but the shape is the same one D-036 was
raised for: an undefined case filled silently, with `is_costed` reading as
authoritative. The delivered test `test_a_week_with_no_shifts_costs_zero_when_a_rate_exists`
records a wage first, so the two candidate answers cannot differ inside it —
the same blind spot D-036 recorded about `test_rate_is_resolved_for_the_week_not_today`.

Options:
  A) **Ratify as built** — an empty week costs `$0` and is costed, rate or no
     rate. Zero hours cost zero whatever the rate is, so the number is true; the
     cost is that `is_costed=True` stops meaning "we know this person's rate"
     and starts meaning "nothing contradicted us", and a nonexistent employee_id
     answers confidently.
  B) **Require a rate even for an empty week** — resolve at `week_finish` when
     there are no shifts; absent ⇒ `dollars=None`, `is_costed=False`. Restores
     CON-005's literal reading and keeps the FORBIDDEN_ACTION intact for one
     extra lookup per shift-less person; abstains where the answer ($0) is
     knowable.
  C) **A third state** — `WeekCost` grows `no_activity: bool` (or `dollars=None`
     with `is_costed=True`) so "worked nothing" is distinguishable from both
     "costed" and "cannot cost". Most honest, widens CON-005's shape and touches
     T-0009's consumer.
Burst recommends: **B** — it is one branch and one test, it keeps
`is_costed=True ⇒ the rate is known`, and it is the reading CON-005 and the
task's own FORBIDDEN_ACTIONS already carry. **A** is defensible and costs
nothing to adopt if the founder prefers the truthful zero.   [recommendation, not a decision]
Status: **DECIDED 2026-08-17 → B.** An empty week must still resolve a rate, at
`week_finish`; absent ⇒ `dollars=None`, `is_costed=False`. This keeps
**`is_costed=True` meaning "the rate is known"** rather than "nothing
contradicted us", which is the reading CON-005 and the task's own
FORBIDDEN_ACTIONS already carry. Recorded as **D-038**; CON-005 amended,
SPEC-PPL-001 → v1.4.0. Accepted cost: the figure abstains on a week whose answer
($0) is arithmetically knowable — deliberate, because a caller cannot tell a real
zero from an unpriceable one unless the flag means something.

### B-0036 — Two concurrent runs of the DB-backed suite destroy each other's fixtures
Task: T-0007 (found while re-running the gate) · Blocks: nothing today; makes any overlapping gate run unreliable · Raised: 2026-08-17

**Observed.** My pre-merge run of `9583f0f` exited 1 with 3 failed and 4 errors
in `tests/test_people_wages.py`. The `/audit` ran the same gate on the same
commit and got exit 0. Same code, opposite verdicts — because the two runs
overlapped.

Reproduced deterministically, two runs of the same file started together:

```
run A : 3 failed, 21 passed, 2 errors
run B : 4 failed, 19 passed, 4 errors
serial: 25 passed
```

**Cause.** Every DB-backed test file namespaces its rows with a per-FILE
constant — `MARK = "t0007-wages-selftest"`, `KIND = "t0003_selftest"`,
`MARK = "t0004-selftest"` — and its fixture teardown deletes *everything*
carrying that marker. The marker identifies the file, not the run. So a second
concurrent run of the same file wipes the first run's fixtures out from under it
mid-test, which is exactly the "a wage row vanishing mid-test" symptom the audit
saw and could not explain.

This is not specific to T-0007. It is the pattern every DB-backed test file in
the repo uses, so **the suite is not reentrant against the shared database**.

**Why it matters beyond the flake.** `/audit` re-runs the gate by design, and a
build may re-run its own. Those two runs going red for reasons unrelated to the
code is the worst kind of gate noise: it teaches everyone to re-run and shrug,
which is how a real failure gets waved through. I nearly reported my own red run
as a code problem.

Teardown is not at fault and no residue was left — after the concurrent runs,
all three markers and the stray-punch check came back zero.

Options:
  A) **Namespace per run, not per file** — mix a per-session token (a uuid
     generated once per pytest session) into every marker, and scope teardown to
     it. Concurrent runs stop seeing each other. Costs a touch of plumbing in
     every DB-backed test file and does not stop two runs from competing for the
     same *real* rows they read (e.g. `ref_stores`).
  B) **Serialise the gate** — a lockfile so only one `verify.sh` touching the
     database runs at a time. Cheapest, and honest about there being one shared
     resource; makes an audit wait behind a build.
  C) **Wait for T-0011 / D-025** (containerised Postgres per session), which
     dissolves this along with B-0001's whole class. Correct at the root;
     T-0011 is founder-paired and unscheduled, and until it lands every
     overlapping run is a coin flip.
Burst recommends: **A now, C as the real fix.** A is small, local to the test
files, and removes the false-red immediately; B makes the gate slower in exactly
the situation where two people are trying to get work done. C supersedes both and
this becomes dead weight the day it lands — which is fine, that is what C is for.
[recommendation, not a decision]
Status: **DECIDED 2026-08-17 → A.** Every DB-backed test file mixes a per-SESSION
token into its namespace marker and scopes teardown to it, so two concurrent runs
stop deleting each other's fixtures. Recorded as **D-040**; task **T-0016**,
which also carries D-039's synthetic stores because both change the same files
and splitting them would only manufacture a merge conflict. **C remains the real
fix** — T-0011's containerised Postgres dissolves this whole class and D-040
becomes dead weight the day it lands, which is the intended end state.

### B-0035 — T-0007's cost tests write timeclock rows against real, active store numbers, which codex 13 says never to do
Task: T-0007 (audit RED, rework) · Blocks: codex/13-BUILD/CONVENTIONS.md "Tests and the database" · Raised: 2026-08-17

**Specified.** `codex/13-BUILD/CONVENTIONS.md` — "DB-backed tests currently run
against **production** (B-0001). Until that is fixed: **Never point a test at a
real store number.** Use a synthetic identifier and seed it `is_active=false` so
the ingests cannot pick it up." The chapter states why: both rules exist because
both were broken, and `test_mart_recon_weekly.py` was hard-deleting store 4092's
history on every run.

**Observed.** `tests/test_people_cost.py:153-157` takes the two lowest real
store numbers straight out of `ref_stores` —

```
SELECT store_number FROM ref_stores ORDER BY store_number LIMIT 2
-> ('10393', is_active=True), ('17967', is_active=True)
```

— and nine DB-backed tests then INSERT `stg_timeclock` punches against them, up
to 35 hours on a single day, dated inside the **current** business week. Rows
are namespaced by `clerk_id` (`t0007:clerk-a/b`) and removed in fixture
teardown, and a scan of `stg_timeclock` after the gate found **0** leftovers, so
nothing durable has been written. The exposure is the crash window: teardown is
a fixture finalizer, and a killed or crashed run leaves 25–35h phantom punches
on two live stores in the open week, with no owner and no alarm. Nothing reads
`stg_timeclock` for a mart today — the labor-dollar mart that will is the very
next consumer of this task's output.

Every other DB-backed test in the repo inserts its own synthetic store
(`T1`/`T2`/`T3`, `TEST_STORE`) and deletes it. The people/ chain is the
exception: `tests/test_people_schema.py:67,227` (T-0004, merged and audited
green) reads real store numbers too — but only to satisfy an FK on a ref table,
never to write staging rows. So this is a repo-wide question the founder should
settle once rather than a T-0007 idiosyncrasy.

Options:
  A) **Seed synthetic stores in the people fixtures** — `T-PPL-1`/`T-PPL-2`,
     `is_active=false`, created and dropped by the fixture, matching the
     `T1`/`T2`/`T3` pattern already in the repo. Small, mechanical, and closes
     the crash window; also fixes T-0004's tests when someone gets to them.
  B) **Ratify the read-a-real-store pattern for `people/`** and scope the
     convention to "never write to a real store's rows" — cheapest, keeps the
     tests as written, and leaves the exact hazard the convention was written
     after (staging rows on a live store) one crash away.
  C) **Wait for T-0011** — D-025's containerised Postgres removes the entire
     class, so change nothing now. Correct in the end state, but T-0011 is
     founder-paired and unscheduled, and the labor mart lands before it.
Burst recommends: **A** — the fix is a fixture, the pattern already exists three
times in `tests/`, and it is the only option that leaves nothing to remember.
[recommendation, not a decision]
Status: **DECIDED 2026-08-17 → A.** The people fixtures seed their own synthetic
stores (`T-PPL-1`/`T-PPL-2`, `is_active=false`) and drop them, matching the
`T1`/`T2`/`T3` pattern already used three times in `tests/`. Recorded as
**D-039**. T-0007's rework fixes its own file; the rest of the repo — including
T-0004's merged tests, which read real store numbers for an FK — is **T-0016**.

### B-0032 — Which date inside a business week resolves the wage rate? A mid-week raise re-prices the whole week
Task: T-0007 (audit RED) · Blocks: REQ-003/AC-012, AC-016 · Raised: 2026-08-17

**Specified.** AC-012 — "WHEN a rate is requested for a **business date**, the
roster service SHALL resolve the rate in force for that date." AC-016 costs a
week at a singular `hourly_rate`. §6's edge table has a row for a back-dated
wage row, and **no row for a raise that lands inside a week being costed**.
So the spec says how to resolve a rate for a *date* and never says which date
represents a *week*.

**Observed.** `cost_week` fills the gap silently with the last day of the week:
`rate = rate_in_force(employee_id, week_finish)` (`src/subway_ops/people/cost.py:135`).
Probed against the live DB, week 2026-07-15 → 2026-07-21, raise effective
Saturday 2026-07-18, 10h worked Wednesday and 10h worked Sunday:

```
rate at week_start : 10.0000
rate at week_finish: 30.0000
cost_week dollars  : 600.00000000   (20h × $30)
correct            : 400            (10h × $10 + 10h × $30)
DELTA              : +200           — the week overstated by 50%
```

Every hour worked before the raise is paid at the post-raise rate. A mid-week
*cut* understates by the same mechanism. This is the one input wages exist to
produce, and the error is invisible: `is_costed` is `True` and the figure looks
authoritative.

Choosing `week_finish` is not called out in the journal, and the test that looks
like it covers this — `test_rate_is_resolved_for_the_week_not_today` — records
its wage *before* the week starts, so `week_start` and `week_finish` return the
same rate and the choice cannot fail. No test distinguishes the two.

Rule 1: a threshold not defined by the governing spec is a HALT and a bench
item. A correct guess would still be a defect; this one is also wrong.

Options:
  A) **Pro-rate within the week** — cost each shift at the rate in force on its
     own `business_date`, then split regular/overtime on the summed hours.
     Matches how a raise actually works and how WA/OR pay it. Costs a
     per-shift-date rate resolution and forces a decision on which rate the
     overtime premium multiplies (the OT hours are no longer at one rate).
  B) **Pin to `week_start`** — one rate per week, the rate in force when the
     week opened. Cheapest, preserves AC-016's singular `hourly_rate` exactly,
     and errs toward the *old* (lower) rate rather than the new one. Still
     wrong for the post-raise hours, but wrong in the direction that does not
     overstate cost.
  C) **Pin to `week_finish`** — as built. Ratify the current behavior.
  D) **Refuse to cost a week containing a rate change** — `is_costed = False`,
     `dollars = None`, same machinery as the NULL-hours case. Never wrong,
     abstains on the weeks a payroll question is most likely to be asked about.
Burst recommends: **A**, with the overtime premium multiplying the rate in force
on the shift that crossed 40 — but that second half is itself undefined and
would need deciding in the same sitting. **D** is the honest interim if A is too
large for this task: it reuses a path that already exists and cannot produce a
confidently wrong number.   [recommendation, not a decision]
Status: **DECIDED 2026-08-17 → A.** Pro-rate within the week: each shift is
costed at the rate in force on its **own** `business_date`, and the
regular/overtime split is then taken on the person's summed weekly hours.
Policy recorded as **D-036**; SPEC-PPL-001 → v1.3.0.

**The sub-question I flagged is answered by an existing decision, not left
open.** Which rate the overtime premium multiplies follows from Q-007/B-0020,
already folded into this spec: the overtime hours are "the hours after the 40th,
wherever worked, **ordered by `clock_in`**". That ordering identifies *which*
shifts contain the premium hours; option A then prices those shifts at their own
rates. NG-007 still fences out the *store allocation* of the premium — this uses
only Q-007's ordering rule, not its attribution, and `CON-005` still returns a
per-person weekly figure.

### B-0033 — AC-013 guards the write; the read it actually names is unguarded, and CON-002 gives no way to guard it
Task: T-0007 (audit RED) · Blocks: REQ-003/AC-013, INV-006 · Raised: 2026-08-17

**Specified.** AC-013 — "IF a caller whose role is not `office` or `owner`
**requests** a wage, THEN the roster service SHALL refuse and SHALL NOT include
the rate in any response body." INV-006 — "a wage rate is **readable** only by
`office` and `owner`." Both name a *read*. CON-002 specifies the read as
`rate_in_force(employee_id, on: date) -> Decimal | None` — **no role
parameter**, so the contract makes the AC unenforceable at that boundary.
CON-003's `record_wage(*, employee_id, effective_date, hourly_rate, set_by)`
likewise carries no role, yet is required to raise `PermissionError`.

**Observed.** The builder resolved the same contradiction in opposite directions
in the same file: `record_wage` gained an unspecified `actor_role` parameter and
enforces the guard; `rate_in_force` did not, and is unguarded. Probed:

```
rate_in_force(employee_id, week_finish)  # no caller identity at all
-> Decimal('30.0000')
```

All four tests named against AC-013 exercise `record_wage` and assert
`match="may not set wages"` — i.e. they verify a *set*, which is not AC-013's
trigger. **No test exercises a refused read, because no code path can refuse
one.** As delivered AC-013's stated condition is unimplemented and INV-006 does
not hold.

The builder saw this and wrote it up in `journal/T-0007.md` ("INV-006 is not
enforced on the read path, and I did not add it"), reasoning that the contracts
are unambiguous about what to build. They are not: two clauses of the same REQ
require a guard that a third forbids the shape of. Rule 1 makes that a bench
item, not a judgment call, and Gate 2 step 5 makes an ambiguous spec RED-blocked
rather than a builder's choice.

**A guard on `rate_in_force` alone would not close it.** `cost_week` is
unguarded and returns both dollars and hours, so any caller recovers the rate by
division — probed: `600.00000000 / 20.0000 = 30.0000`. Whatever is decided has
to cover the derived figures, not just the accessor.

Options:
  A) **Amend CON-002 and CON-003 to carry `actor_role`**, guard both, and decide
     what `cost_week` (which needs the rate internally) passes. Consistent, and
     makes INV-006 real — but pushes a role parameter into every future caller
     including the labor mart, which has no human actor.
  B) **Enforce INV-006 at the view/API layer only**; scope AC-013 explicitly to
     `record_wage` and amend INV-006 to say the library is trusted. Honest about
     where the boundary really is, matches how the dashboard already gates
     roles, and leaves `cost_week` free for marts — but the invariant then
     guarantees less than its wording claims and every new surface must remember.
  C) **Two functions** — an unguarded internal resolver for marts and a guarded
     `read_wage(..., actor_role)` for humans. Keeps marts clean and makes the
     guarded path the obvious one for a view, at the cost of a second name.
  D) **Ratify as built** — the guard is on the write only; amend AC-013 and
     INV-006 to say so.
Burst recommends: **C**, then AC-013 and INV-006 amended to name the guarded
entry point explicitly. B is the cheapest defensible answer; A is the most
complete and the most invasive. Note that whichever is chosen, `cost_week`'s
division side channel needs an explicit answer rather than being left to the
next task.   [recommendation, not a decision]
Status: **DECIDED 2026-08-17 → C.** Two entry points. `rate_in_force` stays
exactly as CON-002 specifies — unguarded, internal, for marts and for
`cost_week`. A new **`read_wage(employee_id, on, *, actor_role)`** is the guarded
human-facing accessor and is the entry point AC-013 and INV-006 now name.
Policy recorded as **D-037**; SPEC-PPL-001 → v1.3.0 with CON-006 added.

**`cost_week`'s division side channel is answered rather than deferred:**
`cost_week` stays unguarded. It is a mart path with no human actor, it needs the
rate internally, and a caller holding both dollars and hours can always recover
the rate by division — so a guard there would be theatre. INV-006 is therefore
amended to say what is actually true: the library's *guarded* accessor is
`read_wage`, and any human-facing surface must go through it or enforce the role
itself. An invariant that promises more than it delivers is worse than one
scoped honestly.

### B-0031 — A worktree convenience symlink was committed; merging it silently destroys main's recorded fixtures
Task: T-0005 (audit RED) · Blocks: T-0005 merge, and T-0006…T-0009 behind it · Raised: 2026-08-17

**Specified.** T-0005 DELIVERABLES license five created paths. Rule 4 is BOUNDED
SURFACE — write only within them.

**Observed.** `forge/T-0005` adds a sixth, a symlink committed in `c387ab9`:
`tests/fixtures/recorded -> ../../../../../tests/fixtures/recorded`. Its target
resolves only from inside `.claude/worktrees/T-0005/tests/fixtures/`; five levels
above `main`'s own `tests/fixtures/` is the filesystem root. Audited by merging
into a throwaway clone of `main` with a fixture present: merge exits 0, no
conflict, no warning, and the real fixtures directory is replaced by a dangling
link. The 15 recorded fixtures are gitignored, so git's index cannot see them and
nothing conflicts. `main` would drop from `568 passed, 6 skipped` to ~33 tests
silently skipped.

It became a commit because pre-merge Run 1 failed `git status: NOT CLEAN`, and
committing an untracked file is the shortest way to green that check. The gate
enforces cleanliness, not scope. The ignore rule
`tests/fixtures/recorded/` carries a trailing slash, so it matches the directory
but not the symlink — which is why the link was untracked rather than ignored.

Nothing else is wrong with the task: four ACs verified by hand, 26/26 tests,
both FORBIDDEN_ACTIONS clean, ROLE_ORDER exact.

Options: A) drop the symlink from the branch · B) fix the ignore rule (one
character) · C) worktree setup creates the symlinks (B-0030's C) · D) teach the
gate a DELIVERABLES scope check.
Burst recommends: **B then A, with D as its own task.**   [recommendation]
Status: **DECIDED 2026-08-17 → B + A.** Ignore rule loses its trailing slash so
it covers the symlink; `forge/T-0005` drops the committed link. Policy recorded
as **D-033**. `.gitignore` added to T-0005's DELIVERABLES; the fix re-enters
through build → audit → close. **Option D not adopted** — the gate still does not
check deliverable scope, and that is now a known-uncovered class rather than a
surprise.

### B-0030 — An adhoc sweep in a worktree reports green with 109 tests skipped
Task: T-0005 · Blocks: nothing today · Raised: 2026-08-13

**Observed** on the first `[P]` task to use a worktree. A worktree gets tracked
files only, so every gitignored artifact the suite needs is absent — `.env`
first, then `tests/fixtures/recorded/`:

```
worktree, as created      :  465 passed, 109 skipped   ← adhoc: all checks passed
+ .env symlinked          :  535 passed,  39 skipped   ← adhoc: all checks passed
+ fixtures/recorded too   :  568 passed,   6 skipped   ← matches main
```

103 tests were not running, including all 14 of T-0003's and all 21 of T-0004's.
Fixing the first cause moved the number and left a green tick over 33 still-absent
tests; the coverage floor is what caught the rest. Pre-merge was never foolable —
the schema snapshot fails hard on an unset `DATABASE_URL`.

Options: A) adhoc asserts `DATABASE_URL` · B) adhoc prints its skip count ·
C) worktree setup carries the artifacts.
Burst recommends: **C and B together.**   [recommendation]
Status: **DECIDED 2026-08-17 → C.** Worktree setup links `.env` and
`tests/fixtures/recorded/`. Policy recorded as **D-034**. Task **T-0014**.
**Option B not adopted** — adhoc still will not say what it skipped, so the
general "a skip presents as a pass" hole stays open by choice.

### B-0029 — The drift check cannot see a constraint change
Task: T-0004 (found during build; does not block it) · Blocks: nothing today · Raised: 2026-08-13

**Observed.** Migration `021_people.sql` drops and re-creates
`ref_users_role_check`, widening who may hold an account on the admin surface
from three roles to six. `schema_snapshot.py --diff` reports **four** changes,
all of them new tables, and says nothing about the constraint. Reproduced: the
declaration matches at four lines and the gate is green with the ALTER entirely
unmentioned.

The snapshot captures tables and columns. A `CHECK`, a `UNIQUE`, a foreign key,
an index predicate, a `NOT NULL` — none of them appear. So a migration can widen
an access-control constraint, drop a uniqueness guarantee, or remove a foreign
key on an existing table and produce zero drift lines.

**Why this matters more than it looks.** B-0022 chose option A over option B
specifically because B "cannot see an ALTER that a migration makes by accident,
which is precisely the case worth catching". Option A was adopted to preserve
that property, and it does not have it either — for a different reason, at a
different layer. The declared-drift mechanism is sound; what it is declared
*over* is narrower than the review it is meant to support. T-0003's own
`dismissed` fix widened an index predicate, and that produced no drift line
either.

Not urgent: 021's constraint change is intentional, tested both ways
(`test_ref_users_role_accepts_the_six_roles`, and a rejection test pinning
`shift_lead` as deliberately absent), and described in the declaration prose. The
gap is that the *next* one might not be.

Options:
  A) **Extend the snapshot to constraints and indexes** — CHECK, UNIQUE, FK,
     PK, NOT NULL, index definitions. The declaration format already handles
     arbitrary lines. Costs a noisier first diff and a one-time baseline rotation
     that will show every existing constraint as "added".
  B) **Constraints only, not indexes** — constraints are contracts, indexes are
     performance. Smaller diff, but T-0003's suppression predicate lives in a
     partial index and is genuinely semantic, so this would miss it.
  C) **Leave it; rely on the migration diff for constraint review.** Cheapest,
     and honest about what the check is for — but it means the gate's green is
     narrower than a reader will assume, which is the failure mode B-0022 was
     raised about in the first place.
Burst recommends: **A**, timed with or after T-0013 rather than now — both are
harness-hardening found by leaning on the harness, both touch checks that police
builds, and neither should be done by a task the check is currently gating. Note
C's specific danger: three separate times now, a check has been believed to cover
something it did not.   [recommendation, not a decision]
Status: **DECIDED 2026-08-17 → A.** The snapshot captures CHECK, UNIQUE, FK, PK,
NOT NULL and index definitions alongside tables and columns. Policy recorded as
**D-035**. Task **T-0015**. Accepted cost: the first diff after it lands reports
every existing constraint and index as added, absorbed by a one-time baseline
rotation. Noted for the record — B-0022 chose option A over B specifically to
keep the "catch an accidental ALTER" property, and option A did not have it
either.

### B-0027 — May T-0003 edit migration `020`, or must a `021` correct it?
Task: T-0003 (rework) · Blocks: T-0003's rework, and every migration task until D-025 lands · Raised: 2026-08-13

**Specified.** codex 02 and `tools/verify_invariants/check_migrations_append_only.py`
both say: never edit a migration **after it has been applied**; a new change is a
new file. The invariant's own docstring gives the reason — "the file no longer
describes the schema that actually exists, so a fresh environment built from the
migrations diverges from production."

**Observed.** D-029 and D-030 both change `020_worklist.sql`: the index predicate
gains `dismissed`, and `resolved_by` goes. `020` has been **applied to the live
shared database** (during T-0003's build, per the D-025 defect) but has **never
been merged to `main`**. So "applied" and "merged" come apart, and no document
says which one the rule means. Two readings, materially different history.

Measured, because it changes the stakes: `ops_worklist_items` currently holds
**0 rows**. No producer exists — T-0009 is unbuilt — so nothing is at risk either
way, and the question is about the record rather than about data.

Options:
  A) **Edit `020` in place**, drop the live table, re-apply the corrected
     migration, re-run `--update`. `main` receives one honest migration
     describing the table as it actually is. Reads the rule as "applied *on
     `main`*", which is the only environment a fresh replay ever builds from.
     Costs a hand-run `DROP TABLE` against the shared database.
  B) **Ship `021` correcting `020`.** Literal reading of the rule as written.
     `main` gains a permanent fix-up migration for a table introduced two files
     earlier in the same unmerged branch — history that is honest about the
     process and misleading about the design.
  C) **Wait for T-0011/D-025** (containerised Postgres) and rebuild T-0003 on it,
     where a build never touches production and the question dissolves. Correct
     at the root; T-0011 is founder-paired and T-0003…T-0009 all wait.
Burst recommends: **A** — the rule's stated purpose is that the migration set
replays to the schema that exists, and editing an unmerged file plus re-applying
satisfies it exactly, while B guarantees the opposite for every reader of `main`
afterwards. The zero-row measurement is what makes A safe rather than merely
convenient. Note this is my own halt-adjacent surface again, so it is benched
rather than decided in the rework.   [recommendation, not a decision]
Status: **DECIDED 2026-08-13 → A.** Append-only binds at **merge**, not at
application: a task may edit its own unmerged migration in place, and a
migration that has reached `main` is frozen absolutely, with no exception and no
size threshold. Three conditions — measure rows before dropping, re-apply so the
live schema agrees with the edited file, regenerate `CHECKSUMS.txt`. Policy
recorded as **D-032**. T-0003's rework edits `020` and ships no `021`.
Exposed by the decision and minted rather than filled: `--update` regenerates
the manifest unconditionally, so it blesses an edit to *any* migration including
a merged one — the invariant is honor-system exactly where D-032 now leans on
it. Task **T-0013**, kept out of T-0003 because a task must not harden the check
that polices it.

### B-0028 — "Cadence" is not yet a number
Task: — · Blocks: codex 11 → authoritative, and every AC in SPEC-COM · Raised: 2026-08-13

D-031 settled *which* messages batch — seven of the eight kinds. It did not
settle **what cadence**, and codex 03's rule that a metric without a stated grain
is a gap applies just as well to a notification without a stated period.

For each of the seven: daily or weekly, and at what local hour. They plausibly
differ — yesterday's numbers want a morning push, bonus standings probably weekly,
certificate expiry is an ageing nudge that may want a lead time rather than a
period at all. Store timezone matters: `STORE_TZ` already varies, so "8am" is a
per-store question, not a global one.

Burst recommends: no recommendation on the periods themselves — they are
operational rhythm, and picking them is how a channel gets muted. One structural
note offered for the answer: certificate expiry is the one kind whose natural
form is a lead time ("30 days before"), and forcing it into a period would make
it either noisy or late.
Status: OPEN

### B-0025 — Does `dismissed` suppress a re-open, or is dismissal advisory?
Task: T-0003 (audit failed) · Blocks: REQ-004/AC-018, and T-0009's sweep · Raised: 2026-08-13

**Specified.** AC-018: "SHALL NOT open a duplicate while one is already open for
that person." Codex 02 names four states — `open` / `in_progress` / `resolved` /
`dismissed` — and says nothing about which of them suppress a re-raise. T-0003's
NOTES specify the mechanism ("a partial unique index on (kind, subject_ref) WHERE
state IN ('open', 'in_progress')") but not its meaning for `dismissed`. The
task's AC list requires re-opening after `resolved`
(`test_open_item_creates_again_after_resolve`) and is silent on `dismissed`.

**Observed.** `LIVE_STATES = ("open", "in_progress")` in
`src/subway_ops/db/worklist.py`, and the same predicate on
`uq_worklist_open_subject` in `020_worklist.sql`. So a dismissed item does not
suppress anything. Reproduced against the delivered code:

```
open_item(...)  -> id 326
UPDATE ... SET state='dismissed' WHERE id=326
open_item(...)  -> id 327          # not None
states for subject: ['dismissed', 'open']
```

`resolve_item` on a dismissed subject returns 0, so a dismissed item is also
never closed out — it stays dismissed while a fresh `open` row accumulates
beside it.

The consequence lands on this table's first producer. T-0009's completeness
sweep is idempotent by design and runs every cycle: office dismisses an
`employee_incomplete` item, the next sweep re-raises it, and dismissal is inert
for the one case AC-018 was written about. `dismissed` becomes a state nothing
can reach durably.

This is a Rule 1 fill, not a defect of reasoning — the choice is defensible, it
was simply made at build time rather than benched, and the journal's 353 lines
never mention `dismissed`. It is also encoded in an index inside an append-only
migration, so reversing it costs migration `021`, which is why it wants deciding
before merge rather than after.

Options:
  A) `dismissed` suppresses — add it to the index predicate and to `LIVE_STATES`,
     so a dismissed subject stays quiet until someone explicitly reopens it —
     dismissal means something, but a genuinely new occurrence of the same
     problem stays invisible.
  B) `dismissed` is advisory, as built — the sweep re-raises freely, nothing is
     ever lost, and office has no way to silence a recurring item.
  C) Dismissal carries a cool-off (`dismissed_until DATE`), suppressing for a
     window — matches how a human means "not now", and costs another column plus
     a policy for the default window.

Burst recommends: A — under B the `dismissed` state has no observable effect for
a swept producer, which is the only kind T-0003 has; C is A plus machinery that
no spec has asked for yet.   [recommendation, not a decision]
Status: **DECIDED 2026-08-13 → A.** `dismissed` suppresses. The index predicate
and `LIVE_STATES` both become `('open', 'in_progress', 'dismissed')`; `resolved`
still does not suppress. Dismissal is durable and needs an explicit reopen,
which SPEC-APP-001 builds. Accepted cost recorded: a genuinely new occurrence of
a dismissed problem stays invisible until someone reopens it. Policy recorded as
**D-029**, and codex 02 now states which states suppress so no future producer
re-derives it. T-0003 → rework.

### B-0026 — Are `resolved_at` / `resolved_by` part of the worklist shape?
Task: T-0003 (audit failed) · Blocks: REQ-004/AC-020 · Raised: 2026-08-13

**Specified.** Codex 02 "The worklist is the spine" states the shape as: "typed,
role-assigned, with a state (`open` / `in_progress` / `resolved` / `dismissed`),
a due date, and a reference back to whatever produced it." T-0003's NOTES restate
that list and rest the whole task on its completeness — "codex 02 already defines
the shape completely, so this is not invention" — which makes it a closed list,
and the journal repeats the claim at line 24. The task's behavior line is
`resolve_item(kind, subject_ref) -> int`.

**Observed.** `020_worklist.sql` additionally creates `resolved_at TIMESTAMPTZ`
and `resolved_by TEXT`, and `resolve_item` takes a third parameter:

```
def resolve_item(kind, subject_ref, *, resolved_by: str | None = None) -> int
```

Confirmed against the live table: 10 columns, the last two being `resolved_at`
and `resolved_by`. Neither appears in codex 02's list nor anywhere in T-0003.
`test_resolve_records_who_and_when` asserts on both, and it is not among the
seven tests the task's ACCEPTANCE_CRITERIA names. No caller passes `resolved_by`
— it defaults to `None`, so every row this system writes today leaves it NULL,
and there is no producer that would populate it until a worklist UI exists
(SPEC-APP-001, explicitly not this task).

The audit gate treats gold-plating past the spec as RED even when the extra code
is good, and this is the case it describes: two columns and a parameter that no
governing document licenses. The journal is otherwise scrupulous about exactly
this failure mode — it records catching and rejecting an invented
`ref_roles` FK on the ground that "the reasonable-looking option is the dangerous
one" — and never mentions these two columns at all. That silence is the finding
more than the columns are.

Options:
  A) Ratify — amend codex 02's stated shape to include resolution audit fields,
     via a `codex_update` task, and keep the migration as built — one codex line,
     and the closed list becomes true again; blesses columns nothing populates.
  B) Strip to the licensed shape before merge — drop both columns and the
     parameter, re-raise when SPEC-APP-001 needs them — the record stays exact,
     at the cost of a rebuild now and migration `021` later, since migrations are
     append-only and the worklist screen will very likely want both.
  C) Split — keep `resolved_at` as entailed by the `resolved` state, drop
     `resolved_by` as an actor concept with no producer — smallest honest
     surface; still needs A's codex amendment for `resolved_at`.

Burst recommends: A — append-only migrations make B pay twice for columns
SPEC-APP-001 will almost certainly require, and the value at stake here is the
written record, not the two columns.   [recommendation, not a decision]
Status: **DECIDED 2026-08-13 → C** (against the recommendation). `resolved_at`
stays and codex 02's stated shape now names it — it is entailed by the terminal
state, and an item that resolved at no particular time is not a record.
`resolved_by` is dropped, along with `resolve_item`'s undeclared parameter: no
producer can populate an actor until SPEC-APP-001 exists, and a nullable column
filled by nobody reads as attribution that was never tracked. Policy recorded as
**D-030**; the column returns in SPEC-APP-001, with a producer, as a new
migration. T-0003 → rework.

### B-0024 — Does a drift declaration assert causation or accounting?
Task: T-0010 (audit failed) · Blocks: T-0010 merge, and T-0003's resumption · Raised: 2026-08-13

**Specified.** D-024: "a task that intends to change the schema declares its
expected drift in `.drift/expected/T-####.txt`", and its consequence line — "the
declaration is a reviewable artifact in the diff". T-0010's own NOTES restate it:
"a reader sees, in the diff, exactly which schema objects **the task intended to
change**." Both read causation.

**Observed.** T-0010 changes no schema, and ships `.drift/expected/T-0010.txt`
declaring `+ table ops_worklist_items (10 columns)` — T-0003's table, live in the
shared database because T-0003's migration `020` was applied during its build
while T-0003 sits unmerged. To make that line honest the build redefined what the
file asserts, from causation to "every schema difference between the baseline and
the live database is accounted for", and wrote the new definition into
`.drift/expected/README.md` as governing text. The journal states it plainly:
"So I changed the definition rather than the declaration." That is a change to a
recorded decision, made at build time — Rule 1 says bench it, not fill it. The
mechanism itself is sound; only its meaning is undecided.

**Two consequences, both reproduced against the delivered gate:**
1. T-0010's post-merge rotates the baseline to include `ops_worklist_items`. When
   T-0003 resumes and declares its own table — which T-0010's FORBIDDEN_ACTIONS
   explicitly reserves for it — the line is declared but not observed → STALE →
   RED. Verified: `--before schema-now --after schema-now --expected <T-0003
   line>` exits 1. As delivered, T-0003 cannot do the thing it was told to do.
2. Under the accounting reading T-0003 declares nothing, so the reviewable
   artifact lands on the wrong task: T-0003's diff shows a migration and no
   declaration, and T-0010's diff shows a table it never touched.

Options:
  A) **Ratify the accounting semantics** as an amendment to D-024, and write the
     predecessor rule that is currently missing: a task inherits its unmerged
     predecessor's drift, attributes it in a comment, and the declaration is
     retired when the originating task merges. Cheap — the delivered code already
     does this — but the T-0003 rule must be stated, because today it silently
     forbids T-0003 from declaring its own table.
  B) **Hold causation.** The declaration names only what the task changed, and
     cross-task drift is handled by a second mechanism — the gate diffing against
     the baseline plus the declarations still open on unmerged branches, or the
     baseline rotating at build rather than at post-merge. Keeps D-024 as
     recorded; costs a mechanism.
  C) **Remove the cause.** Land D-025 (T-0011, containerised Postgres) before any
     further migration task, so a build stops applying migrations to the shared
     database and this class of drift stops existing. Correct at the root, but
     T-0011 is founder-paired and T-0003/T-0004 wait on it.
Burst recommends: **A**, with the T-0003 rule written down — the accounting
reading is the one that still catches "a table appeared and nobody knows whose it
is", which is the more alarming case, and the delivered mechanism already
implements it. C is right underneath and does not conflict with A.
[recommendation, not a decision]

Also for the record, not a decision: `.drift/expected/T-0010.txt` is outside
T-0010's DELIVERABLES (Rule 4). Whichever option is taken, that file's existence
is part of it.

Status: **DECIDED 2026-08-13 → A.** Accounting semantics ratified as
**D-028**, amending D-024. The predecessor rule D-024 was missing is now
written: a task declares the drift observed at its own gate run; inherited
drift carries an attributing comment; the inherited line is retired once the
predecessor merges (the staleness check enforces this rather than obstructing
it); and merge order follows dependency order so inheritance stays exceptional.

For this tangle specifically: T-0010 merges first because it is the enabler.
T-0003 then observes no drift and declares nothing — its migration, CHECKSUMS
entry and journal carry the record. The audit is right that the reviewable
artifact lands on the wrong task this once; that is a one-time cost of T-0003
having halted, and D-025 removes the cause rather than elaborating the rule.

Rule 4: `.drift/expected/T-0010.txt` is added to T-0010's DELIVERABLES.
T-0010 → `queued` for rework; the fix re-enters through build → audit, not
from the bench.

### B-0023 — The crew scorecard weights and the payout cap
Task: — · Blocks: codex 05 → all of SPEC-BON · Raised: 2026-08-13
B-0009 settled the crew scorecard's STRUCTURE (team-based: store
sales/food/labor + own throughput + own training). It did not settle the
arithmetic, and a bonus spec cannot be written against "weighted"
without the weights.
Two numbers are needed:
  (a) **Weights** across the five components. They must sum to 1. The
      split between store-driven and self-driven components is the real
      decision — heavily store-weighted makes it a team bonus, heavily
      self-weighted makes the team components decorative.
  (b) **The payout cap** — the ceiling on the sliding scale above the
      90% floor, so a freak period cannot pay out unboundedly.
Burst recommends: no recommendation on either. Both are compensation
policy, not design, and a plausible-looking guess here is money.
Status: OPEN

### B-0022 — The schema-drift gate blocks every schema_change task
Task: T-0003 (halted) · Blocks: T-0003, T-0004, and every future migration · Raised: 2026-08-13
`scripts/schema_snapshot.py --diff` returns exit 1 on ANY drift, and
`verify.sh` treats a non-zero exit as a failed check. So a task whose
whole purpose is to add a table can never reach a green pre-merge.

The check's own message already knows this — it prints "Schema drift is
not automatically wrong — a migration is supposed to change the schema.
It must be INTENDED" — but it has no way to record that a human agreed,
so it fails anyway. Right intent, wrong mechanism. My defect, introduced
in T-0000.

T-0003's code is complete: 12 tests, every AC verified individually,
adhoc green, full suite 502 passed. The ONLY pre-merge failure is this.

Options:
  A) Acknowledgement file — the task declares its expected drift (e.g.
     `.drift/expected/T-0003.txt`), the gate passes when observed drift
     matches the declaration and fails when it does not. Keeps the check
     adversarial: undeclared drift still reds, and a stale declaration
     reds too.
  B) Trace drift to migrations — the gate passes if every changed table
     appears in a migration added on this branch. Fully automatic, no
     declaration to maintain, but it cannot see an ALTER that a
     migration makes by accident, which is precisely the case worth
     catching.
  C) Demote drift to a warning at pre-merge; assert only at post-merge.
     Cheapest. Also removes the review surface exactly where review
     happens, so a bad migration reaches main before anyone looks.
Burst recommends: **A** — it keeps the property that made the check
worth writing (drift must be looked at by a person) while letting the
look happen once, in the task, instead of blocking forever.
Status: **DECIDED 2026-08-13 → A.** Acknowledgement file: a task declares
expected drift in `.drift/expected/T-####.txt`; the gate passes on an exact
match and fails on undeclared drift or a stale declaration. Policy recorded as
**D-024**. Gate fix is **T-0010**; T-0003 then declares its drift and re-runs.

### B-0021 — AC-019 names no grain for `partially_costed`
Task: SPEC-PPL-001 Q-008 · Blocks: nothing · Raised: 2026-08-11
AC-019 says "a labor-dollar aggregate" is marked `partially_costed`.
codex 03 says a metric without a stated grain is a gap, so strictly this
is one. PLAN-SPEC-PPL-001 reads it as per person per business week,
because CON-005 is the only aggregate this spec produces and NG-007
fences store allocation out.
Options: A) Per person per week only here; the labor-dollar mart marks
its own store/week aggregate from the person-week flags. B) Amend AC-019
to name the grain explicitly.
Burst recommends: **B** — same behavior, but the AC stops being ambiguous
to the next reader. Cosmetic, do it whenever the spec is next touched.
Status: **DECIDED 2026-08-13 → B.** AC-019 now names its grain: per person,
per business week. Same behavior the L1 plan assumed; the AC is no longer
ambiguous. SPEC-PPL-001 → v1.1.0, open_questions 0.

### B-0020 — Which store bears the overtime premium?
Task: SPEC-PPL-001 Q-007 · Blocks: the labor-dollar mart, not SPEC-PPL-001 · Raised: 2026-08-11
Created by the interview's own answers rather than found: Q-005 sets 1.5x
beyond 40 h **per person**, and codex 06 makes a person one record across
stores. So 25 h at store A plus 25 h at store B is 10 overtime hours, and
the premium has to land on some store's labor cost.
Options: A) Chronological — the hours after the 40th, wherever they were
worked. Truest to what happened; needs shift-level ordering across stores.
B) Pro-rata by hours — simple, defensible, matches no individual shift.
C) Wholly to the store where the crossing occurred — punishes whichever
store scheduled last.
Burst recommends: **A** — the data supports it (`clock_in` orders shifts)
and it is the only rule that survives someone asking "why is my store
carrying that?"
SPEC-PPL-001 is unblocked regardless: CON-005 returns a per-person weekly
cost and NG-007 fences the allocation out.
Status: **DECIDED 2026-08-13 → A.** Chronological: the premium lands on
whichever store the person was working for the hours past the 40th, ordered by
`clock_in`. Folded into codex 06 and SPEC-PPL-001 Q-007. Applied by the
labor-dollar mart; `CON-005` still returns a per-person weekly figure.

### B-0014 — How is a (store, clerk_id) resolved to a person?
Task: SPEC-PPL-001 Q-001 · Blocks: REQ-002, US-003, every employee grain · Raised: 2026-08-11
codex 06 (6.2A) says one person, many store assignments. The data cannot
deliver that automatically. Measured: 250 distinct clerk_ids across 399
(clerk_id, store) pairs; **56 clerk_ids carry more than one name** — PIN
`8` appears under 5 different names at 5 stores, `1998` under 4 names at
9 stores. clerk_id is a per-store PIN, not a person. Names are no better:
`samir, samir` appears at 5 stores under 6 clerk_ids.
Options: A) Never auto-link — every pair its own person, office merges
manually (~149 merges).  B) Auto-link on exact clerk_id + normalised name
(51 pairs qualify); everything else separate, merge available. Under-links
(`singh, bir` vs `bir` stay apart) but effectively cannot over-link.
C) Auto-link on name alone — over-links badly, see samir.
Burst recommends: **B** — under-linking is repairable by a merge; over-
linking silently fuses two people's hours, wages and certificates.
Status: **DECIDED 2026-08-11 → B.** Link on exact clerk_id + exact
normalized name; everything else separate, merge available. Folded into
SPEC-PPL-001 REQ-002 (AC-005…AC-010). Accepted cost: `singh, bir` and
`bir` stay separate until office merges them.

### B-0015 — How do crew authenticate?
Task: SPEC-PPL-001 Q-002 · Blocks: REQ-006 permissions, SPEC-APP-001 · Raised: 2026-08-11
codex 06 (6.4B) makes phone the login identifier, but `ref_users` is
email-PK with `password_hash NOT NULL` — it cannot represent a crew login.
Options: A) Crew are not in `ref_users` at all; they authenticate against
`ref_employees.phone` by SMS one-time code. Clean separation; SMS costs.
B) Widen `ref_users` — nullable email, add phone, nullable password_hash.
One auth table; the admin table now carries 250 crew rows.
C) Discord OAuth — they are all being put on Discord anyway (D-018), so
the account already exists and there is no SMS bill.
Burst recommends: **C**, with **A** as fallback for anyone not on Discord.
It reuses an identity the rollout is already creating.
Status: **DECIDED 2026-08-11 → C.** Discord OAuth, with phone as
fallback for anyone not on Discord. SPEC-PPL-001 stores `discord_user_id`
and `phone`; the flow itself is SPEC-APP-001 (NG-004).

### B-0016 — Which hours field costs labor dollars?
Task: SPEC-PPL-001 Q-003 · Blocks: REQ-003 · Raised: 2026-08-11
`stg_timeclock` carries `hours_before_adj`, `hours_after_adj` and
`adj_amount`. 1,369 of 19,089 rows (7%) differ — one by −2.48 h on a
7.98 h shift. So the POS already has an adjustment concept, separate from
the custody chain in codex 08.
Options: A) `hours_after_adj` — the POS's final word; codex 08's chain
later layers on top.  B) `hours_before_adj` — raw evidence only, our chain
owns every adjustment.  C) Carry both; before as evidence, after as the
default payable.
Burst recommends: **A** — the POS adjustment is already someone's
decision, and discarding it means re-making 1,369 decisions by hand.
Status: **DECIDED 2026-08-11 → A.** `hours_after_adj` is the costing
basis. Folded into SPEC-PPL-001 AC-015.

### B-0017 — Salaried employees, and the overtime rate
Task: SPEC-PPL-001 Q-004/Q-005 · Blocks: REQ-003 schema · Raised: 2026-08-11
`ref_employee_wages.hourly_rate` assumes everyone is hourly. Two
questions: (a) is anyone salaried — a store manager on a fixed weekly
figure breaks hours × rate entirely; (b) is overtime paid at a premium?
codex 08 sets a 40-hour threshold, and WA/OR both require 1.5× over 40,
so labor dollars need the multiplier or they understate.
Burst recommends: on (b), **1.5× over 40**, matching WA/OR law. On (a) no
recommendation — it is a fact about the business, not a design choice.
Status: **DECIDED 2026-08-11.** (a) All employees are hourly — no
salary support; SPEC-PPL-001 NG-006. (b) Overtime at 1.5x beyond 40 h per
person per business week, matching WA/OR law; AC-016.

### B-0018 — Display-name normalisation
Task: SPEC-PPL-001 Q-006 · Blocks: AC-004 · Raised: 2026-08-11
Observed names are `LAST, FIRST` and inconsistent — `singh, bir` and
`bir` are the same human under the same PIN.
Options: A) Derive `First Last` from `LAST, FIRST`, office can override.
B) Store verbatim.  C) Office types every display name.
Burst recommends: **A** — it is right most of the time and the override
covers the rest.
Status: **DECIDED 2026-08-11 → A.** Derive `First Last` from
`LAST, FIRST`, office may override and the override survives later
derivation runs. AC-026…AC-028.

### B-0019 — stg_timeclock.clock_in violates codex 02 (naive TIMESTAMP)
Task: SPEC-PPL-001 A-003 · Blocks: nothing today · Raised: 2026-08-11
codex 02 requires `TIMESTAMPTZ` stored UTC. `stg_timeclock.clock_in` and
`clock_out` are naive `TIMESTAMP`; the ingest attaches `STORE_TZ` at read
time to derive `business_date`. A genuine code/codex disagreement, found
by retro-reading during SPEC-PPL-001 and recorded rather than normalised
by silence (the D-016 guard).
SPEC-PPL-001 does not depend on it — it keys on `business_date`. But
codex 08's clock reconciliation compares clock times to scheduled times,
and that comparison across a DST boundary is where a naive timestamp
bites.
Options: A) Leave it; document the deviation in codex 02 as a known
exception.  B) Migrate both columns to TIMESTAMPTZ before Phase C.
Burst recommends: **B**, timed before SPEC-SCH-003, not now.
Status: **DECIDED 2026-08-13 → B.** Migrate `stg_timeclock.clock_in` and
`clock_out` to `TIMESTAMPTZ` before Phase C — specifically before SPEC-SCH-003,
whose clock-vs-schedule comparison is where a naive timestamp bites across a
DST boundary. Not minted as a task yet: Rule 2 needs an anchor, and SPEC-SCH
does not exist. Queued on the board as a Phase C prerequisite.

### B-0009 — Crew bonus scorecard: 5.2 and 3.1 contradict each other
Task: T-0002 · Blocks: codex 05 → all of SPEC-BON · Raised: 2026-08-11
Answer 5.2 puts crew on a weighted scorecard of "sales / food / labor /
training". Answer 3.1 says sales totals, food cost and labor cost are
INVALID at employee grain — an employee controls none of them. Same
sitting, both cannot stand.
Options: A) Crew scorecard uses only what 03 permits — throughput plus
training. Consistent; narrow.  B) Crew scorecard is team-based: their
STORE's sales/food/labor attainment plus their own throughput and
training — the store metrics stay at store grain, so 03 holds.
C) Revise 3.1 to admit these at employee grain.
Burst recommends: **B** — the only option that pays crew on the things
5.2 named without attributing store economics to an individual.
Status: **DECIDED 2026-08-13 → B.** Team-based: a crew scorecard combines
their STORE's sales/food/labor attainment with their OWN throughput and
training. Resolves the 5.2 / 3.1 contradiction — the store metrics stay at
store grain, so the crew member shares in the result rather than being measured
on it. Folded into codex 05. **Chapter 05 stays draft**: the weights and the
payout cap are numbers nobody has set — now **B-0023**.

### B-0011 — The timecard exception taxonomy is undecided
Task: T-0002 · Blocks: codex 08 → all of SPEC-SCH, Phase C · Raised: 2026-08-11
Question 8.3 went unanswered. It is the centre of the chapter: the
custody chain (office adjusts → owner approves → locked report) cannot
be specced without knowing what enters it. Candidates offered, none
adopted: clocked in >N min early · clocked out >N min late · no-show ·
unscheduled shift worked · missed or short meal break · over-run past
close. Each needs a threshold, and a decision on whether it flags or
blocks approval.
Burst recommends: no recommendation — the thresholds are operational
knowledge. Note the failure mode in both directions: too tight and
office reviews 300 items a week and stops reading them; too loose and
the review chain is ceremony over a rubber stamp.
Status: OPEN

### B-0012 — Three money parameters left open
Task: T-0002 · Blocks: codex 09 → SPEC-RCN-002/006/007 · Raised: 2026-08-11
(a) **Deposit ageing** (9.4): how many days a deposit may sit with no
bank receipt before it escalates, and to whom. The worklist item most
worth chasing currently has no due date.
(b) **Royalty basis and tolerance** (9.6): 12.5% was given. Of net
sales, presumably — the familiar 8% + 4.5% — but "presumably" is not a
spec for something that runs weekly across 15 stores forever. Confirm
the basis; state what discrepancy is material.
(c) **Material invoice price variance** (9.7): every supplier price
moves. Without a threshold the three-way match emits an exception per
line item and becomes noise.
Burst recommends: no recommendation on (a) and (c). On (b), confirm
net sales explicitly rather than let the familiar number stand in.
Status: OPEN

### B-0013 — Real-time vs cadence routing table
Task: T-0002 · Blocks: codex 11 → SPEC-COM · Raised: 2026-08-11
Question 11.1 unanswered. Which of these push immediately and which
batch: yesterday's numbers · schedule publication · shift reminders ·
overtime notifications · task assignment · bonus standings ·
reconciliation exceptions · certificate expiry.
Burst recommends: shift reminders real-time, everything else cadence.
Note that 8.6B made overtime *detection* rather than prediction, so an
overtime message now reports something already past and has no urgency
to preserve. The real question is volume, not technology: push eight
kinds of message in real time and everyone mutes the channel, which is
worse than no channel because it looks like communication.
Status: **DECIDED 2026-08-13 → A.** Shift reminders real-time; the other seven
kinds on a cadence. Real-time is a budget with one occupant: a new notification
is cadence by default, and promoting one is a founder decision recorded in codex
11. Policy recorded as **D-031**; routing table written into codex 11 and
`blocked_by: B-0013` lifted.
**Interpretation flagged:** this item carried no lettered options, so "A" was
read as the single marked recommendation. Nothing else in the item was labelled.
One line to correct if that reads wrong.
Residue: "cadence" is not yet a number — **B-0028**, which keeps codex 11 draft.

### B-0010 — Are I-9 and W-4 ours to hold?
Task: T-0002 · Blocks: codex 07 record types (chapter otherwise authoritative) · Raised: 2026-08-11
7.1 answered "everything you said", but the list itself flagged I-9/W-4
as probably payroll's rather than ours — so the answer is genuinely
ambiguous. Not pedantry: an I-9 has its own federal retention rule
(3 years after hire or 1 year after termination, whichever is later —
NOT the 7 years in 7.2) and is conventionally stored SEPARATELY from the
personnel file so an I-9 audit does not expose everything else.
Modelling it as another credential row gets both wrong.
Options: A) Out of scope — payroll holds them.  B) In scope, with their
own retention rule and separate storage.
Burst recommends: **A** unless payroll is not already holding them.
Status: **DECIDED 2026-08-13 → B** (against the recommendation). I-9 and W-4
are ours to hold, under their own rules: the I-9 retains for three years from
hire or one year from termination, whichever is later — which can be SHORTER
than the seven years applied to everything else — and both are stored
separately from the personnel file, office and owner only, excluded from the
inspection packet. The W-4 carries an SSN and is never rendered in any list,
export or notification. Folded into codex 07, with the termination consequence
noted in codex 06.

### B-0007 — Confirm which metrics carry a target
Task: T-0002 · Blocks: SPEC-TGT-001 (ref_targets columns) · Raised: 2026-08-11
4.5 was stated as an interview default and not explicitly answered:
net sales · food cost % · labor hours · labor dollars · transactions ·
average ticket. Recorded in codex 04 as assumed, not decided. Low risk
and additive — a metric added later is a nullable column and a backfill
— but silence on a stated default is weak consent and Rule 1 says flag
rather than fill.
Burst recommends: confirm the six as listed.
Status: **DECIDED 2026-08-13 → A.** The six confirmed: net sales, food cost %,
labor hours, labor dollars, transactions, average ticket. Folded into codex 04,
which no longer calls the list assumed.

### B-0008 — Should loss-prevention by employee exist as an office-only view?
Task: T-0002 · Blocks: nothing (Phase E scope question) · Raised: 2026-08-11
3.1 keeps void / refund / discount rates OFF the employee card, and codex
03 respects that. But `TransactionDetails` carries `clerk_id`, the data
is already available, and per-employee void rate is a standard
loss-prevention signal.
Options: A) Build it as an office-and-owner-only view — never shown to
the employee, never part of recognition or bonus.  B) Do not build it;
3.1 settles the matter.
Burst recommends: **A** — the decision in 3.1 is about what an employee
is *judged* on, which is a different question from what the owner can
*see*. But this is deliberately asked rather than assumed.
Status: **DECIDED 2026-08-13 → A.** Void / refund / discount rates by employee
exist as an office-and-owner-only loss-prevention view — never on the employee
card, never shown to their store manager, never an input to recognition or
bonus. Folded into codex 03: what an employee is judged on and what the owner
can see are different questions.

### B-0006 — The codex interview for chapters 03–11
Task: T-0002 · Blocks: every spec in Phases A–E (D-017) · Raised: 2026-08-11
Nine chapters of design authority exist only in the founder's head:
measurement grains, targets, compensation, people lifecycle, safety/health
records, scheduling and the hours custody chain, money reconciliation,
recognition, and comms. Chapters 00–02 and 13 are harvested and
authoritative; these cannot be derived from anything in the repo.
The batch is written up at [INTERVIEW-codex-03-11.md](INTERVIEW-codex-03-11.md)
— ~40 questions, choice-format with recommendations, answerable compressed
in one sitting. Ordered so that 03, 04 and 06 come first: those three gate
Phase A, which gates everything else.
Options:
  A) Answer the batch in one founder window; chapters are written from the
     answers and promoted to authoritative as each completes.
  B) Answer 03/04/06 only, unblock Phase A, and defer the rest until their
     phase comes up — less context-switching, but the later chapters then
     sit on the critical path of their own phase.
Burst recommends: **A** — the questions are cheap to answer together and
expensive to answer piecemeal, because several cross-reference each other
(bonus basis depends on target basis; recognition rewards depend on whether
crew are bonus-eligible).
Status: **ANSWERED 2026-08-11.** 33 of 40 answered; chapters written in
T-0002. Six chapters authoritative; four draft. The residue became
B-0007 through B-0013 — one contradiction, four unanswered questions,
one ambiguity, one new fork.

### B-0001 — The test suite runs against the production database
Task: — · Blocks: all DB-backed tests · Raised: 2026-08-11
There is no test database. `DATABASE_URL` points at live Supabase, so
DB-backed tests read and write production. Two defects already came from
this: `test_mart_recon_weekly.py` hard-deleted a real store's history on
every run for three months, and DB-backed tests still write real rows to
`ops_job_runs` (42 `refresh_mart_recon_weekly` entries were added by the
Part 0 runs alone, and they surface on the system status page).
Options:
  A) Separate Supabase project for tests, `DATABASE_URL` swapped in CI and
     locally via `.env.test` — true isolation, costs a second free-tier
     project and a migration run per environment.
  B) Postgres in a container for tests (testcontainers or a compose service)
     — fully local, fast, no cloud dependency; migrations run per session.
  C) Schema-per-run inside the existing database (`SET search_path`) —
     cheapest, but a bug in the isolation still lands on production infra.
Burst recommends: **B** — the tests only need Postgres, not Supabase, and a
container removes the production blast radius entirely.   [recommendation]
Status: **DECIDED 2026-08-13 → B.** Postgres in a container for DB-backed
tests; migrations per session. Policy recorded as **D-025**. Task **T-0011**
(infrastructure — founder-paired per the ceremony tiering).

### B-0002 — The cash drop reconciliation sheet is the missing domain source
Task: — · Blocks: `codex/09-MONEY-AND-RECONCILIATION/`, SPEC-RCN-002 · Raised: 2026-08-11
The founder has an existing cash drop reconciliation sheet and has described
it as tacky and hard to use. It is the only written statement of what
"reconciled" means for cash, what tolerances apply, and which fields a
manager actually fills in. Without it the codex chapter is guesswork, and
Rule 1 forbids guessing.
Options:
  A) Founder uploads the sheet; the chapter is written from it and the parts
     that are hard to use are designed away explicitly.
  B) Interview-only reconstruction — slower, and risks missing the edge cases
     that only show up in the sheet's own columns.
Burst recommends: **A**.   [recommendation]
Status: OPEN

### B-0003 — Provider names for the money-side integrations
Task: — · Blocks: SPEC-RCN-003, SPEC-RCN-004, SPEC-RCN-005, D-022 report format · Raised: 2026-08-11
Third-party delivery platforms, the card merchant/processor, and the payroll
provider are all unnamed. Each determines a statement format, and payroll
determines the locked report's layout.
Options:
  A) Founder names all three now; specs pin the formats.
  B) Build format-agnostic importers first and calibrate on a real file later
     — more rework, but unblocks Phase B's shape.
Burst recommends: **A**.   [recommendation]
Status: **DECIDED 2026-08-13 — confirmed from the interview.** Card processor
FreedomPay; Amex settled separately; ezCater for catering; DoorDash, GrubHub
and UberEats for delivery. No payroll provider is needed — D-022 made payroll a
locked report that office keys in. Six settlement sources, each its own ingest.

### B-0004 — The coverage floor
Task: — · Blocks: `scripts/verify.sh` reaching its designed bar · Raised: 2026-08-11
Coverage is held at the existing 75% floor rather than the 80% the ceremony
tiering implies. Measured today: 77-78%, so 80 is close but not free — the
Streamlit page modules sit at 21-43% and are the whole gap.
Note: the mypy half of this item was **wrong when raised**. `pyproject.toml`
already sets `strict = true`, and `mypy --strict src/` passes clean on 48
files today. The gate runs `--strict` and always did in effect.
Options:
  A) Hold 75 until the Streamlit pages are retired by the new app (D-019),
     then raise to 80 against what is left — the pages are going away anyway,
     so covering them now is work with a short half-life.
  B) Raise to 80 now and backfill page tests.
Burst recommends: **A**.   [recommendation]
Status: **DECIDED 2026-08-13 → A.** Floor holds at 75% until the Streamlit
pages are retired under D-019, then raise to 80% against what remains, in the
same task that deletes them. Policy recorded as **D-026**.

### B-0005 — The repo has never been `ruff format`ed
Task: — · Blocks: the `ruff format --check` line in the gate · Raised: 2026-08-11
`ruff format --check .` reports 68 files would change, ~58 of them
pre-existing. The check is commented out of `scripts/verify.sh` with a
pointer here; new files added by the harness were formatted individually so
they do not add to the debt.
Options:
  A) One `refactor`-TYPE task: run `ruff format .`, commit the reformat alone
     with no behavioral change, re-enable the gate line in the same commit.
     One noisy diff, reviewable because it is provably formatting-only.
  B) Format incrementally as files are touched — no big diff, but the gate
     line cannot be re-enabled for months and formatting drift persists.
Burst recommends: **A** — the diff is mechanical and `git diff -w` verifies
it changed nothing but whitespace.   [recommendation]
Status: **DECIDED 2026-08-13 → A.** One `refactor` task runs `ruff format .`,
commits the reformat alone, and re-enables the gate line in the same commit.
Policy recorded as **D-027**. Task **T-0012**.
