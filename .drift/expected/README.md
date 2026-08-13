# `.drift/expected/` — declared schema drift (D-024, amended by D-028)

A task declares here, in `T-####.txt`, every schema change the gate will observe
during its run. The gate then checks the observed drift against that statement
instead of refusing outright.

## What the declaration asserts

Per **D-028** (amending D-024), a declaration asserts:

> Every schema difference between the baseline and the live database **at gate
> time** is accounted for, and here is what each one is.

It does **not** assert "this task caused these changes". D-028 is the authority
for that reading; this file only restates it.

The accounting reading is the one that still catches what the gate exists for:
an unexplained table fails whether or not the current task created it, and "a
table appeared and nobody knows whose it is" is the more alarming case, not the
less.

## The predecessor rule (D-028)

Drift is measured against `.drift/schema-before.json`, which rotates at the
**post-merge** of the previous task. A migration applied by a task that has been
built but not yet merged is therefore still visible to the next task's gate.

1. A task declares the drift **observed at its own gate run**, whatever caused it.
2. Drift inherited from a predecessor whose migration is applied but whose task
   is unmerged is declared with an **attributing comment** naming that task.
3. Once the predecessor merges and post-merge rotates the baseline, the inherited
   line is no longer observed, so it must be **retired** from the inheriting
   task's declaration. The staleness check enforces this rather than obstructing
   it — a declaration still carrying a merged predecessor's line reds the gate
   until someone removes it.
4. **Merge order follows dependency order** wherever it can. Under a clean queue
   the originating task merges first, its table enters the baseline, and the
   later task observes nothing and declares nothing. **Inheritance is the
   exception, not the normal case.**

If you find yourself writing an attributing comment, check first whether the
predecessor should simply merge ahead of you.

Inheritance exists at all only because builds apply migrations to a shared
database (B-0001). D-025 removes that cause; this rule covers the interim.

## Why a declaration instead of an allowlist

Before D-024 the drift check exited non-zero on *any* change, which meant no
migration task could ever reach a green pre-merge. It halted T-0003 on the first
task that touched a migration.

The obvious fix — let drift pass when a migration exists on the branch — was
rejected (B-0022 option B) because it cannot see an `ALTER` a migration makes by
accident, and that is exactly the case worth catching. Demoting drift to a
warning (option C) was rejected because it removes the review surface at the one
moment review actually happens.

So the declaration is the artifact. A reviewer reads the diff and sees precisely
which schema objects are present and accounted for at this point in the queue.

## Format

One drift line per line, exactly as the gate prints them. Blank lines and `#`
comments are ignored, and order does not matter — a declaration is a set of
facts, not a transcript.

```
# T-0003 — ops_worklist_items, the system spine (codex 02)
+ table ops_worklist_items (10 columns)
```

The column count is part of the line and must match what the gate prints. An
example carrying the wrong count teaches the wrong shape — this one said 11
against a 10-column table and contradicted a real declaration two files away.

The line forms the gate emits:

| Form | Meaning |
|---|---|
| `+ table <name> (<n> columns)` | table added |
| `- table <name> REMOVED` | table dropped |
| `+ <table>.<column> <type>` | column added |
| `- <table>.<column> REMOVED` | column dropped |
| `~ <table>.<column> type <old> -> <new>` | type changed |
| `~ <table>.<column> <NULL\|NOT NULL> -> <NULL\|NOT NULL>` | nullability changed |
| `~ <table> primary key <old> -> <new>` | primary key changed |

## How to write one

Run the gate once without a declaration. It prints every observed line. Then, for
each line, decide which of three things it is:

- **Your task's own change** — declare it, with a comment saying why it exists.
- **Inherited from an unmerged predecessor** — declare it, attributing the task
  it belongs to (rule 2 above). First check whether that task should merge ahead
  of you instead; rule 4 says inheritance is the exception.
- **Neither** — an accident. Do NOT declare it. This is the check doing its job:
  fix the migration.

The third case is the whole reason the file exists, and it is why "declare
everything observed" is not the same as "declare everything away". A line you
cannot attribute to yourself or to a named predecessor is a defect.

## Two ways to fail

**Undeclared drift** — observed but not declared. The original protection: a
schema change nobody wrote down.

**A stale declaration** — declared but not observed. Also a failure, and this is
the property that made option A worth the extra file. A declaration that no
longer matches reality is *worse* than no declaration at all, because it reads
as confirmation that someone looked.

## Scope

The declaration covers one task's gate run. It is not deleted afterwards — it
stays as the record of what the schema looked like when that task passed,
alongside its journal entry and its gate log.

Inherited lines are the exception: per rule 3 they are retired once the
predecessor merges, because the staleness check will red the gate on them
otherwise.
