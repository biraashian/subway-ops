"""SQL migration runner.

Discovers `*.sql` files in `src/subway_ops/db/migrations/` (sorted by filename),
computes a SHA-256 over each file's contents, and applies any whose filename
isn't already recorded in the `ops_migrations` table. Each application happens
in its own transaction.

If a filename is already in `ops_migrations` but the checksum on disk differs
from what was recorded at application time, the runner aborts. Migrations are
append-only: never edit an applied file — create a new one instead.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import structlog
from sqlalchemy import text

from subway_ops.db.connection import get_engine

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

# Bootstrap DDL: the migrations table itself. Applied before every run so we
# always have somewhere to record subsequent migrations.
_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS ops_migrations (
    filename     TEXT PRIMARY KEY,
    applied_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    checksum     TEXT NOT NULL
)
"""

log = structlog.get_logger(__name__)


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def discover_migrations(migrations_dir: Path = MIGRATIONS_DIR) -> list[Path]:
    """Return migration files in lexicographic (apply) order."""
    return sorted(p for p in migrations_dir.glob("*.sql"))


def apply_migrations(migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply pending migrations and return the list of newly-applied filenames.

    Raises:
        RuntimeError: if a previously-applied migration's checksum has changed.
    """
    engine = get_engine()

    with engine.begin() as conn:
        conn.execute(text(_BOOTSTRAP_SQL))

    with engine.connect() as conn:
        rows = conn.execute(text("SELECT filename, checksum FROM ops_migrations")).all()
    applied: dict[str, str] = {r[0]: r[1] for r in rows}

    files = discover_migrations(migrations_dir)
    newly_applied: list[str] = []

    for path in files:
        digest = _checksum(path)
        if path.name in applied:
            if applied[path.name] != digest:
                raise RuntimeError(
                    f"Migration {path.name} has changed since it was applied "
                    f"(recorded checksum {applied[path.name]}, on-disk {digest}). "
                    "Migrations are append-only — create a new file instead of "
                    "editing this one."
                )
            continue

        sql_text = path.read_text(encoding="utf-8")
        log.info("applying_migration", filename=path.name)
        with engine.begin() as conn:
            conn.execute(text(sql_text))
            conn.execute(
                text(
                    "INSERT INTO ops_migrations (filename, checksum) VALUES (:filename, :checksum)"
                ),
                {"filename": path.name, "checksum": digest},
            )
        newly_applied.append(path.name)

    return newly_applied
