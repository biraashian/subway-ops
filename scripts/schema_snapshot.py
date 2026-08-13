"""Capture the live database schema, and diff two captures.

This is the contract-drift gate. Verity's spine tracked Python module contracts;
in a warehouse the contract that matters is the schema — a widened NUMERIC, a
dropped NOT NULL, a renamed key. Those changes are invisible in a code review
that only reads the migration, and they surface at 03:00 as an ingest failing
against a column that no longer means what it did.

    uv run python scripts/schema_snapshot.py --out .drift/schema-now.json
    uv run python scripts/schema_snapshot.py --diff --before A.json --after B.json

The snapshot deliberately does NOT skip when DATABASE_URL is unset. A drift gate
that reports success without looking at a database is worse than no gate: it
turns "unverified" into "verified" on the log.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from subway_ops.config import settings
from subway_ops.db.connection import execute_sql

REPO_ROOT = Path(__file__).resolve().parent.parent

SCHEMA_SQL = """
SELECT c.table_name,
       c.column_name,
       c.data_type,
       c.is_nullable,
       c.numeric_precision,
       c.numeric_scale,
       c.character_maximum_length
FROM information_schema.columns c
JOIN information_schema.tables t
  ON t.table_schema = c.table_schema AND t.table_name = c.table_name
WHERE c.table_schema = 'public' AND t.table_type = 'BASE TABLE'
ORDER BY c.table_name, c.column_name
"""

PK_SQL = """
SELECT tc.table_name, kcu.column_name, kcu.ordinal_position
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON kcu.constraint_name = tc.constraint_name
 AND kcu.table_schema = tc.table_schema
WHERE tc.table_schema = 'public' AND tc.constraint_type = 'PRIMARY KEY'
ORDER BY tc.table_name, kcu.ordinal_position
"""


def _column_type(row: tuple[Any, ...]) -> str:
    """Render a column's type the way a migration would declare it."""
    _, _, data_type, _, precision, scale, max_len = row
    if data_type == "numeric" and precision is not None:
        return f"numeric({precision},{scale or 0})"
    if max_len is not None:
        return f"{data_type}({max_len})"
    return str(data_type)


def capture() -> dict[str, Any]:
    if not settings.database_url:
        raise SystemExit(
            "DATABASE_URL is not set, so the schema cannot be captured. "
            "This is a hard failure on purpose: a drift check that passes "
            "without reading a database has verified nothing."
        )

    tables: dict[str, Any] = {}
    for row in execute_sql(SCHEMA_SQL):
        table, column = row[0], row[1]
        entry = tables.setdefault(table, {"columns": {}, "primary_key": []})
        entry["columns"][column] = {
            "type": _column_type(row),
            "nullable": row[3] == "YES",
        }
    for table, column, _ in execute_sql(PK_SQL):
        if table in tables:
            tables[table]["primary_key"].append(column)
    return tables


def diff(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    changes: list[str] = []

    for table in sorted(set(after) - set(before)):
        changes.append(f"+ table {table} ({len(after[table]['columns'])} columns)")
    for table in sorted(set(before) - set(after)):
        changes.append(f"- table {table} REMOVED")

    for table in sorted(set(before) & set(after)):
        old, new = before[table], after[table]
        old_cols, new_cols = old["columns"], new["columns"]
        for column in sorted(set(new_cols) - set(old_cols)):
            changes.append(f"+ {table}.{column} {new_cols[column]['type']}")
        for column in sorted(set(old_cols) - set(new_cols)):
            changes.append(f"- {table}.{column} REMOVED")
        for column in sorted(set(old_cols) & set(new_cols)):
            o, n = old_cols[column], new_cols[column]
            if o["type"] != n["type"]:
                changes.append(f"~ {table}.{column} type {o['type']} -> {n['type']}")
            if o["nullable"] != n["nullable"]:
                was = "NULL" if o["nullable"] else "NOT NULL"
                now = "NULL" if n["nullable"] else "NOT NULL"
                changes.append(f"~ {table}.{column} {was} -> {now}")
        if old["primary_key"] != new["primary_key"]:
            changes.append(f"~ {table} primary key {old['primary_key']} -> {new['primary_key']}")

    return changes


def parse_declaration(text: str) -> list[str]:
    """Parse a `.drift/expected/T-####.txt` declaration into drift lines.

    Blank lines and `#` comments are ignored, so a declaration can explain
    itself to a reviewer — which is most of the point of having one.
    """
    lines = []
    for raw in text.splitlines():
        stripped = raw.split("#", 1)[0].strip()
        if stripped:
            lines.append(stripped)
    return lines


def compare_declaration(
    observed: list[str], declared: list[str]
) -> tuple[list[str], list[str]]:
    """Return ``(undeclared, stale)`` drift lines.

    ``undeclared`` — observed but not declared. The original protection: a
    schema change nobody wrote down.

    ``stale`` — declared but not observed. Equally a failure, and the reason
    D-024 chose a declaration over a simple allowlist: a declaration that no
    longer matches reality is *worse* than none, because it reads as
    confirmation that someone looked.

    Order-insensitive — a declaration is a set of facts, not a transcript.
    """
    obs, dec = set(observed), set(declared)
    return sorted(obs - dec), sorted(dec - obs)


def _load(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _report_declared(changes: list[str], expected: Path) -> int:
    """Declared-drift mode (D-024, amended by D-028). Returns an exit code.

    The declaration accounts for every difference observed at gate time —
    including drift inherited from an unmerged predecessor, which carries an
    attributing comment. Undeclared drift fails as it always did; a stale line
    fails too, and that is what retires an inherited declaration once its
    predecessor merges.
    """
    if not expected.exists():
        print(f"declaration not found: {expected}")
        return 1

    declared = parse_declaration(expected.read_text(encoding="utf-8"))
    undeclared, stale = compare_declaration(changes, declared)

    if not undeclared and not stale:
        print(f"drift matches declaration ({len(changes)} change(s), all declared)")
        return 0

    if undeclared:
        print(f"{len(undeclared)} UNDECLARED change(s) — not in {expected.name}:")
        for line in undeclared:
            print(f"  {line}")
    if stale:
        print(f"{len(stale)} STALE declaration line(s) — declared but not observed:")
        for line in stale:
            print(f"  {line}")
    print(
        f"\nEvery schema difference must be accounted for in {expected}, and "
        "every declared line must still be true. An undeclared change is drift "
        "nobody wrote down; a stale line is worse, because it reads as "
        "confirmation that someone looked. If a line was inherited from a "
        "predecessor that has now merged, retire it (D-028 rule 3)."
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="write a snapshot to this path")
    parser.add_argument("--diff", action="store_true", help="compare two snapshots")
    parser.add_argument("--before", type=Path, help="baseline snapshot (with --diff)")
    parser.add_argument("--after", type=Path, help="current snapshot (with --diff)")
    parser.add_argument(
        "--expected",
        type=Path,
        help="declaration of intended drift (with --diff) — see .drift/expected/README.md",
    )
    args = parser.parse_args(argv)

    # --expected only means anything alongside --diff. Silently ignoring it
    # would let `--expected <file>` without `--diff` look like a check that
    # ran, which is the same vacuous-pass shape this gate exists to prevent.
    if args.expected is not None and not args.diff:
        parser.error("--expected requires --diff")

    if args.diff:
        if not args.before or not args.after:
            parser.error("--diff requires --before and --after")
        changes = diff(_load(args.before), _load(args.after))

        if args.expected is not None:
            return _report_declared(changes, args.expected)

        # --- Undeclared mode: any drift is a failure ----------------------
        if not changes:
            print("no drift")
            return 0
        print(f"{len(changes)} change(s) vs the baseline:")
        for line in changes:
            print(f"  {line}")
        print(
            "\nSchema drift is not automatically wrong — a migration is supposed "
            "to change the schema. It must be INTENDED. Declare it in "
            "`.drift/expected/T-####.txt` (D-024) and the gate will check the "
            "change against your statement instead of refusing outright."
        )
        return 1

    tables = capture()
    columns = sum(len(t["columns"]) for t in tables.values())
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(tables, indent=2, sort_keys=True), encoding="utf-8")
    print(f"{len(tables)} tables, {columns} columns")
    return 0


if __name__ == "__main__":
    sys.exit(main())
