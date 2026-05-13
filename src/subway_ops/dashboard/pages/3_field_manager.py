"""Field manager portfolio (placeholder for Task 4.4)."""

from __future__ import annotations

import streamlit as st


def main() -> None:
    if not st.session_state.get("user_email"):
        st.warning("Please log in via the main page.")
        return

    st.title("Field manager portfolio")
    st.write(
        f"Welcome **{st.session_state['display_name']}** "
        f"(role `{st.session_state['user_role']}`)."
    )
    st.write(
        f"Visible stores ({len(st.session_state['assigned_stores'])}): "
        + ", ".join(st.session_state["assigned_stores"])
    )
    st.info(
        "Task 4.4 will fill this page with FM-level KPIs vs the 20% / 25% "
        "portfolio targets."
    )


main()
