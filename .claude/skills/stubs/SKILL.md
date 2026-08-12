---
name: stubs
description: Populate the board's Backlog with the complete DAG - every component as a node with source, kind, phase, and edges. Idempotent; rewrites only the Backlog section. Invoke as /stubs.
disable-model-invocation: true
---

# /stubs — The whole graph, day one

Density arrives just-in-time; the GRAPH must exist immediately — you cannot
topologically order nodes you haven't enumerated.

1. Walk `codex/12-PROMPTS/` in numeric order. Each entry → one node. A batch
   entry → one node per bolded component row (source = batch file + the
   component's codex chapter).
2. Cross-check the node set against the phase tables in
   `codex/00-INSTITUTION/` and against what already exists in
   `src/subway_ops/`. Flag any component that appears in neither the source
   queue nor a phase table — an unenumerated component is how scope leaks.
3. Per node record: slug · source (prompt path or batch+chapter) ·
   kind (`greenfield` | `retro-spec`, per D-016) · phase (A–E) ·
   edges (from stated prerequisites).
4. Honor the standing dependency facts, which no phase ordering may violate:
   - `SPEC-PPL-001` (roster + wages) precedes everything in Phases C, D and E —
     scheduling, timecards, training records and employee KPIs all key on it.
   - `SPEC-APP-001` (app shell + `ops_worklist_items`) precedes every node that
     emits a worklist item, which is most of Phase B.
   - `SPEC-TGT-001` precedes the target-attainment mart and all of Phase C's
     budget checks.
   - `SPEC-CAP-001` (capture) precedes every `SPEC-RCN-*` node that ingests a
     photographed document.
5. Rewrite ONLY the board's `## Backlog` section. Print the summary: node count,
   edge count, greenfield/retro-spec split, first ten nodes in topological order.
