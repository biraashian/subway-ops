"""Every ingest module is wired into the daily orchestrator.

Step 4 of "How to add a new ingest endpoint" is to register the new module in
``scripts/daily_pull.py``. It is the easiest of the five steps to forget, and
forgetting it is invisible: the module exists, its tests pass, its migration
applies, and it simply never runs. The gap only shows up months later as a table
that stopped filling.
"""

from __future__ import annotations

from pathlib import Path

from ._base import Result, failed, ok

NAME = "ingests registered in daily_pull"

ORCHESTRATOR_REL = Path("scripts/daily_pull.py")


def check(repo_root: Path) -> Result:
    ingest_dir = repo_root / "src" / "subway_ops" / "ingest"
    orchestrator = repo_root / ORCHESTRATOR_REL
    if not ingest_dir.is_dir():
        return failed(NAME, "no ingest package", [str(ingest_dir)])
    if not orchestrator.exists():
        return failed(NAME, "no orchestrator", [str(ORCHESTRATOR_REL)])

    body = orchestrator.read_text(encoding="utf-8")
    modules = sorted(p.stem for p in ingest_dir.glob("*.py") if not p.stem.startswith("_"))

    violations = [
        f"src/subway_ops/ingest/{name}.py: never referenced in {ORCHESTRATOR_REL} "
        f"— add it to _default_daily_ingests() or _default_weekly_ingests()"
        for name in modules
        if f"{name}." not in body
    ]

    if violations:
        return failed(NAME, f"{len(violations)} unwired ingest(s)", violations)
    return ok(NAME, f"{len(modules)} ingest(s) wired")
