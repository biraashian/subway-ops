"""No ``print()`` in library code outside a ``__main__`` guard.

The package logs through structlog so that output is structured, levelled and
routed. A stray ``print`` bypasses all of it: invisible in prod JSON logs,
unfilterable, and in a Streamlit or worker context it goes nowhere at all.

``if __name__ == "__main__":`` blocks are exempt — those are scripts, and a
couple of modules legitimately emit DDL that way.
"""

from __future__ import annotations

import ast
from pathlib import Path

from ._base import Result, failed, iter_python_files, ok

NAME = "no print() in library code"


def _is_main_guard(node: ast.stmt) -> bool:
    """True for ``if __name__ == "__main__":``."""
    if not isinstance(node, ast.If):
        return False
    test = node.test
    return (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == "__name__"
        and len(test.comparators) == 1
        and isinstance(test.comparators[0], ast.Constant)
        and test.comparators[0].value == "__main__"
    )


def _entrypoint_names(tree: ast.Module) -> set[str]:
    """Functions invoked directly by the ``__main__`` guard.

    The convention here is ``if __name__ == "__main__": sys.exit(main())``, so
    the printing usually happens one frame down in ``main()`` / ``_main()``
    rather than lexically inside the guard. Those functions ARE the command-line
    entrypoint and printing is their job. Resolved one level only — a helper
    buried three calls deep is not an entrypoint, it is library code.
    """
    names: set[str] = set()
    for node in tree.body:
        if not _is_main_guard(node):
            continue
        for child in ast.walk(node):
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                names.add(child.func.id)
    return names


def _print_lines(tree: ast.Module) -> list[int]:
    """Line numbers of print() calls that are not part of a CLI entrypoint."""
    exempt: set[int] = set()

    def _mark(node: ast.AST) -> None:
        for child in ast.walk(node):
            if hasattr(child, "lineno"):
                exempt.add(child.lineno)

    entrypoints = _entrypoint_names(tree)
    for node in tree.body:
        is_entrypoint_def = (
            isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name in entrypoints
        )
        if _is_main_guard(node) or is_entrypoint_def:
            _mark(node)

    hits = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "print"
            and node.lineno not in exempt
        ):
            hits.append(node.lineno)
    return sorted(hits)


def check(repo_root: Path) -> Result:
    package = repo_root / "src" / "subway_ops"
    if not package.is_dir():
        return failed(NAME, "package not found", [str(package)])

    files = iter_python_files(package)
    violations = []
    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:  # a file that will not parse is its own problem
            violations.append(f"{path.relative_to(repo_root)}: does not parse — {exc}")
            continue
        violations += [
            f"{path.relative_to(repo_root)}:{line}: print() outside a __main__ block"
            for line in _print_lines(tree)
        ]

    if violations:
        return failed(NAME, f"{len(violations)} stray print(s)", violations)
    return ok(NAME, f"{len(files)} module(s) clean")
