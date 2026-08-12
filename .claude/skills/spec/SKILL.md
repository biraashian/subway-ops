---
name: spec
description: Convert one source-queue entry or component into a build-grade spec - retro-spec for what already exists, codex-first for greenfield - with every residual gap flagged as a choice-format interview question. Invoke as /spec <prompt path or component name>.
disable-model-invocation: true
---

# /spec — Source → build-grade specification (v0.1)

**Objective.** Produce `specs/SPEC-<AREA>-<nnn>.md` per `specs/_TEMPLATE.md` with
zero silently-filled gaps, for the target named in $ARGUMENTS.

Areas: `DATA` `PPL` `TGT` `APP` `CAP` `RCN` `SCH` `COM` `TRN` `REC` `KPI` `BON` `RGN`.

## Source rules (D-009)
- **Greenfield** (nothing built yet): the codex chapter is PRIMARY. Its stated
  parameters carry into REQs *as stated*, never re-litigated. Expect a full
  interview — most of this system's domain has never been written down.
- **Retro-spec** (D-016 — the component already exists in `src/subway_ops/`):
  the codex is still the authority; the existing code and its tests are
  **evidence of current behavior**, not a source of truth. Read them to
  discover what the thing does, then write the ACs the codex licenses.
  **Where code and codex disagree, that is a bench item — never quietly write
  the AC to match the code.** That rule is the entire guard on D-016; without
  it a retro-spec is just fake-done with extra steps.

## Steps
1. Locate sources per the rules above. Read nothing beyond them plus
   `codex/00-INSTITUTION/` for scope and the relevant `codex/02-DATA-MODEL/`
   sections.
2. **Prior-art harvest.** For a retro-spec, also read the component's entry in
   the pre-Burst log at the bottom of `DECISIONS.md` and anything relevant in
   `legacy/`. Where the pre-Burst build made a choice a gap question touches,
   record it — it becomes a labeled option in the interview ("the pre-Burst
   build chose X"). Never treat it as settled.
3. Draft the spec: §0 metadata (`status: draft`), §1 intent + inherited codex
   principles, §2 stories, §3 one REQ per external behavior (inputs/outputs/
   IO-map/pre/post/invariants + EARS ACs), §4 contracts, §5 data model, §6 edge
   table (every row cites an IF…THEN AC), §7 non-goals, §9 traceability skeleton.
4. Two-anchor rule: every REQ names its story AND its codex chapter/decision;
   anything that can't goes to a "Parked (founder's call)" appendix.
5. Gap hunt: could two competent engineers implement a REQ differently and both
   claim compliance — then it's a gap. Every gap → §10 `Q-###` naming what it blocks.
6. **Interview:** present ONLY the Q-list, numbered, each 2–3 concrete options
   with one-line trade-offs, prior-art options labeled, one marked
   recommendation. Accept compressed answers ("1A 2B 3: $5"). No open-ended
   questions.
7. Apply answers → fold into REQs/ACs, record `Q-### → decided` in §10, set
   `status: approved`, update the board's Runway lane, append a chronicle line.

## Money, time, and identity (this domain's recurring gaps)
These four are wrong by default and must be pinned explicitly in every spec
that touches them, or raised as a Q:
- **Money** is `NUMERIC(12,4)` and `Decimal`, never float. A tolerance is a
  stated number, never "about."
- **Dates** are Subway business dates — 02:00 cutoff, Wednesday–Tuesday weeks.
  "Yesterday" and "this week" are `codex/01-CALENDAR/` terms, not Python ones.
- **Grain** — per what? Employee, shift, store, territory, week. A metric
  without a stated grain is a gap; see `codex/03-MEASUREMENT/` for which
  metrics are invalid at which grain.
- **Who approves** — anything that reaches payroll, a dispute, or a public
  standing has a custody chain. Name it.

## Validation before presenting the interview
- [ ] Every REQ names both anchors  ·  [ ] Every AC parses as EARS
- [ ] Every §6 row cites an AC or became a Q  ·  [ ] Nothing numeric or shaped
      appears that a source or the founder didn't supply — Burst inferences live
      in §10, not in REQs
- [ ] For a retro-spec: every code/codex disagreement found is a bench item,
      and none of them were resolved by writing the AC to match the code
