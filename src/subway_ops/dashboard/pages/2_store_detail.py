"""Store detail drill-down (placeholder for Task 4.3)."""

from __future__ import annotations

import streamlit as st


def main() -> None:
    if not st.session_state.get("user_email"):
        st.warning("Please log in via the main page.")
        return

    st.title("Store detail")
    st.write(
        f"Welcome **{st.session_state['display_name']}** "
        f"(role `{st.session_state['user_role']}`)."
    )
    st.write(
        f"Visible stores ({len(st.session_state['assigned_stores'])}): "
        + ", ".join(st.session_state["assigned_stores"])
    )
    st.info(
        "Task 4.3 will fill this page with four tabs: daily trend, "
        "weekly history, WISR inventory detail, cash drops."
    )


main()
