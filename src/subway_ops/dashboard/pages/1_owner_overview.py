"""Owner overview page (placeholder for Task 4.2)."""

from __future__ import annotations

import streamlit as st


def main() -> None:
    if not st.session_state.get("user_email"):
        st.warning("Please log in via the main page.")
        return

    st.title("Owner overview")
    st.write(
        f"Welcome **{st.session_state['display_name']}** "
        f"(role `{st.session_state['user_role']}`)."
    )
    st.write(
        f"Visible stores ({len(st.session_state['assigned_stores'])}): "
        + ", ".join(st.session_state["assigned_stores"])
    )
    st.info(
        "Task 4.2 fills this page with a 15-store grid plus a 13-week "
        "trend chart."
    )


main()
