# `.drift/expected/` — declared schema drift (D-024)

A task declares here, in `T-####.txt`, every schema change the gate will observe
during its run. The gate then checks the observed drift against that statement
instead of refusing outright.

## What the declaration asserts

**"Every schema difference between the baseline and the live database is
accounted for, and here is what each one is."**

Note what that is *not*: it is not "this task caused these changes". The
distinction matters more than it first appears, and it was found by running the
gate rather than by reasoning about it.

Drift is measured against `.drift/schema-before.json`, which rotates at the
**post-merge** of the previous task. So a migration applied by a task that has
been built but not yet merged is still visible as drift to the next task's gate.
T-0010 changes no schema whatsoever and still observed T-0003's
`ops_worklist_items`, because T-0003's migration was applied to the shared
database while T-0003 itself sat unmerged.

Under the "this task caused it" reading there is no honest thing to write.
Under the accounting reading there is: declare the line, and attribute it in a
comment. The point of the file is that no schema change is unaccounted for, and
attribution in a comment is what makes it accountable.

This is also a symptom of B-0001 / D-025 — with no test database, migrations are
applied to production during a build. Once tests run against a container, most
of this class disappears.

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
which schema objects the task meant to touch.

## Format

One drift line per line, exactly as the gate prints them. Blank lines and `#`
comments are ignored, and order does not matter — a declaration is a set of
facts, not a transcript.

```
# T-0003 — ops_worklist_items, the system spine (codex 02)
+ table ops_worklist_items (11 columns)
```

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

Run the gate once without a declaration. It prints every observed line; paste
the ones your task intended into `T-####.txt` and add a comment saying why.

If a line appears that your task did **not** intend, that is the check doing its
job — fix the migration rather than declaring the accident.

## Two ways to fail

**Undeclared drift** — observed but not declared. The original protection: a
schema change nobody wrote down.

**A stale declaration** — declared but not observed. Also a failure, and this is
the property that made option A worth the extra file. A declaration that no
longer matches reality is *worse* than no declaration at all, because it reads
as confirmation that someone looked.

## Scope

The declaration covers one task. It is not deleted afterwards — it stays as the
record of what that task changed, alongside its journal entry and its gate log.
