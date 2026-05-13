"""Sortable color-coded store grid. Placeholder for Phase 4.2."""

from __future__ import annotations

import pandas as pd
import streamlit as st


def store_grid(df: pd.DataFrame) -> None:
    """Plain-table placeholder. Task 4.2 replaces this with a color-coded
    sortable grid keyed on the mart's in_target flags."""
    if df.empty:
        st.info("No store rows yet for this period. Run the mart refresh first.")
        return
    st.dataframe(df, use_container_width=True, hide_index=True)
