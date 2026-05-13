"""Generic ``INSERT ... ON CONFLICT DO UPDATE`` helper.

Every Phase 2 ingest converges on the same pattern: a list of typed rows,
a known set of natural-key columns, and the desire to make re-running the
ingest a no-op. This module centralises that pattern.

The helper is deliberately small and SQL-injection-aware: table and column
identifiers are validated against a strict regex before being interpolated
into the statement.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text

from subway_ops.db.connection import get_engine

# Identifiers we accept directly into SQL — letters, digits, underscores
# only. Anything else hints at injection or a typo and is refused.
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_identifier(name: str, kind: str) -> str:
    if not _IDENT_RE.match(name):
        raise ValueError(f"Invalid {kind} identifier: {name!r}")
    return name


def upsert_rows(table: str, rows: list[dict[str, Any]], key_cols: list[str]) -> int:
    """UPSERT ``rows`` into ``table`` keyed on ``key_cols``.

    Returns the number of rows passed in (every row is either inserted or
    updates an existing one). Empty input returns 0 without touching the DB.

    Identifiers are validated; values are bound via SQLAlchemy parameters.
    All rows in a single call must share the same column set.
    """
    if not rows:
        return 0

    table = _validate_identifier(table, "table")
    for k in key_cols:
        _validate_identifier(k, "key column")

    columns = list(rows[0].keys())
    for c in columns:
        _validate_identifier(c, "column")

    for r in rows[1:]:
        if list(r.keys()) != columns:
            raise ValueError("All rows passed to upsert_rows must share the same columns.")

    key_set = set(key_cols)
    for k in key_cols:
        if k not in key_set or k not in columns:
            raise ValueError(f"Key column {k!r} missing from row columns {columns!r}.")
    non_key = [c for c in columns if c not in key_set]

    col_list = ", ".join(columns)
    placeholders = ", ".join(f":{c}" for c in columns)
    conflict_cols = ", ".join(key_cols)

    if non_key:
        update_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in non_key)
        sql = (
            f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
            f"ON CONFLICT ({conflict_cols}) DO UPDATE SET {update_clause}"
        )
    else:
        # No non-key columns means there is nothing to update on conflict.
        sql = (
            f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
            f"ON CONFLICT ({conflict_cols}) DO NOTHING"
        )

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(sql), rows)

    return len(rows)
