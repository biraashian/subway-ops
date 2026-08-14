# Bench — Open Founder Decisions

Drained by `/bench`, one sitting per founder window. Decided policy-shaped
items also append to `DECISIONS.md`. Format: see root `CLAUDE.md`.

---

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
Status: OPEN

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
