"""Migrations are append-only.

CLAUDE.md has always said "never edit a migration after it has been applied;
new change = new migration file", and nothing enforced it. Editing an applied
migration is silently destructive: the file no longer describes the schema that
actually exists, so a fresh environment built from the migrations diverges from
production and nobody finds out until an ingest fails against the wrong column.

CHECKSUMS.txt is the manifest. Adding a migration is fine and expected — the
new file simply is not in the manifest yet, and ``--update`` folds it in.
Changing or deleting one that IS in the manifest is a failure.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from ._base import Result, failed, ok

NAME = "migrations append-only"
MANIFEST_NAME = "CHECKSUMS.txt"


def _migrations_dir(repo_root: Path) -> Path:
    return repo_root / "src" / "subway_ops" / "db" / "migrations"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_manifest(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    entries: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        digest, _, name = line.partition("  ")
        if digest and name:
            entries[name] = digest
    return entries


def write_manifest(repo_root: Path) -> Path:
    """Regenerate the manifest from the migrations on disk (``--update``)."""
    directory = _migrations_dir(repo_root)
    lines = [
        "# sha256 checksums of applied migrations. Append-only: a changed or",
        "# deleted entry fails the gate. Regenerate after ADDING a migration:",
        "#   uv run python -m tools.verify_invariants --update",
        "",
    ]
    lines += [f"{_digest(p)}  {p.name}" for p in sorted(directory.glob("*.sql"))]
    manifest = directory / MANIFEST_NAME
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest


def check(repo_root: Path) -> Result:
    directory = _migrations_dir(repo_root)
    if not directory.is_dir():
        return failed(NAME, "no migrations directory", [str(directory)])

    manifest_path = directory / MANIFEST_NAME
    recorded = _load_manifest(manifest_path)
    if not recorded:
        return failed(
            NAME,
            "no checksum manifest",
            [
                f"{manifest_path} is missing or empty. Seed it with: "
                f"uv run python -m tools.verify_invariants --update"
            ],
        )

    on_disk = {p.name: p for p in sorted(directory.glob("*.sql"))}
    violations: list[str] = []

    for name, digest in sorted(recorded.items()):
        path = on_disk.get(name)
        if path is None:
            violations.append(f"{name}: recorded in the manifest but missing from disk")
        elif _digest(path) != digest:
            violations.append(f"{name}: content changed since it was recorded")

    added = sorted(set(on_disk) - set(recorded))

    if violations:
        return failed(NAME, f"{len(violations)} altered migration(s)", violations)
    suffix = f", {len(added)} new" if added else ""
    return ok(NAME, f"{len(recorded)} migration(s) unchanged{suffix}")
