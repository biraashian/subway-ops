"""Every scheduled entrypoint records itself in ops_job_runs.

CLAUDE.md calls this non-negotiable: anything launched on a schedule must wrap
its work in ``track_job(...)``. The value is entirely in the breach — a job that
does not record itself is invisible when it stops running, and "the cron silently
stopped three weeks ago" is the failure mode the whole observability layer exists
to prevent.

The set of scheduled scripts is derived from the workflow files rather than
hardcoded, so adding a cron without a ``track_job`` fails on the next run
instead of waiting for someone to remember to update a list here.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from ._base import Result, failed, ok

NAME = "scheduled jobs tracked"

# `python scripts/foo.py`, `uv run python scripts/foo.py`, with or without args.
SCRIPT_RE = re.compile(r"python\s+(scripts/[A-Za-z0-9_./-]+\.py)")

# Not every workflow-invoked script is a scheduled job. migrate.py runs as a
# setup step inside other jobs; notify_failure.py is the failure handler and
# recording it would create a loop where the tracker's own failure needs
# tracking.
EXEMPT = {
    "scripts/migrate.py",
    "scripts/notify_failure.py",
}


def _imported_from_package(tree: ast.Module) -> dict[str, str]:
    """Map imported symbol -> the subway_ops module it came from."""
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("subway_ops"):
            for alias in node.names:
                out[alias.asname or alias.name] = node.module or ""
    return out


def _called_names(tree: ast.Module) -> set[str]:
    return {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }


def _function_tracks(module_path: Path, func_name: str) -> bool:
    """True if ``func_name`` in ``module_path`` wraps its body in track_job.

    Scoped to the function, not the module. A module-wide search would pass any
    script that happens to import from a package where *something else* tracks —
    and since nearly every ingest and mart module tracks itself, that fallback
    made this check vacuous.
    """
    try:
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return False
    for node in ast.walk(tree):
        is_target = (
            isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == func_name
        )
        if is_target and "track_job" in ast.unparse(node):
            return True
    return False


def _tracks(script: Path, repo_root: Path) -> bool:
    """True if the script records its run, directly or in the function it delegates to.

    Thin entrypoints are the norm: ``uos_pull.py`` is twenty lines that call
    ``subway_ops.uos.ingest.ingest_recent``, and the ``track_job`` wrapper lives
    inside that function. Resolution is one level and targeted at the specific
    imported callable, so "imports a package that tracks somewhere" is not enough.
    """
    source = script.read_text(encoding="utf-8")
    if "track_job" in source:
        return True
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False

    imports = _imported_from_package(tree)
    for name in _called_names(tree) & imports.keys():
        target = repo_root / "src" / Path(*imports[name].split("."))
        for candidate in (target.with_suffix(".py"), target / "__init__.py"):
            if candidate.exists() and _function_tracks(candidate, name):
                return True
    return False


def check(repo_root: Path) -> Result:
    workflows = repo_root / ".github" / "workflows"
    if not workflows.is_dir():
        return ok(NAME, "no workflows to check")

    referenced: set[str] = set()
    for wf in sorted(workflows.glob("*.yml")) + sorted(workflows.glob("*.yaml")):
        referenced |= set(SCRIPT_RE.findall(wf.read_text(encoding="utf-8")))

    scheduled = sorted(referenced - EXEMPT)
    violations: list[str] = []
    for rel in scheduled:
        path = repo_root / rel
        if not path.exists():
            violations.append(f"{rel}: referenced by a workflow but does not exist")
            continue
        if not _tracks(path, repo_root):
            violations.append(f"{rel}: scheduled by a workflow but never calls track_job()")

    if violations:
        return failed(NAME, f"{len(violations)} untracked job(s)", violations)
    return ok(NAME, f"{len(scheduled)} scheduled script(s) tracked")
