"""Streamlit auth wiring backed by ``ref_users``.

``ref_users`` already stores bcrypt-hashed passwords (seeded in Task 0.3),
so we tell ``streamlit-authenticator`` to skip its own hashing pass with
``auto_hash=False`` and just feed it the live rows.

Public surface:

    build_credentials(rows)
        Map ``ref_users`` rows into the credentials dict
        ``streamlit-authenticator`` expects. Pure — unit-tested without
        Streamlit running.

    load_credentials_from_db()
        Read live rows and call ``build_credentials``.

    make_authenticator()
        Compose the ``Authenticate`` object using the cookie key from
        Streamlit secrets / env. Cached per session in
        ``st.session_state`` to avoid the
        ``StreamlitDuplicateElementKey('init')`` crash that arises when
        the wrapper's internal ``CookieManager`` is re-registered on
        every script rerun.

    visible_stores(user_row)
        Return the set of store_numbers the given user can see. Owners
        and any user with no ``assigned_stores`` list see everything;
        others see only their cluster.
"""

from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass
from typing import Any

import streamlit as st
import streamlit_authenticator as stauth
from sqlalchemy import text

from subway_ops.db.connection import get_engine

COOKIE_NAME = "subway_ops_auth"
COOKIE_EXPIRY_DAYS = 30
# Auth roles that get to see every store regardless of assigned_stores.
ALL_STORE_ROLES = frozenset({"owner"})

# Key under which the cached ``Authenticate`` instance lives in
# ``st.session_state``. Constructing ``Authenticate`` twice in the
# same script run triggers ``StreamlitDuplicateElementKey`` because
# the library's internal ``CookieManager`` registers a widget with
# ``key='init'``. Cache the wrapper so every call from a given
# Streamlit session returns the same object.
_AUTHENTICATOR_STATE_KEY = "_authenticator"


@dataclass(frozen=True)
class UserRow:
    email: str
    display_name: str
    role: str
    password_hash: str
    assigned_stores: tuple[str, ...] | None


def _normalise_assigned(raw: Any) -> tuple[str, ...] | None:
    """``ref_users.assigned_stores`` is ``TEXT[]`` — psycopg returns a list."""
    if raw is None:
        return None
    if isinstance(raw, list | tuple):
        return tuple(str(s) for s in raw)
    return tuple(str(s).strip() for s in str(raw).split(",") if s.strip())


def build_credentials(rows: list[UserRow]) -> dict[str, Any]:
    """Shape ``ref_users`` rows into the dict ``stauth.Authenticate`` needs."""
    usernames: dict[str, Any] = {}
    for r in rows:
        usernames[r.email] = {
            "name": r.display_name,
            "password": r.password_hash,
            "email": r.email,
        }
    return {"usernames": usernames}


def load_user_rows() -> list[UserRow]:
    """Pull every active user from ``ref_users``."""
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT email, display_name, role, password_hash, assigned_stores "
                "FROM ref_users WHERE is_active = true "
                "ORDER BY email"
            )
        )
        return [
            UserRow(
                email=row[0],
                display_name=row[1],
                role=row[2],
                password_hash=row[3],
                assigned_stores=_normalise_assigned(row[4]),
            )
            for row in result.all()
        ]


def load_credentials_from_db() -> dict[str, Any]:
    return build_credentials(load_user_rows())


def _cookie_signing_key() -> str:
    """Find the cookie signing key in Streamlit secrets or the env.

    Streamlit Cloud users paste this into the secrets UI; local dev users
    drop it into ``.streamlit/secrets.toml``. Falls back to ``AUTH_COOKIE_KEY``
    so the same workflow YAML can pass it via GH secrets without touching
    a TOML file.
    """
    try:
        key = st.secrets["auth_cookie_key"]
        if key:
            return str(key)
    except (FileNotFoundError, KeyError, AttributeError):
        pass
    env = os.environ.get("AUTH_COOKIE_KEY", "")
    if env:
        return env
    # Last-resort dev default — never use this in prod. Loud at import time.
    return "dev-only-cookie-key-replace-in-secrets"


def make_authenticator(
    credentials: dict[str, Any] | None = None,
) -> stauth.Authenticate:
    """Return the per-session ``Authenticate`` wrapper.

    Cached in ``st.session_state`` so multiple ``make_authenticator()``
    calls in the same render (``app.py`` for the login form +
    ``sidebar.py`` for the sign-out button) hand back the same
    instance — otherwise the library re-registers its internal
    ``CookieManager`` widget under ``key='init'`` and Streamlit raises
    ``StreamlitDuplicateElementKey``.

    The cache lives in ``session_state`` (per-user), **never** in
    ``@st.cache_resource`` (process-wide). Sharing one ``Authenticate``
    across sessions would leak login cookies between users.

    Tradeoff: a password change applied mid-session doesn't propagate
    until the user signs out and signs back in. That's already the
    behaviour of any cookie-bound session and matches the rest of the
    app's auth model.

    Passing an explicit ``credentials`` dict bypasses the cache. The
    test suite uses that to exercise the construction path without
    re-using cached state.
    """
    if credentials is not None:
        # Caller is forcing a rebuild (tests, future "credentials
        # rotated" flow). Don't touch the cache so we never hand back
        # a stale instance whose internal credentials don't match.
        return _build_authenticator(credentials)

    cached = _get_cached_authenticator()
    if cached is not None:
        return cached
    auth = _build_authenticator(load_credentials_from_db())
    _store_cached_authenticator(auth)
    return auth


def _build_authenticator(creds: dict[str, Any]) -> stauth.Authenticate:
    return stauth.Authenticate(
        credentials=creds,
        cookie_name=COOKIE_NAME,
        cookie_key=_cookie_signing_key(),
        cookie_expiry_days=COOKIE_EXPIRY_DAYS,
        auto_hash=False,  # ref_users already stores bcrypt hashes
    )


def _get_cached_authenticator() -> stauth.Authenticate | None:
    """Look up the cached authenticator. ``None`` when running outside
    Streamlit (tests, scripts) or on a fresh session.

    ``st.session_state`` access can raise in bare mode (no script
    context) — suppress and treat it as a cache miss so unit tests
    and one-shot CLI imports don't crash.
    """
    with contextlib.suppress(Exception):
        return st.session_state.get(_AUTHENTICATOR_STATE_KEY)
    return None


def _store_cached_authenticator(auth: stauth.Authenticate) -> None:
    """Cache the authenticator in ``session_state``. No-op when
    Streamlit isn't running."""
    with contextlib.suppress(Exception):
        st.session_state[_AUTHENTICATOR_STATE_KEY] = auth


def clear_cached_authenticator() -> None:
    """Drop the cached authenticator — used by tests + a future
    password-rotation hook."""
    with contextlib.suppress(Exception):
        st.session_state.pop(_AUTHENTICATOR_STATE_KEY, None)


def visible_stores(user: UserRow, all_stores: list[str]) -> list[str]:
    """Return the list of store_numbers a given user can see, in order."""
    if user.role in ALL_STORE_ROLES or not user.assigned_stores:
        return list(all_stores)
    assigned = set(user.assigned_stores)
    return [s for s in all_stores if s in assigned]


def is_owner(user_role: str | None) -> bool:
    """True for any role that's allowed to see operational/system pages.

    Centralised so the sidebar nav, the page guard at the top of
    ``5_system_status.py``, and any future owner-only pages all agree.
    """
    return user_role in ALL_STORE_ROLES


def lookup_user(email: str) -> UserRow | None:
    for row in load_user_rows():
        if row.email == email:
            return row
    return None


def all_active_store_numbers() -> list[str]:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT store_number FROM ref_stores "
                "WHERE is_active = true ORDER BY store_number"
            )
        ).all()
    return [str(r[0]) for r in rows]
