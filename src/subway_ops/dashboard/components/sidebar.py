"""Shared sidebar rendered on every page.

Without this, only the home page's ``app.py`` rendered the sidebar —
Streamlit's multipage model re-runs each page from scratch, so each
page has to render its own sidebar. We centralise it here so every
page shows the same identity / refresh-age / sign-out / feedback
block.
"""

from __future__ import annotations

import streamlit as st

from subway_ops.config import settings
from subway_ops.dashboard.auth import make_authenticator
from subway_ops.dashboard.components.helpers import humanize_relative
from subway_ops.dashboard.data import last_data_refresh


def render_sidebar() -> None:
    """Standard sidebar content. Skipped silently when no one is logged in."""
    if not st.session_state.get("user_email"):
        return

    st.sidebar.markdown(f"**{st.session_state['display_name']}**")
    st.sidebar.caption(
        f"role: `{st.session_state['user_role']}` · "
        f"{len(st.session_state.get('assigned_stores', []))} stores"
    )

    refresh_ts = last_data_refresh()
    if refresh_ts is not None:
        st.sidebar.caption(f"Last data refresh: {humanize_relative(refresh_ts)}")
    else:
        st.sidebar.caption("Last data refresh: (no mart data yet)")

    # Sign-out — rebuild authenticator from the cached ref_users so the
    # button works regardless of which page the user is on.
    authenticator = make_authenticator()
    authenticator.logout("Sign out", "sidebar")

    if settings.alert_email:
        st.sidebar.markdown("---")
        st.sidebar.caption(
            f"Found a bug or have feedback? Email **{settings.alert_email}**."
        )
