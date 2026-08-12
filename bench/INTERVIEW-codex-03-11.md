# Codex interview — chapters 03–11

Nine chapters of design authority that exist only in your head. D-017 blocks
every new spec until they are written, so this is the critical path.

**How to answer.** Compressed is fine and preferred: `1A 2B 3: $5 tolerance 4C`.
Pick "other" freely — the options exist to make the trade-offs concrete, not to
constrain you. Where I have a recommendation it is marked **R**, and it is a
recommendation, never a decision.

**Where prior art exists** I have labeled it. Prior art is what the pre-Burst
build chose, which is evidence about what you accepted before, not a settled
answer.

You do not have to do all nine at once. They are ordered by what unblocks the
most work: **03, 04 and 06 gate Phase A**, which is everything else.

---

## 03 — MEASUREMENT (gates Phase A and all of Phase E)

**3.1 — Which metrics are valid at employee grain?**
The chapter's real job is to say which metrics are *invalid* where, so Phase E
does not produce garbage. Food cost per employee is meaningless; units per
labor hour is not.
- A) Throughput only — units/labor hour, transactions/hour, average ticket **R**
- B) Throughput plus loss-prevention — add void rate, refund rate, discount rate
- C) Everything measurable including tips and upsell attach rate

**3.2 — How do store numbers roll up to territory?**
- A) Sales-weighted average — a $20k store moves the territory more than a $5k one *(prior art: `mart_field_manager_portfolio` does this)* **R**
- B) Simple average across stores — every store counts equally, which is arguably fairer to a manager running small stores
- C) Both, shown side by side

**3.3 — What is a number compared against by default?**
- A) The target for that store and week **R**
- B) The same week last year
- C) Trailing 4-week average for that store
- D) Peer stores in the same territory

**3.4 — Is a single shift a reportable grain, or is the week the floor?**
Per-shift means "Tuesday close was slow" is answerable; it also means far more
rows and much noisier numbers.
- A) Week is the floor for employees; day for stores **R**
- B) Shift-level for everything

---

## 04 — TARGETS AND BUDGETS (gates Phase A)

**4.1 — Who sets a store's target?**
- A) You set all of them
- B) FM proposes, you approve — uses the review chain already in the codex **R**
- C) Computed from last year plus a growth factor, you override exceptions

**4.2 — What cadence?**
- A) Annual, revised quarterly **R**
- B) Quarterly
- C) Weekly

**4.3 — Are targets absolute or relative?**
- A) Absolute dollars per store per week (a real number in `ref_targets`) **R**
- B) Percent growth vs the same week last year, computed
- C) Absolute for sales; percentage for food and labor *(prior art: food cost was a flat 0.22 for every store)*

**4.4 — A store blows past or misses badly mid-quarter. What happens to the target?**
This one decides whether attainment history is trustworthy.
- A) Targets are immutable once the period opens; variance is the story **R**
- B) You can revise, and the revision is effective-dated so history stays honest
- C) You can revise and it applies retroactively

**4.5 — Which metrics get a target at all?**
Free text. My assumption unless told otherwise: net sales, food cost %, labor
hours, labor $, transactions, average ticket.

---

## 05 — COMPENSATION (gates Phase E)

**5.1 — Who is bonus-eligible?**
- A) Store managers only
- B) Store managers and field managers **R**
- C) Everyone including crew

**5.2 — How is a bonus computed?**
- A) Single metric — hit the sales target, get the payout
- B) Weighted scorecard — sales / food / labor / training, each weighted **R**
- C) Gate plus multiplier — must pass a food-cost gate to earn anything on sales

**5.3 — Cliff or sliding scale?**
- A) Cliff — 100% of target or nothing
- B) Sliding from a floor — nothing below 90%, linear from there to a cap **R**
- C) Sliding from zero

**5.4 — What period?**
- A) Monthly — fast feedback, noisy
- B) Quarterly **R**
- C) Both: quarterly payout, monthly standings

**5.5 — Does an employee who leaves mid-period keep a pro-rated bonus?**
Free text. It is a real policy question and the code cannot guess it.

---

## 06 — PEOPLE (gates Phases A, C, D and E — the widest blocker)

**6.1 — How does someone get onto the roster?**
`stg_timeclock` already carries 250 distinct `clerk_id`s, so a roster can be
derived for free.
- A) Auto-create a stub row on first clock-in; you fill in wage, role, hire date later **R**
- B) Manual add required first; an unknown `clerk_id` clocking in raises a worklist item
- C) Auto-create, but the stub is invisible until completed

**6.2 — One person working two stores: one record or two?**
`stg_timeclock`'s natural key is `(clerk_id, store)`, so today they are two.
- A) One person, many store assignments — correct, and more work **R**
- B) One record per person per store — simpler, but their KPI card splits in two
- C) Does not happen in practice

**6.3 — What happens when someone leaves?**
- A) Marked terminated; their page goes read-only; records retained **R**
- B) Marked terminated and hidden everywhere except compliance reports
- C) Purged after a retention window (see 7.2)

**6.4 — What identifies a person to the app, given crew need a login?**
- A) Email
- B) Phone number — more realistic for crew **R**
- C) Discord account link
- D) Store manager issues a code

---

## 07 — SAFETY, HEALTH AND RECORDS (gates Phase D; has legal weight)

**7.1 — What must exist for each employee, and which are legally required vs your policy?**
Free text — this is the chapter I can least guess at. My starting list: WA/OR
food handler card, safety orientation, health/hygiene orientation, harassment
training, I-9 and W-4 (probably payroll's, not ours). Tell me which are ours to
hold and which are legally mandated.

**7.2 — Retention period after an employee leaves?**
- A) 3 years
- B) 7 years **R** (usual conservative default; confirm against your accountant)
- C) Indefinite
- D) Per record type — say which

**7.3 — Who may view an employee's certificates?**
- A) The employee, their store manager, office, you **R**
- B) Add their field manager
- C) Anyone in the store

**7.4 — What goes in the inspection packet?**
Free text. My assumption: every currently-active employee's food handler card
with expiry, training and orientation completions, plus store-level permits and
the pest control log. Say what an inspector has actually asked you for.

**7.5 — Renewal nudges — how early?**
- A) 60 / 30 / 7 days **R**
- B) 30 / 7
- C) 90 / 60 / 30 / 7

---

## 08 — SCHEDULING AND HOURS (gates Phase C)

**8.1 — Who builds the schedule?**
- A) Store manager, within the labor budget **R**
- B) Field manager for their territory
- C) Store manager drafts, FM approves before publish

**8.2 — Publication lead time, and what happens after publish?**
- A) Published Thursday for the week starting Wednesday; changes after publish need manager approval and are logged **R**
- B) Published whenever; freely editable
- C) Locked at publish; changes are exceptions handled at reconciliation

**8.3 — What counts as an exception needing office review?**
Multi-select. My starting set: clocked in more than 5 min before scheduled
start; clocked out more than 10 min after scheduled end; no-show; worked an
unscheduled shift; missed or short meal break; shift over-run past close.
Add, remove, or set the thresholds.

**8.4 — Are WA/OR meal and rest breaks tracked and enforced?**
Washington requires a 30-minute meal period for shifts over 5 hours and a paid
10-minute rest per 4 hours; Oregon is similar but not identical. This is
compliance exposure, not a nicety.
- A) Track and flag violations as exceptions **R**
- B) Track only, no flagging
- C) Out of scope — the POS handles it

**8.5 — Shift swaps between employees: allowed, and who approves?**
- A) Allowed with store manager approval, logged **R**
- B) Not through this system
- C) Allowed freely between employees at the same store

**8.6 — Overtime: what is the threshold and what happens when someone approaches it?**
- A) 40 hours/week; warn at 35 projected; the schedule guard flags it mid-week **R**
- B) 40 hours; warn only when exceeded
- C) Daily overtime rules also apply — say what they are

---

## 09 — MONEY AND RECONCILIATION (gates Phase B; **B-0002 blocks most of this**)

Please upload the cash drop reconciliation sheet before I write this chapter.
These are the questions it probably answers, so treat them as a checklist to
read it against rather than homework.

**9.1 — Cash drop tolerance: at what variance is a drop "reconciled"?**
*Prior art: the recon mart uses ≤$5 clean, ≤$50 flagged, above that escalated.*
- A) Keep $5 / $50 **R**
- B) Different numbers — say what
- C) Percentage of the drop rather than absolute

**9.2 — Who reconciles a cash drop, and when?**
- A) Store manager records the drop and uploads the receipt; office matches against the bank **R**
- B) Office does all of it from receipts
- C) Store manager does the whole match

**9.3 — Deposit cadence?**
- A) Daily
- B) Every other day
- C) Varies by store volume — say which stores differ

**9.4 — A deposit has no bank receipt after N days. What is N, and what happens?**
Free text. This becomes a worklist item with a due date.

**9.5 — Chargebacks: who disputes, and what is the window?**
- A) Office disputes; worklist item opens on notification with the processor's deadline as the due date **R**
- B) You dispute personally
- C) Store manager disputes

**9.6 — Royalty: what is the expected figure, and what tolerance?**
Free text — the calculation basis (percent of net sales? of gross?) and what
counts as a material discrepancy.

**9.7 — Invoice matching: which suppliers, and what is a material price variance?**
Free text. Also: do you receive invoices digitally from any of them, or is it
all paper to be photographed?

**9.8 — Third-party and merchant: which providers?** *(B-0003)*
Free text — delivery platforms and the card processor. Each is a statement
format.

---

## 10 — RECOGNITION (gates Phase E)

**10.1 — Who sets the weekly task?**
- A) You, one task for all stores
- B) FM, per territory
- C) Rotating library of standard tasks, auto-assigned, you override **R**

**10.2 — Who grades, and on what scale?**
- A) FM grades their territory, 1–5 **R**
- B) You grade everything
- C) Pass/fail

**10.3 — Store of the week: judged or computed?**
- A) Computed from target attainment **R**
- B) You pick
- C) Computed, you can override with a reason

**10.4 — Employee of the week: who picks?**
- A) Store manager nominates **R** — KPIs cannot see attitude or teamwork
- B) Computed from KPIs
- C) Manager nominates from a KPI-ranked shortlist

**10.5 — What is the reward, concretely?**
Free text. Recognition post only, points toward something, gift card, extra
break? This determines whether the system needs a ledger of balances or just a
list of winners — a real architectural fork.

---

## 11 — COMMS (gates Phase C)

**11.1 — What is genuinely real-time vs a daily/weekly cadence?**
Multi-select from: yesterday's numbers, schedule publication, shift reminders,
overtime warnings, task assignment, bonus standings, reconciliation exceptions,
certificate expiry. My assumption: only overtime warnings and shift reminders
are real-time; everything else is cadence.

**11.2 — Do crew get DMs or channel posts?**
- A) Personal things by DM (shifts, training, certificates), store things in the store channel **R**
- B) Everything in channels
- C) Everything by DM

**11.3 — Who can post in a store channel?**
- A) Everyone in that store — it becomes a working channel **R**
- B) Managers post, crew react only
- C) Bot only

**11.4 — What must never go to Discord?**
Free text. My assumption: wages, individual bonus amounts, disciplinary matters,
and anything from an employee's certificate file. Confirm and extend — Discord
is a third party and this list is the privacy boundary.

**11.5 — Territory channels: does an FM get one, and can store managers see peer stores?**
- A) FM channel per territory; store managers see only their own store **R**
- B) All store managers can see all store channels
- C) No territory channels

---

## What happens when you answer

Each answer becomes a stated parameter in a codex chapter, and every chapter
that reaches `status: authoritative` unlocks the specs anchored to it. Anything
you leave open stays a bench item and blocks only the specs that touch it — the
rest of the queue keeps moving.

Anything you answer with "I don't know yet" is a legitimate answer and I will
record it as an open question rather than picking for you.
