# Bench — Open Founder Decisions

Drained by `/bench`, one sitting per founder window. Decided policy-shaped
items also append to `DECISIONS.md`. Format: see root `CLAUDE.md`.

---

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
Status: OPEN

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
