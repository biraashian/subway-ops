---
name: sweep
description: Weekly deviation sweep - state of play, drift and contradiction flags against DECISIONS.md and the specs, revert count, WIP staleness, runway health. Invoke as /sweep.
disable-model-invocation: true
---

# /sweep — Is this still the thing we set out to build (v0.2)

1. **Snapshot** from the board + last ~30 chronicle lines: merged / awaiting
   audit / halted / queued counts · open bench count · velocity (tasks closed
   per day, 7-day) · **revert count** since last sweep (Layer 9's question;
   D-004's reopen trigger watches here).
2. **Diff against anchors:** uncovered ACs (spec lines no task carries) · orphan
   tasks (no live anchor) · forge/* changes outside any DELIVERABLES · live
   state contradicting any D-### in `DECISIONS.md` or any NG-###.
3. **Health rules:** WIP items sitting >2 days · bench items OPEN >3 days ·
   runway below floor 3 · provisioning-horizon items aging without owner action
   · spec pipeline less than one component ahead of the batch cliff.
4. Output: State of Play ≤10 lines → ⚑ drift flags (each with where it entered)
   → ⚑ contradiction flags (naming the D-### violated) → the three
   highest-leverage next actions. Never smooth a contradiction.
