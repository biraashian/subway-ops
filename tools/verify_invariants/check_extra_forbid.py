"""Every FreshConnect model forbids unknown fields.

``extra="forbid"`` is what makes an upstream API change fail loudly instead of
silently dropping a field we never knew arrived. Task 1.3's discovery pass exists
because of exactly this: the models drifted from the live payloads and the only
reason it surfaced was that parsing raised.

The rule is structural — a model must inherit ``_FCModel``, which sets the
config once — rather than a search for the string ``extra="forbid"``, so a
per-class override that quietly relaxes it is still caught.
"""

from __future__ import annotations

import ast
from pathlib import Path

from ._base import Result, failed, ok

NAME = "API models forbid extra fields"

BASE_CLASS = "_FCModel"
MODELS_REL = Path("src/subway_ops/freshconnect/models.py")


def _base_names(node: ast.ClassDef) -> list[str]:
    names = []
    for base in node.bases:
        if isinstance(base, ast.Name):
            names.append(base.id)
        elif isinstance(base, ast.Attribute):
            names.append(base.attr)
    return names


def check(repo_root: Path) -> Result:
    path = repo_root / MODELS_REL
    if not path.exists():
        return failed(NAME, "models module not found", [str(MODELS_REL)])

    tree = ast.parse(path.read_text(encoding="utf-8"))
    violations = []
    counted = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        bases = _base_names(node)
        if node.name == BASE_CLASS:
            continue
        if "BaseModel" in bases:
            violations.append(
                f"{MODELS_REL}:{node.lineno}: {node.name} inherits BaseModel directly "
                f"— inherit {BASE_CLASS} so extra='forbid' applies"
            )
        elif BASE_CLASS in bases:
            counted += 1

    # A per-class model_config that re-opens the door is the other way to break
    # this, and it reads as a normal assignment rather than a suspicious one.
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "extra":
            value = node.value
            if isinstance(value, ast.Constant) and value.value != "forbid":
                violations.append(
                    f"{MODELS_REL}:{node.value.lineno}: extra={value.value!r} "
                    f"— only 'forbid' is allowed"
                )

    if violations:
        return failed(NAME, f"{len(violations)} unguarded model(s)", violations)
    return ok(NAME, f"{counted} model(s) inherit {BASE_CLASS}")
