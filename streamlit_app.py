"""Streamlit Cloud / Fly.io entry point.

Streamlit Cloud (and our Dockerfile) launches ``streamlit run`` against
this file at the repo root. Streamlit's automatic ``pages/`` discovery
walks the directory next to the entry script — but our canonical page
files live under ``src/subway_ops/dashboard/pages/``. Rather than
duplicate them at the root we register the full nav explicitly with
``st.navigation()`` (Streamlit 1.36+) so the canonical sources stay in
the package and the deployment shim stays tiny.

Local dev still uses ``streamlit run src/subway_ops/dashboard/app.py``
— page auto-discovery works there because the pages live next to that
file. Both entrypoints render the same UI.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Make the in-tree package importable without a `pip install -e .` step.
sys.path.insert(0, str(HERE / "src"))

import streamlit as st  # noqa: E402  (sys.path tweak must come first)

DASHBOARD_DIR = HERE / "src" / "subway_ops" / "dashboard"
PAGES_DIR = DASHBOARD_DIR / "pages"

pages = [
    st.Page(str(DASHBOARD_DIR / "app.py"), title="Home", default=True),
    st.Page(str(PAGES_DIR / "1_owner_overview.py"), title="Owner overview"),
    st.Page(str(PAGES_DIR / "2_store_detail.py"), title="Store detail"),
    st.Page(str(PAGES_DIR / "3_field_manager.py"), title="Field manager"),
    st.Page(str(PAGES_DIR / "4_reconciliation.py"), title="Reconciliation"),
]

# Owner-only pages. Hidden from the nav for field managers and readonly
# users; the pages themselves also block on entry (defence in depth).
if st.session_state.get("user_role") == "owner":
    pages.append(
        st.Page(str(PAGES_DIR / "5_system_status.py"), title="System status"),
    )

st.navigation(pages).run()
