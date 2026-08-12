# Bench — Open Founder Decisions

Drained by `/bench`, one sitting per founder window. Decided policy-shaped
items also append to `DECISIONS.md`. Format: see root `CLAUDE.md`.

---

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
Status: OPEN

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
Status: OPEN

### B-0007 — Confirm which metrics carry a target
Task: T-0002 · Blocks: SPEC-TGT-001 (ref_targets columns) · Raised: 2026-08-11
4.5 was stated as an interview default and not explicitly answered:
net sales · food cost % · labor hours · labor dollars · transactions ·
average ticket. Recorded in codex 04 as assumed, not decided. Low risk
and additive — a metric added later is a nullable column and a backfill
— but silence on a stated default is weak consent and Rule 1 says flag
rather than fill.
Burst recommends: confirm the six as listed.
Status: OPEN

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
Status: OPEN

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
Status: OPEN

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
Status: OPEN

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
Status: OPEN

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
Status: OPEN
