"""Database connection helpers.

A single SQLAlchemy engine is constructed lazily from `settings.database_url`
and reused for the life of the process. Most of this project's SQL is hand-
written, so `execute_sql` (which binds parameters via SQLAlchemy `text()`)
is the workhorse — never string-format SQL.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine, Row, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from subway_ops.config import settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def _normalize_url(url: str) -> str:
    """Force SQLAlchemy to use psycopg v3, which is what we pin in pyproject.

    Supabase / Postgres connection strings come back as `postgresql://...`,
    which SQLAlchemy maps to psycopg2 by default. We don't install psycopg2 —
    only psycopg v3 — so rewrite the scheme to be explicit.
    """
    if url.startswith("postgresql+"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    return url


def get_engine() -> Engine:
    """Return the process-wide SQLAlchemy engine, creating it on first call."""
    global _engine, _session_factory  # noqa: PLW0603 — process-wide singleton
    if _engine is None:
        if not settings.database_url:
            raise RuntimeError(
                "DATABASE_URL is not set. Add it to .env or export it before "
                "creating a database engine."
            )
        _engine = create_engine(
            _normalize_url(settings.database_url),
            pool_pre_ping=True,
            future=True,
        )
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


@contextmanager
def get_session() -> Iterator[Session]:
    """Yield a SQLAlchemy Session, committing on success and rolling back on error."""
    get_engine()
    assert _session_factory is not None
    session = _session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def execute_sql(
    sql: str,
    params: dict[str, Any] | None = None,
) -> Sequence[Row[Any]]:
    """Execute raw SQL with bound parameters in a short-lived transaction.

    Always use named placeholders (`:name`) — never f-strings or `%` formatting.
    Rows are eagerly fetched before the connection closes. For statements that
    don't return rows (INSERT/UPDATE/DDL), the returned sequence is empty.
    """
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(text(sql), params or {})
        if result.returns_rows:
            return result.fetchall()
        return []


def reset_engine_for_tests() -> None:
    """Drop the cached engine — only for use in tests that swap DATABASE_URL."""
    global _engine, _session_factory  # noqa: PLW0603 — process-wide singleton
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
