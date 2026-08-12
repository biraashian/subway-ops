# Task Format

*The structured task specification format. What every task must include for the Forge to execute it well.*

---

## Why structured task format matters

Free-form task descriptions produce inconsistent Forge behavior. Some tasks complete cleanly; others surface ambiguity halts; others produce code that passes tests but doesn't address the real intent.

Structured task format addresses this by requiring every task to specify the same set of fields. The Forge knows exactly what to read, what to produce, what to verify, and what to do on completion. The founder writing the task knows exactly what fields to fill in, which forces clear thinking about what the task actually requires.

The structured format also enables analysis: completion rates per task category, halt patterns, budget consumption per category. This analysis informs improvement to the prompt library over time.

---

## Required fields

Every task must include:

### TASK_ID

A unique identifier for the task. Format: `T-XXXX` where XXXX is a sequence number.

Example: `T-0001`, `T-0247`, `T-1023`.

The ID is used in:
- Branch naming: `forge/T-0001-implement-oracle-edition-1`
- Bench item naming: items related to the task reference its ID
- Chronicle entries: log entries tagged with the task ID
- Workshop tracking: queue position and status by ID

### TITLE

Brief description of what the task produces. One sentence.

Example: "Implement Oracle Engine Edition 1 with regime classification per the specification in 02-ENGINES/intelligence/oracle.md"

### TYPE

The category of task. Standard types:

- `engine_implementation`: building an engine for the first time
- `engine_edition`: implementing a new edition of an existing engine
- `pattern_implementation`: implementing pattern logic in the Conjecture Engine
- `dashboard_view`: building a dashboard mode or component
- `test_addition`: adding tests to existing code
- `refactor`: structural improvement without behavior change
- `bug_fix`: correcting a specific defect
- `infrastructure`: configuration or deployment changes (rare; usually requires human edit)
- `documentation`: code-level documentation (excluding codex)

The type drives Workshop categorization and analysis.

### CONTEXT

Files the Forge must read before beginning. Specifies the codex chapters relevant to the task, the existing code files that will be modified or that the new code interacts with, and any specifications referenced.

Example:

```
CONTEXT:
  read:
    - codex/02-ENGINES/intelligence/oracle.md (the engine specification)
    - codex/00-FOUNDATIONS/04-engine-snapshot.md (snapshot requirements)
    - codex/05-RULEBOOK/03-edition-rules.md (edition rules)
  reference:
    - core/tenant_context.py (for connection patterns)
    - core/engine_base.py (the base class for engines)
    - tests/engines/test_engine_base.py (test patterns to follow)
```

The Forge reads `read` files before beginning planning. `reference` files are loaded into context only if needed during implementation.

### DELIVERABLES

What the task produces. Specifies file paths to be created or modified, with brief description of each.

Example:

```
DELIVERABLES:
  create:
    - core/engines/intelligence/oracle.py
    - core/engines/intelligence/oracle_edition_1.py
    - tests/engines/intelligence/test_oracle.py
    - tests/engines/intelligence/test_oracle_edition_1.py
  modify:
    - core/engines/intelligence/__init__.py (export Oracle)
    - core/engine_registry.py (register Oracle as a known engine)
```

### ACCEPTANCE_CRITERIA

What constitutes successful task completion. Tests that must pass, behaviors that must be demonstrated, requirements that must be met.

Example:

```
ACCEPTANCE_CRITERIA:
  tests:
    - test_oracle_classifies_known_regime_correctly (uses fixture data of known regime, verifies classification)
    - test_oracle_returns_regime_string_with_required_fields (regime, confidence, timestamp)
    - test_oracle_handles_insufficient_data_gracefully (returns "unknown" rather than crashing)
    - test_oracle_edition_1_produces_deterministic_output (same input → same output)
  behaviors:
    - Oracle.classify(market_data) returns RegimeResult with regime field, confidence field, timestamp
    - Oracle.classify is deterministic for given input
    - Oracle integrates with engine_snapshot mechanism so Vault trades record which Oracle edition produced the regime classification
  coverage:
    - 80% line coverage minimum on oracle.py and oracle_edition_1.py
```

The Forge verifies all acceptance criteria before marking task complete.

### FORBIDDEN_ACTIONS

What the Forge must not do during this task. Often empty (the layer-1 file permissions cover most prohibitions) but used for task-specific constraints.

Example:

```
FORBIDDEN_ACTIONS:
  - do not modify Oracle's existing interface (other engines depend on it; interface changes require coordinated update)
  - do not introduce new external dependencies without specifying them in this task
  - do not add database queries beyond what is already in core/engines/intelligence/
```

### ON_COMPLETION

What the Forge does when the task is complete. Standard:

- Commit to forge/[task-id] branch with descriptive message
- Update Workshop with task status
- Log Chronicle entry with task ID, completion timestamp, branches modified
- Generate brief summary for the daily report

Sometimes additional steps:

```
ON_COMPLETION:
  standard:
    - commit, workshop update, chronicle entry, daily report summary
  additional:
    - generate engine documentation in /docs/engines/oracle-edition-1.md (per docstring extraction)
    - verify integration with downstream Conductor tests
```

### ON_HALT

What the Forge does if the task halts before completion. Standard:

- Commit work-in-progress to forge/[task-id]-wip branch with clear status
- Surface Bench item describing the halt reason and recommended next action
- Log Chronicle entry
- Continue to next task or end window per halt type

---

## Optional fields

### ESTIMATED_COMPLEXITY

Rough estimate of task complexity. Used by the Forge for budget planning and by the founder for queue management.

Values: `small` (under 30 minutes typical), `medium` (30-90 minutes typical), `large` (90+ minutes typical), `unknown` (no good estimate available).

### DEPENDENCIES

Other tasks that must complete before this one can begin. Specifies task IDs.

Example:

```
DEPENDENCIES:
  - T-0234 (Oracle base class) must complete before this task can begin
```

The Workshop respects dependencies in queue ordering. Dependent tasks do not start until their dependencies complete successfully.

### NOTES

Free-form notes from the founder or Architect explaining context, rationale, or special considerations.

Example:

```
NOTES:
  This is Edition 1 of the Oracle. Edition 2 will add regime transition forecasting,
  which requires this edition's classification to be working first. Keep the interface
  forward-compatible with future regime-transition fields.
  
  The regime taxonomy comes from the historical analysis in our Q3 research review.
  See codex/03-PATTERNS/regime-classification/ for the taxonomy specifics.
```

---

## Example complete task

```yaml
TASK_ID: T-0247
TITLE: Implement Oracle Engine Edition 1 with regime classification per specification
TYPE: engine_implementation
ESTIMATED_COMPLEXITY: large

CONTEXT:
  read:
    - codex/02-ENGINES/intelligence/oracle.md
    - codex/00-FOUNDATIONS/04-engine-snapshot.md
    - codex/05-RULEBOOK/03-edition-rules.md
    - codex/03-PATTERNS/regime-classification/README.md
  reference:
    - core/tenant_context.py
    - core/engine_base.py
    - tests/engines/test_engine_base.py

DELIVERABLES:
  create:
    - core/engines/intelligence/oracle.py
    - core/engines/intelligence/oracle_edition_1.py
    - tests/engines/intelligence/test_oracle.py
    - tests/engines/intelligence/test_oracle_edition_1.py
  modify:
    - core/engines/intelligence/__init__.py
    - core/engine_registry.py

ACCEPTANCE_CRITERIA:
  tests:
    - test_oracle_classifies_known_regime_correctly
    - test_oracle_returns_regime_string_with_required_fields
    - test_oracle_handles_insufficient_data_gracefully
    - test_oracle_edition_1_produces_deterministic_output
    - test_oracle_integrates_with_engine_snapshot
  behaviors:
    - Oracle.classify(market_data) returns RegimeResult
    - Oracle.classify is deterministic
    - Oracle integrates with engine_snapshot mechanism
  coverage:
    - 80% line coverage minimum on oracle.py and oracle_edition_1.py

FORBIDDEN_ACTIONS:
  - do not introduce new external dependencies beyond pandas and numpy
  - do not add database queries beyond core/engines/intelligence/

DEPENDENCIES:
  - T-0234 (Engine base class implementation) must complete first

ON_COMPLETION:
  standard:
    - commit, workshop update, chronicle entry, daily report summary
  additional:
    - generate engine documentation at /docs/engines/oracle-edition-1.md

ON_HALT:
  standard:
    - WIP branch commit, Bench item, Chronicle entry

NOTES:
  Edition 1 is foundation. Edition 2 will add transition forecasting. 
  Keep interface forward-compatible.
  
  The regime taxonomy is in codex/03-PATTERNS/regime-classification/.
```

---

## Where tasks come from

Three sources:

**Founder authorship.** The founder writes a task directly in the Workshop. Most common in early operation.

**Architect recommendation.** The Architect (post-Year 2) analyzes the codebase against the codex and identifies missing components. It generates task drafts that the founder reviews and approves before queueing.

**Edition specifications.** The Designer specifies new editions of existing components. The specification includes a task draft that follows the standard format.

In all cases, the task enters the Workshop queue, the founder reviews and approves, and the Forge consumes it during the next window.

---

## Task lifecycle

1. **Drafted** — task created but not yet reviewed
2. **Approved** — founder approved; task is in queue awaiting Forge availability
3. **In progress** — Forge has started executing this task
4. **Completed** — task finished successfully; branch ready for review
5. **Halted** — task halted; Bench item created; awaiting human resolution
6. **Merged** — branch merged to main; codex documentation updated; task retired

The Workshop tracks all tasks across all states. Founder review focuses on Approved (deciding queue order), Halted (resolving issues), and Completed (reviewing branches before merge).

---

## What good task specifications produce

A well-specified task produces:

- Clear Forge execution without ambiguity halts
- Code that meets the actual requirement (not just the literal interpretation)
- Tests that catch real issues
- Documentation that's useful months later

A poorly specified task produces:

- Ambiguity halts requiring multiple Bench cycles to resolve
- Code that technically passes tests but doesn't address the real intent
- Iteration limits hit because the task wasn't well-defined
- Wasted Forge budget on rework

The discipline of writing good task specifications is institutional capability that grows with practice. Year 1 task specifications will be rougher; Year 5 specifications will be precise. The improvement compounds: better specifications produce more reliable Forge work, which builds trust, which enables more advanced operating modes.

---

## v0.2 addendum (era 2)

Required additional block:
```
ANCHORS:
  spec: SPEC-<AREA>-<nnn>
  req:  [REQ-###]
  ac:   [AC-###, AC-###]
```
Tags: only `[P]` survives (parallel-safe: no shared DELIVERABLES, no dependency
edge). Size small/medium (30–90 min); split larger. The quality bar is stated
once: ACCEPTANCE_CRITERIA ends with "`scripts/verify.sh <T-id> pre-merge` exits
0" — numbers live in the script alone (D-014). The journal entry (≥40 lines,
target 150) is written BEFORE the pre-merge run; the gate asserts it (D-003).
