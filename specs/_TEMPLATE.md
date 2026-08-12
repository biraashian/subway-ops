# Spec Template — the Sovereign Document

**What this is.** The build-side control document that pins *external behavior* explicitly so an
agent can't fill gaps with assumptions and head the wrong way. It is the source of truth Burst
generates against; the code is the output, not the authority. It is **not** a renamed PRD — a PRD
is written for a human who interprets ambiguity from context, whereas an agent handed a gap fills
it with a guess and drifts fast, so this document leaves no gaps.

**Where it sits.** In the four-phase spine **Specify → Plan → Tasks → Implement** (GitHub Spec Kit;
AWS Kiro and Cursor Plan Mode standardize the same shape), this is the **Specify** artifact, with a
human checkpoint before Plan. Mapped to your stack:

```
codex (Constitution + Conventions)        ← inherited, read upward, never re-litigated
   └─ THIS SPEC  ............................  the sovereign "what + why" (Specify)
        └─ L0 brief  .........................  compressed Specify+Plan frame for one build
             └─ L1 = Plan / Technical Design   the "how" (Plan)
                  └─ L2 = Build Sheet  ........  ordered tasks, CT/T-tagged (Tasks)
                       └─ Implement + Verity ..  merge-and-audit gate (Implement)
```

**The read-upward principle.** Meaning shades the line: the codex (theme) contains this Spec's
intent (chapter), which contains each requirement (passage), which licenses each behavior line
(line). A behavior line is only valid if the layers above license it. Anything that reaches past
what the codex and intent support isn't spec — it's treatise, and it moves out, flagged as your call.

**The fidelity discipline (two anchors).** Every requirement must name (1) the user story / intent
it serves, and (2) the governing context — a codex principle or an ADR — that justifies the reading.
If it can't name both, it's overreaching. This is what gives Verity teeth: the merge-and-audit loop
validates each produced unit against its anchored criteria before it reaches your review lane.

---

## EARS reference *(keep at hand — every acceptance criterion uses one of these)*

EARS = Easy Approach to Requirements Syntax (Mavin et al., Rolls-Royce, RE'09). It gently constrains
natural language into five patterns plus combinations, so requirements are unambiguous and testable —
and parseable by an agent. Ruleset: **0–many** preconditions, **0–1** trigger, **exactly one** system
name, **1–many** responses; clauses always in temporal order.

| Pattern | Keyword grammar | Use for |
|---|---|---|
| **Ubiquitous** | `The <system> SHALL <response>.` | always-true behavior (no keyword) |
| **State-driven** | `WHILE <precondition>, the <system> SHALL <response>.` | behavior active while a state holds |
| **Event-driven** | `WHEN <trigger>, the <system> SHALL <response>.` | response to a triggering event |
| **Optional feature** | `WHERE <feature is included>, the <system> SHALL <response>.` | behavior tied to an optional capability |
| **Unwanted behavior** | `IF <unwanted condition>, THEN the <system> SHALL <response>.` | error / edge handling |
| **Complex** | `WHILE <precondition>, WHEN <trigger>, the <system> SHALL <response>.` | combinations, in temporal order |

> Rule of thumb: every edge case in §6 should surface as an **IF…THEN** line; every happy path as a
> **WHEN…SHALL** line; every guarantee-that-must-always-hold as a **Ubiquitous** line or an invariant.

---

# === SPEC: <feature name> ===

## 0 · Metadata *(the anchors, machine-readable front matter)*

```yaml
spec_id:        SPEC-<area>-<nnn>
feature:        <short name>
version:        0.1.0
status:         draft            # draft | approved | locked
owner:          <name>
inherits:       codex@<version>  # Constitution + Conventions, read upward
l0_brief:       <path/ref to the L0 brief that frames this build>
phase:          specify          # specify | plan | tasks | implement
bound_by:       [CON-PRINCIPLE-01, CON-PRINCIPLE-04]   # the specific codex non-negotiables that bind here
```

## 1 · Intent (North Star) — the upward anchor
<One paragraph: what this feature achieves and **why**. Restated from the L0 brief / PRD. Everything
below is checked against this; nothing below may exceed what this paragraph and the codex license.>

**Inherited non-negotiables.** This feature must honor, without re-deciding: <list the specific codex
principles by ID — e.g. CON-PRINCIPLE-01 "tests accompany every unit", CON-PRINCIPLE-04 "no silent
schema changes". These are the parents; ADRs below may refine but never contradict them.>

## 2 · User Stories
Each owns a cluster of acceptance criteria below.

- **US-001** — As a `<role>`, I want `<capability>`, so that `<outcome>`.
- **US-002** — …

## 3 · Behavioral Specification *(the sovereign core)*
For each requirement, define external behavior with no gaps. Repeat the block per requirement.

---
### REQ-001 — <requirement, one line>
Serves: **US-001**  ·  Governed by: **CON-PRINCIPLE-01 / ADR-001**   ← two anchors (else it's treatise)

- **Inputs** — `<name: type, range/format, source>`
- **Outputs** — `<name: type, shape>`
- **I/O mapping** — `<the explicit input → output relation>`
- **Preconditions** — `<what must be true before this runs>`
- **Postconditions** — `<what is guaranteed true after>`
- **Invariants** — `INV-001: <what stays true throughout, never violated>`
- **Sequential logic** — `<ordering constraints, if any; else "none">`
- **Acceptance criteria (EARS)**
  - `AC-001` — WHEN `<trigger>`, the `<system>` SHALL `<response>`.
  - `AC-002` — IF `<unwanted condition>`, THEN the `<system>` SHALL `<response>`.
  - `AC-003` — WHILE `<state>`, the `<system>` SHALL `<response>`.
---

## 4 · Interface Contracts
The boundary between components — what each piece exposes and expects. OpenAPI-style for HTTP.

- **CON-001 — `<interface name>`**
  - Exposes: `<method / endpoint / function signature with types>`
  - Expects: `<request shape / parameter types>`
  - Returns: `<response shape / types>`
  - Error contract: `<status/exception → meaning>`

## 5 · Data Model / Schema
The shape of the data the system moves.

- **`<Entity>`** — fields `<name: type, constraints>`; relationships `<…>`; invariants `<…>`.

## 6 · Edge Cases & Error Conditions *(where gaps hide — close every one)*
Enumerate exhaustively. Each row must map to an EARS **IF…THEN** criterion above, or it's an open gap
Burst is forbidden to fill silently (see §10).

| Edge case | Expected behavior | Covered by |
|---|---|---|
| `<malformed input>` | `<…>` | AC-002 |
| `<dependency unreachable>` | `<…>` | AC-0XX |
| `<concurrent / duplicate request>` | `<…>` | AC-0XX |

## 7 · Non-Goals *(scope fence — the build twin of the chat Scope's non-goals)*
- This feature deliberately does **NOT** `<X>`, because `<reason>`. (NG-001)
- … *Verity fails any unit that crosses an NG line — this is what stops gold-plating.*

## 8 · Acceptance / Definition of Done
> **Done =** all `AC-###` pass · all `INV-###` hold · no `NG-###` crossed · Verity audit green ·
> traceability matrix (§9) fully covered (no orphan tasks, no uncovered requirements).
Pairs one-to-one with the Test Plan.

## 9 · Traceability Matrix *(the spine Verity walks)*
Each row traces one behavior end to end — backward to intent, forward to code and test. This is what
lets the merge-and-audit loop confirm every produced unit maps to a spec line and every spec line is
covered.

| Story | Requirement | Acceptance (EARS) | Build Sheet task (L2) | Test |
|---|---|---|---|---|
| US-001 | REQ-001 | AC-001, AC-002 | T-001 [CT], T-002 [T] | TST-001 |
| US-001 | REQ-001 | AC-003 | T-003 [T] | TST-002 |

## 10 · Open Questions & Assumptions *(same discipline as the chat artifacts)*
Anything unresolved here is a gap Burst must **flag, not fill**.

- `Q-001` — `<undecided question>` — blocks: `<which REQ>`.
- `A-001` — `<assumption>` — confidence: stated|assumed|unverified — depends-on: `<which REQ breaks if false>`.

## 11 · Consumption notes for Burst *(how the stack threads through)*
- **codex** = Constitution (Mission, Tech Stack, Roadmap) + Conventions (the persistent `CLAUDE.md`
  the agent reads every task). Inherited via §0 `inherits`; never restated, never overridden.
- **This Spec** = the sovereign "what + why." Sections 3–6 are the contract Burst builds against.
- **L0** = the compressed Specify+Plan brief that frames one build — derived from §1–§3.
- **L1 (Plan / Technical Design)** = the "how": stack choices, patterns, architecture for this feature,
  derived from §3/§4/§5. Must pass a constitution check against the codex before proceeding.
- **L2 (Build Sheet)** = ordered tasks derived from L1. Each task: carries its `REQ-###`/`AC-###`
  anchors, is tagged **[CT]** (needs Claude reasoning) or **[T]** (mechanical execution) per your
  CT/T split, marks parallel-safe units **[P]**, and names exact file paths (Spec Kit task convention).
  Tasks group by user story and order by dependency.
- **Verity (merge-and-audit)** = the gate. Each produced unit is validated against its anchored
  `AC-###` + `INV-###` + the governing ADRs before merge; anything that violates an ADR or crosses an
  `NG-###` fails the audit *before* it reaches your review lane. Richer Spec → tighter gate → the
  scope-tightening you were after.
- **Checkpoints.** Human sign-off at each phase boundary (Specify→Plan→Tasks→Implement). Before
  Implement, run an `/analyze`-style consistency pass (Spec Kit) over Spec + Plan + Build Sheet to
  catch contradictions, ambiguities, and coverage gaps against the codex.

---

# === WORKED EXAMPLE (illustrative) — SPEC-BRAIN-007: Stage Package export ===
*Filled-in to show the shape. Details are illustrative, not a claim about Stage's real behavior.*

**§0** `spec_id: SPEC-BRAIN-007 · feature: Stage Package export · status: draft · inherits: codex@1.4 ·
bound_by: [CON-FIDELITY-02 "every artifact cites its anchors", CON-PORTABILITY-01 "packages resume in a clean context"]`

**§1 Intent.** Let a user park a workstream and resume it later — or drop it into a fresh chat — by
bundling the thread digest, the reasoning trace, and the linked files into one portable archive, so
no context is lost across the gap. *Inherited:* CON-PORTABILITY-01 (must resume clean), CON-FIDELITY-02
(manifest cites every included artifact).

**§2** US-001 — As a user, I want to export a Stage Package, so that I can resume this work later
without re-establishing context.

**§3 REQ-001 — Produce a single resumable archive on request.** Serves US-001 · Governed by
CON-PORTABILITY-01 / ADR-003.
- Inputs: `thread_id: string; include_files: bool = true; redact: bool = false`
- Outputs: `archive: bundle; manifest: list<entry>`
- I/O mapping: `thread_id → {digest, reasoning_trace, linked_files[]} → archive + manifest`
- Preconditions: thread exists and has ≥1 settled conclusion.
- Postconditions: archive contains a digest, a reasoning trace, and every available linked file;
  manifest lists one entry per intended artifact.
- Invariants: `INV-001` every artifact in the archive has a manifest entry, and every manifest
  entry names its source.
- Acceptance criteria (EARS):
  - `AC-001` — WHEN the user requests a Stage Package, the exporter SHALL produce one archive
    containing the thread digest, the reasoning trace, and the linked files.
  - `AC-002` — IF the assembled package exceeds the size ceiling, THEN the exporter SHALL split it
    into ordered parts and emit a parts manifest.
  - `AC-003` — WHILE a linked file is unavailable, the exporter SHALL substitute a placeholder
    manifest entry recording the file's identifier and last-known location.
  - `AC-004` — WHERE redaction is enabled, the exporter SHALL strip flagged spans before writing the
    archive and record each redaction in the manifest.

**§6 Edge cases** — oversized bundle → AC-002 · missing linked file → AC-003 · redaction on, flagged
span present → AC-004 · thread with no settled conclusion → precondition fails, export refused.

**§7 Non-goals** — NG-001: does NOT re-run or re-summarize the reasoning, only bundles what Brain
already produced (re-summarizing belongs to Brain, not the exporter).

**§9 Traceability** — US-001 → REQ-001 → AC-001 → T-010 [T] "assemble archive" → TST-010 · AC-002 →
T-011 [CT] "size-split logic" → TST-011 · AC-003 → T-012 [T] → TST-012 · AC-004 → T-013 [CT]
"redaction pass" → TST-013.

---

## v0.2 addendum (era 2)

- **Lifecycle:** `draft → interview open (N Qs) → approved → planned → tasked →
  building → complete` — tracked in §0 `status` and mirrored on the board.
- **Sources (D-009):** Zone 1 = prompt-first (parameters carry as *stated*);
  Zone 2 = codex-first. §0 gains `source:` naming the prompt path or batch row.
- **Era-1 harvest (D-011):** interview options may carry the label
  "(era-1 chose …)" — a labeled input, never an authority.
- **Environments (D-012):** the two-axis eight; normalize any "five
  environments" language on conversion.
