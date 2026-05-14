"""Targeted coverage tests for branches that fell below 80%.

These are deliberately narrow: each one exercises a specific branch in
``subway_ops.db.connection`` or ``subway_ops.dashboard.auth`` that the
existing tests miss because they need either a live DB (``get_engine``
no-URL raise) or a Streamlit runtime (``_cookie_signing_key`` fallbacks).
Mocking lets us cover the pure logic without spinning either up.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import streamlit_authenticator as stauth

from subway_ops.config import Settings
from subway_ops.dashboard import auth as auth_mod
from subway_ops.dashboard.auth import (
    UserRow,
    _cookie_signing_key,
    lookup_user,
    make_authenticator,
)
from subway_ops.db import connection as connection_mod
from subway_ops.db.connection import _normalize_url, get_engine, reset_engine_for_tests

# ---------------------------------------------------------------------------
# db.connection URL normalisation + engine singleton
# ---------------------------------------------------------------------------


def test_normalize_url_passthrough_when_already_explicit() -> None:
    """``postgresql+psycopg://`` URLs come back untouched."""
    url = "postgresql+psycopg://user:pw@host:5432/db"
    assert _normalize_url(url) == url


def test_normalize_url_rewrites_bare_postgres_scheme() -> None:
    """``postgres://`` (Heroku-style) → psycopg v3 explicit."""
    rewritten = _normalize_url("postgres://user:pw@host:5432/db")
    assert rewritten == "postgresql+psycopg://user:pw@host:5432/db"


def test_normalize_url_rewrites_standard_postgresql_scheme() -> None:
    rewritten = _normalize_url("postgresql://user:pw@host:5432/db")
    assert rewritten == "postgresql+psycopg://user:pw@host:5432/db"


def test_normalize_url_leaves_non_postgres_url_alone() -> None:
    """Test that the unknown-scheme branch returns the URL verbatim
    instead of mangling it (sqlite, in-memory etc. should round-trip)."""
    url = "sqlite:///./test.db"
    assert _normalize_url(url) == url


def test_get_engine_raises_when_database_url_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Loud failure beats silent confusion when DATABASE_URL is unset."""
    monkeypatch.setattr(connection_mod, "settings", Settings(_env_file=None))  # type: ignore[call-arg]
    reset_engine_for_tests()
    try:
        with pytest.raises(RuntimeError, match="DATABASE_URL is not set"):
            get_engine()
    finally:
        reset_engine_for_tests()


# ---------------------------------------------------------------------------
# dashboard.auth cookie signing key fallback chain
# ---------------------------------------------------------------------------


def test_cookie_signing_key_prefers_streamlit_secrets() -> None:
    fake_secrets = {"auth_cookie_key": "secret-from-toml"}
    with patch.object(auth_mod.st, "secrets", fake_secrets):
        assert _cookie_signing_key() == "secret-from-toml"


def test_cookie_signing_key_falls_back_to_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When secrets.toml is missing entirely, the env var wins."""
    # Force st.secrets to raise FileNotFoundError on access.
    class _NoSecrets:
        def __getitem__(self, key: str) -> Any:
            raise FileNotFoundError("no secrets.toml")

    with patch.object(auth_mod.st, "secrets", _NoSecrets()):
        monkeypatch.setenv("AUTH_COOKIE_KEY", "secret-from-env")
        assert _cookie_signing_key() == "secret-from-env"


def test_cookie_signing_key_falls_back_to_dev_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When neither source provides a key, return the dev placeholder."""
    class _NoSecrets:
        def __getitem__(self, key: str) -> Any:
            raise KeyError(key)

    with patch.object(auth_mod.st, "secrets", _NoSecrets()):
        monkeypatch.delenv("AUTH_COOKIE_KEY", raising=False)
        key = _cookie_signing_key()
        assert "dev-only" in key


def test_cookie_signing_key_treats_empty_secret_as_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty string in secrets must not be picked up as a real key."""
    with patch.object(auth_mod.st, "secrets", {"auth_cookie_key": ""}):
        monkeypatch.setenv("AUTH_COOKIE_KEY", "secret-from-env")
        assert _cookie_signing_key() == "secret-from-env"


# ---------------------------------------------------------------------------
# make_authenticator / lookup_user — mock the DB hop, exercise the wiring
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_authenticator_cache() -> None:
    """``make_authenticator`` caches the Authenticate wrapper in
    ``st.session_state``. Tests that exercise the construction path
    need a clean cache or they'd hand back a stale instance from a
    prior test and skip the DB-load assertion."""
    auth_mod.clear_cached_authenticator()
    yield
    auth_mod.clear_cached_authenticator()


def _user_row(email: str = "owner@example.com") -> UserRow:
    return UserRow(
        email=email,
        display_name="Owner",
        role="owner",
        password_hash="$2b$12$abcdefghijklmnopqrstuv",
        assigned_stores=None,
    )


def test_make_authenticator_accepts_explicit_credentials() -> None:
    """The credentials= kwarg short-circuits the DB load. We don't poke
    at streamlit-authenticator internals (they're private and have moved
    between versions); just verify the object is built and is an
    Authenticate instance."""
    creds = {"usernames": {"x@x.com": {"name": "x", "password": "$2b$abc"}}}
    with patch.object(auth_mod, "_cookie_signing_key", return_value="k"):
        auth = make_authenticator(credentials=creds)
    assert isinstance(auth, stauth.Authenticate)


def test_make_authenticator_loads_credentials_from_db_when_missing() -> None:
    """No credentials arg → load_credentials_from_db() is invoked."""
    fake_creds = {"usernames": {"a@b.com": {"name": "a", "password": "h"}}}
    with (
        patch.object(auth_mod, "load_credentials_from_db", return_value=fake_creds) as load,
        patch.object(auth_mod, "_cookie_signing_key", return_value="k"),
    ):
        make_authenticator()
    load.assert_called_once()


def test_make_authenticator_caches_within_session() -> None:
    """Regression for StreamlitDuplicateElementKey('init').

    Two ``make_authenticator()`` calls (e.g. the login form on app.py
    plus the sign-out button on the sidebar, both invoked during one
    page render) must hand back the **same** ``Authenticate`` object
    so the library's internal CookieManager is registered as a
    Streamlit widget exactly once.
    """
    fake_creds = {"usernames": {"a@b.com": {"name": "a", "password": "h"}}}
    with (
        patch.object(auth_mod, "load_credentials_from_db", return_value=fake_creds) as load,
        patch.object(auth_mod, "_cookie_signing_key", return_value="k"),
    ):
        first = make_authenticator()
        second = make_authenticator()
    assert first is second
    # And the DB-load helper was only consulted on the cache miss.
    load.assert_called_once()


def test_make_authenticator_explicit_credentials_skip_the_cache() -> None:
    """Passing ``credentials=`` is the test/forced-rebuild path. It
    must always build a fresh wrapper so the caller never sees a
    cached instance whose internal credentials don't match."""
    cached_creds = {"usernames": {"a@b.com": {"name": "a", "password": "h"}}}
    explicit_creds = {"usernames": {"b@b.com": {"name": "b", "password": "h"}}}
    with (
        patch.object(auth_mod, "load_credentials_from_db", return_value=cached_creds),
        patch.object(auth_mod, "_cookie_signing_key", return_value="k"),
    ):
        cached = make_authenticator()
        rebuilt = make_authenticator(credentials=explicit_creds)
    assert cached is not rebuilt
    # And subsequent no-arg calls still return the cached instance —
    # the explicit-credentials call did not poison the cache.
    with (
        patch.object(auth_mod, "load_credentials_from_db", return_value=cached_creds),
        patch.object(auth_mod, "_cookie_signing_key", return_value="k"),
    ):
        again = make_authenticator()
    assert again is cached


def test_clear_cached_authenticator_forces_rebuild() -> None:
    fake_creds = {"usernames": {"a@b.com": {"name": "a", "password": "h"}}}
    with (
        patch.object(auth_mod, "load_credentials_from_db", return_value=fake_creds),
        patch.object(auth_mod, "_cookie_signing_key", return_value="k"),
    ):
        first = make_authenticator()
        auth_mod.clear_cached_authenticator()
        second = make_authenticator()
    assert first is not second


def test_lookup_user_returns_matching_row() -> None:
    """``lookup_user`` walks ``load_user_rows()`` and returns the match."""
    rows = [
        _user_row("a@b.com"),
        _user_row("c@d.com"),
    ]
    with patch.object(auth_mod, "load_user_rows", return_value=rows):
        result = lookup_user("c@d.com")
    assert result is not None
    assert result.email == "c@d.com"


def test_lookup_user_returns_none_when_no_match() -> None:
    with patch.object(auth_mod, "load_user_rows", return_value=[_user_row()]):
        assert lookup_user("missing@example.com") is None


# ---------------------------------------------------------------------------
# all_active_store_numbers — DB query is wrapped in a small helper we can
# exercise via a mock engine. Confirms the SQL path is wired up.
# ---------------------------------------------------------------------------


def test_all_active_store_numbers_unwraps_engine_result() -> None:
    """The helper returns the first column as a list of strings."""
    fake_rows = [("4092",), ("17967",), ("26529",)]
    fake_conn = MagicMock()
    fake_conn.execute.return_value.all.return_value = fake_rows
    ctx = MagicMock()
    ctx.__enter__.return_value = fake_conn
    ctx.__exit__.return_value = False
    fake_engine = MagicMock()
    fake_engine.connect.return_value = ctx

    with patch.object(auth_mod, "get_engine", return_value=fake_engine):
        out = auth_mod.all_active_store_numbers()

    assert out == ["4092", "17967", "26529"]
    # And we called connect() exactly once.
    fake_engine.connect.assert_called_once()


def test_load_user_rows_normalises_each_column() -> None:
    """End-to-end shape: the SQL result is mapped into UserRow tuples."""
    fake_rows = [
        ("alice@x.com", "Alice", "owner", "$2b$abc", None),
        ("bob@x.com", "Bob", "field_manager", "$2b$def", ["4092", "17967"]),
    ]
    fake_conn = MagicMock()
    fake_conn.execute.return_value.all.return_value = fake_rows
    ctx = MagicMock()
    ctx.__enter__.return_value = fake_conn
    ctx.__exit__.return_value = False
    fake_engine = MagicMock()
    fake_engine.connect.return_value = ctx

    with patch.object(auth_mod, "get_engine", return_value=fake_engine):
        rows = auth_mod.load_user_rows()

    assert len(rows) == 2
    assert rows[0].email == "alice@x.com"
    assert rows[0].assigned_stores is None
    assert rows[1].assigned_stores == ("4092", "17967")
    assert rows[1].role == "field_manager"
