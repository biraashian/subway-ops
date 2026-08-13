---
status: authoritative
source: harvested from the pre-Burst CLAUDE.md and SUBWAY_OPS_BUILD_PLAYBOOK.md §4 and §6
---

# 02 — The Data Model

## The four layers

Data flows one way. Each layer is derivable from the one before it, which is
what makes any of it recoverable.

| Prefix | Contents | Rebuild rule |
|---|---|---|
| `raw_*` | Append-only, untouched API payloads as JSONB | Never rebuilt. This is the tape. |
| `stg_*` | Typed, deduplicated rows | Fully derivable from `raw_*` |
| `mart_*` | Denormalized, read-optimized | Fully derivable from `stg_*` |
| `ref_*` | Reference data — stores, users, managers, employees | Seeded from `seed/*.csv`, upserted |
| `ops_*` | System metadata — jobs, migrations, backfill, variances, worklist | Written by the system about itself |

`raw_` exists so that a parsing bug is recoverable without re-hitting the API,
and so that "what did the API actually say that day" is always answerable. It is
append-only in the strict sense: no updates, no deletes, ever.

## Column conventions

- **Money is `NUMERIC(12,4)`. Never float.** In Python it is `Decimal`, never
  `float`. A cent lost to binary rounding in a reconciliation mart is a variance
  nobody can explain, and explaining variances is the entire product.
  Enforced by `tools/verify_invariants/check_money_types.py`.
- **Timestamps are `TIMESTAMPTZ`, stored UTC.** Rendered in store-local time at
  the edge, never stored that way.
- **Dates are `DATE` holding a Subway business date**, per
  [01-CALENDAR](../01-CALENDAR/README.md). A `DATE` column in this system never
  means a calendar date unless its name says so.
- **Booleans are `is_*`.**
- **Store numbers are TEXT.** They are identifiers, not quantities. Leading
  zeros and non-numeric test values both matter.
- **Percentages are stored as fractions** — 0.2723, not 27.23. The Fresh Connect
  API returns whole-number percents; the transform layer divides by 100 on the
  way in so every downstream comparison is against a fraction.

## Idempotency is the recovery path

**Every ingest UPSERTs on a natural composite key.** Re-running an ingest never
duplicates data. This is not a nicety — it is the designed response to every
failure mode. A job died halfway, the API rate-limited, a day looks wrong: the
answer is always "run it again."

That property is what makes the backfill resumable across days
(`ops_backfill_progress`) and what makes a 3am failure something to look at in
the morning rather than something to page about.

## Every scheduled job records itself

Anything launched on a schedule or by a CLI wraps its work in
`track_job(name)` from `subway_ops.db.job_runs`:

```python
with track_job("ingest_daily_sales") as meta:
    meta["rows_written"] = n
```

Set `rows_written` for ingests; anything else useful for debugging goes
elsewhere in `meta` and lands in the `metadata` JSONB column. Exceptions are
caught, recorded as failures, and re-raised.

The value is entirely in the breach. A job that does not record itself is
invisible when it stops running, and "the cron silently stopped three weeks ago"
is precisely what this exists to prevent. Enforced by
`tools/verify_invariants/check_track_job.py`.

## The wide table is deliberate

`stg_controlsheet_weekly` is roughly 820 columns: every control-sheet section
field flattened to one column per day of week plus a footer total. This looks
wrong and is not.

The alternative — a long `(store, week, section, field, day, value)` table —
turns every dashboard read into a pivot. Reads here are cheap because the
`(restaurant_number, week_end_date)` primary key is the only access path that
matters, and queries stay narrow because callers select the handful of columns
they need. Postgres does not charge for columns you do not select.

The cost is real and should be known: adding a control-sheet field means a
migration, and the DDL is generated rather than hand-written (see the
`__main__` block in `subway_ops/ingest/controlsheet.py`).

## Migrations are append-only

Never edit a migration once applied. A new change is a new file. An edited
migration no longer describes the schema that exists, so a fresh environment
built from the migrations diverges from production and nobody finds out until an
ingest fails against the wrong column.

Enforced by `tools/verify_invariants/check_migrations_append_only.py` against a
sha256 manifest at `src/subway_ops/db/migrations/CHECKSUMS.txt`. Adding a
migration is expected; run `uv run python -m tools.verify_invariants --update` to
record it. Changing or deleting one already recorded fails the gate.

Schema changes are additionally visible in review through the drift gate — see
`scripts/schema_snapshot.py`, whose baseline is committed at
`.drift/schema-before.json` precisely so a schema change shows up in a diff.

## All SQL is parameter-bound

Raw SQL goes through `db.connection.execute_sql` with bound parameters. Never
string-format SQL, including for identifiers that "obviously" come from a
trusted source.

## The worklist is the spine

`ops_worklist_items` is the table the whole product converges on: typed,
role-assigned, with a state (`open` / `in_progress` / `resolved` / `dismissed`),
a due date, a reference back to whatever produced it, and — once it leaves a
live state — the time that happened.

Every reconciliation exception, expiry nudge, ungraded task, and pending
approval emits a row. One table, one screen, and the answer to "what needs a
human today." A capability that detects a problem but emits no worklist item has
not finished — it has produced a report.

**Which states suppress a re-raise (D-029).** Producers are sweeps: they run
every cycle and re-assert everything they still believe. So the state machine,
not the producer, decides what stays quiet. `open` and `in_progress` suppress
because the work is outstanding. **`dismissed` also suppresses** — a human
looked and said no, and a sweep that re-raises it the same night has overruled
them. `resolved` does **not** suppress: the problem was fixed, and if it recurs
that is genuinely new work.

Dismissal is therefore durable and needs an explicit reopen. The cost is
accepted deliberately: a real new occurrence of a dismissed problem stays
invisible until someone reopens it. The alternative — dismissal that a sweep
undoes — is a button that does nothing, which is worse than no button.

**Resolution timing, not resolution actors (D-030).** The shape carries *when* an
item left a live state. It does not carry *who* did it. No producer can populate
an actor today, and the worklist screen (SPEC-APP-001) is where that question
becomes real; a nullable actor column filled by nobody reads as a record that
someone was tracked when nothing was.

## API models forbid unknown fields

Every Fresh Connect Pydantic model inherits `_FCModel`, which sets
`extra="forbid"`. An upstream field we have never seen must fail loudly rather
than be silently dropped. Enforced by
`tools/verify_invariants/check_extra_forbid.py`.
