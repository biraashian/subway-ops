---
name: plan
description: Produce the L1 technical design from an approved spec, constitution-checked against conventions and interface contracts. Invoke as /plan SPEC-<AREA>-<nnn>.
disable-model-invocation: true
---

# /plan — Approved spec → L1 design (v0.2)

1. Verify the spec is `approved`, zero open Qs; else stop and say what's open.
2. Read: the spec §3–§6, `codex/13-BUILD/CONVENTIONS.md`, the relevant
   `codex/02-DATA-MODEL/` sections, and the existing modules the spec's §4
   touches. Nothing else.
3. Draft `design/PLAN-<spec_id>.md`: module/file layout with exact paths;
   signatures with types; data flow; REQ → module mapping; test strategy per AC;
   dependency and ordering notes.
4. **Constitution check:** walk every convention and contract rule the design
   touches; state compliance explicitly. A conflict is a bench item, never a
   silent workaround.
5. End with the task forecast: 3–8 tasks, one line each, sized ≤90 min
   (anything larger must justify why it can't split). Update the spec's
   lifecycle to `planned`.

Rules: no behavior without a REQ anchor (missing one = spec gap → bench);
existing codebase patterns over new ones (a new pattern is a founder decision).
