"""Reconciliation review (placeholder for Task 5.2)."""

from __future__ import annotations

import streamlit as st

from subway_ops.dashboard.components.sidebar import render_sidebar


def main() -> None:
    if not st.session_state.get("user_email"):
        st.warning("Please log in via the main page.")
        return

    render_sidebar()
    st.title("Reconciliation review")
    st.write(
        f"Welcome **{st.session_state['display_name']}** "
        f"(role `{st.session_state['user_role']}`)."
    )
    st.write(
        f"Visible stores ({len(st.session_state['assigned_stores'])}): "
        + ", ".join(st.session_state["assigned_stores"])
    )
    st.info(
        "Task 5.2 will land here: weekly recon status per store, plus an "
        "audit-logged form for entering actual bank deposits."
    )


main()
