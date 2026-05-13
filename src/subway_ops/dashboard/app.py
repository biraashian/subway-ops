"""Streamlit dashboard entry point.

Launches the login flow, populates ``st.session_state`` with the current
user's identity and visible-store list, and renders a sidebar with the
sign-out button + "last data refresh" timestamp.

Streamlit auto-discovers the ``pages/`` directory next to this file, so
the four placeholder pages show up in the sidebar nav. Each page reads
from ``st.session_state`` to decide what it can show.

Run locally:

    uv run streamlit run src/subway_ops/dashboard/app.py
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from subway_ops.dashboard.auth import (
    all_active_store_numbers,
    lookup_user,
    make_authenticator,
    visible_stores,
)
from subway_ops.dashboard.data import last_data_refresh


def _bootstrap_session(name: str | None, username: str | None) -> None:
    """Populate session_state with profile bits each page reads."""
    if not username:
        return
    user = lookup_user(username)
    if user is None:
        st.error(f"User {username} authenticated but not found in ref_users.")
        return
    visible = visible_stores(user, all_active_store_numbers())
    st.session_state["user_email"] = username
    st.session_state["display_name"] = name or user.display_name
    st.session_state["user_role"] = user.role
    st.session_state["assigned_stores"] = visible


def _sidebar(authenticator: Any) -> None:
    st.sidebar.markdown(f"**{st.session_state['display_name']}**")
    st.sidebar.caption(
        f"role: `{st.session_state['user_role']}` · "
        f"{len(st.session_state['assigned_stores'])} stores"
    )

    refresh_ts = last_data_refresh()
    if refresh_ts is not None:
        st.sidebar.caption(f"Last data refresh: {refresh_ts:%Y-%m-%d %H:%M %Z}")
    else:
        st.sidebar.caption("Last data refresh: (no mart data yet)")

    authenticator.logout("Sign out", "sidebar")


def main() -> None:
    st.set_page_config(
        page_title="Subway Operations",
        page_icon=":sandwich:",
        layout="wide",
    )

    authenticator = make_authenticator()
    authenticator.login(location="main")

    auth_status = st.session_state.get("authentication_status")
    if auth_status is False:
        st.error("Username or password is incorrect.")
        return
    if auth_status is None:
        st.info("Please log in to continue.")
        return

    _bootstrap_session(
        st.session_state.get("name"),
        st.session_state.get("username"),
    )
    _sidebar(authenticator)

    st.title("Subway Operations")
    st.write(
        f"Welcome, **{st.session_state['display_name']}** "
        f"(role `{st.session_state['user_role']}`)."
    )
    st.write(
        f"You can see **{len(st.session_state['assigned_stores'])}** stores: "
        + ", ".join(st.session_state["assigned_stores"])
    )
    st.write(
        "Use the sidebar to navigate. Each page will fill in over Tasks 4.2-4.6."
    )


if __name__ == "__main__":
    main()
