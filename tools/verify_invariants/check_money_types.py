"""Money never lands in a binary float column.

``NUMERIC`` is exact; ``FLOAT``/``REAL``/``DOUBLE PRECISION`` are not. A cent
lost to binary rounding in a reconciliation mart is a variance that cannot be
explained, and this system's entire premise is explaining variances.

The check is deliberately blunt: no approximate numeric type appears in any
migration at all. A heuristic that tried to guess which columns hold money from
their names would miss ``over_short`` and flag ``factor``; forbidding the types
outright has no false negatives and the false positives are hypothetical --
nothing in this domain needs an approximate number in the database.
"""

from __future__ import annotations

import re
from pathlib import Path

from ._base import Result, failed, ok, strip_sql_comments

NAME = "money is NUMERIC, never float"

FLOAT_TYPE_RE = re.compile(
    r"\b(FLOAT\s*(\(\s*\d+\s*\))?|REAL|DOUBLE\s+PRECISION)\b",
    re.IGNORECASE,
)


def check(repo_root: Path) -> Result:
    directory = repo_root / "src" / "subway_ops" / "db" / "migrations"
    if not directory.is_dir():
        return failed(NAME, "no migrations directory", [str(directory)])

    files = sorted(directory.glob("*.sql"))
    violations = []
    for path in files:
        body = strip_sql_comments(path.read_text(encoding="utf-8"))
        for lineno, line in enumerate(body.splitlines(), start=1):
            match = FLOAT_TYPE_RE.search(line)
            if match:
                violations.append(
                    f"{path.name}:{lineno}: approximate numeric type "
                    f"{match.group(0)!r} — use NUMERIC"
                )

    if violations:
        return failed(NAME, f"{len(violations)} float column(s)", violations)
    return ok(NAME, f"{len(files)} migration(s) free of float types")
