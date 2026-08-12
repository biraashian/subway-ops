"""Shared contract for the invariant checks.

Each check is a module exposing ``check(repo_root: Path) -> Result``. Checks are
pure functions over the repo tree: no database, no network, no environment. That
is deliberate — these run in the fast ``adhoc`` phase of every build loop, so
they must be cheap and must never fail for a reason outside the working tree.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Result:
    """The verdict of one invariant check.

    ``detail`` is the one-line summary shown when the check passes.
    ``violations`` are the specific offending items, printed when it fails.
    """

    name: str
    ok: bool
    detail: str
    violations: list[str] = field(default_factory=list)


def ok(name: str, detail: str) -> Result:
    return Result(name=name, ok=True, detail=detail)


def failed(name: str, detail: str, violations: list[str]) -> Result:
    return Result(name=name, ok=False, detail=detail, violations=violations)


def iter_python_files(root: Path) -> list[Path]:
    """Every tracked-looking .py file under ``root``, caches excluded."""
    skip = {"__pycache__", ".venv", ".git", ".mypy_cache", ".ruff_cache", ".pytest_cache"}
    return sorted(p for p in root.rglob("*.py") if not any(part in skip for part in p.parts))


def strip_sql_comments(sql: str) -> str:
    """Drop ``--`` line comments so prose can't trip a keyword scan.

    Migration 017 says "real-world inventory anomalies" in a comment; a naive
    grep for ``real`` flags it. Block comments are not stripped: none of the
    migrations use them, and a half-correct parser is worse than a documented
    limitation.
    """
    out = []
    for line in sql.splitlines():
        idx = line.find("--")
        out.append(line if idx == -1 else line[:idx])
    return "\n".join(out)
