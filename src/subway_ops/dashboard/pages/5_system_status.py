"""System status — owner-only view onto ``ops_job_runs``.

Lists the most recent 50 job runs with color-coded status, lets the
operator filter by ``job_name`` and ``status``, and offers a one-click
"Re-run" link straight to the matching GitHub Actions
``workflow_dispatch`` URL.

The page auto-refreshes every 60 seconds via ``st.fragment(run_every=)``
so an operator who leaves the tab open during a deploy sees new rows
land without manual refresh.

Non-owner access is double-guarded: ``streamlit_app.py`` hides the page
from the nav for non-owners, and this module's ``main()`` also bounces
them with a warning. Either gate alone would be enough; both means a
URL-typed shortcut from a field manager still fails closed.
"""

from __future__ import annotations

import os
from urllib.parse import urlencode

import pandas as pd
import streamlit as st

from subway_ops.config import settings
from subway_ops.dashboard.auth import is_owner
from subway_ops.dashboard.components import (
    COLOR_IN_TARGET,
    COLOR_NEUTRAL,
    COLOR_OFF_TARGET,
    GREEN,
    RED,
    YELLOW,
)
from subway_ops.dashboard.components.helpers import csv_download_button
from subway_ops.dashboard.components.sidebar import render_sidebar
from subway_ops.dashboard.data import distinct_job_names, recent_job_runs

REFRESH_SECONDS = 60
ROWS_LIMIT = 50

# Map a ``job_name`` to its GitHub Actions workflow filename. Anything
# not in this map falls back to the workflows index page; the operator
# can pick from there.
_JOB_TO_WORKFLOW = {
    "daily_pull": "daily_pull.yml",
    "refresh_marts": "refresh_marts.yml",
    "send_weekly_digest": "weekly_digest.yml",
    "ingest_uos": "uos_pull.yml",
    "backfill": None,  # no scheduled workflow — backfill is hand-run
    "discovery": None,
    "audit_backfill": None,  # manual quarterly audit (Task 7.4)
    "send_failure_notification": None,
}

STATUS_COLOURS = {
    "success": GREEN,
    "running": YELLOW,
    "failed": RED,
}


def _gh_repo() -> str:
    """Best-effort guess at ``owner/repo`` for the Re-run links.

    Reads ``GITHUB_REPOSITORY`` first (set by GHA, also a handy override
    in ``.streamlit/secrets.toml``); falls back to a sensible default
    based on this project's working directory name.
    """
    via_env = os.environ.get("GITHUB_REPOSITORY", "")
    if via_env:
        return via_env
    try:
        secret = st.secrets.get("github_repository")
    except (FileNotFoundError, AttributeError):
        secret = None
    if secret:
        return str(secret)
    # Last-resort default — see README's CI-badge comment about the owner
    # placeholder.
    return "amitoj/subway-ops"


def _rerun_url(job_name: str) -> str | None:
    """Build a workflow_dispatch URL for a given job_name. ``None`` when
    we don't know which workflow owns the job."""
    wf = _JOB_TO_WORKFLOW.get(job_name)
    if wf is None:
        return None
    repo = _gh_repo()
    # The Actions "Run workflow" button lives at this URL; manual click
    # is sufficient per the playbook (no API-trigger needed).
    qs = urlencode({"query": f"is%3Asuccess+actor%3A{repo}"})
    return f"https://github.com/{repo}/actions/workflows/{wf}?{qs}"


def _format_duration(seconds: object) -> str:
    if seconds is None or pd.isna(seconds):
        return "—"
    try:
        s = float(seconds)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "—"
    if s < 60:
        return f"{s:.1f}s"
    if s < 3600:
        return f"{int(s // 60)}m {int(s % 60)}s"
    return f"{int(s // 3600)}h {int((s % 3600) // 60)}m"


def _status_chip(status: str) -> str:
    """Render the status as a coloured pill via inline HTML."""
    colour = STATUS_COLOURS.get(status, COLOR_NEUTRAL)
    fg = "#ffffff" if status in ("success", "failed") else "#1f2937"
    return (
        f'<span style="display:inline-block;padding:2px 8px;border-radius:10px;'
        f'background:{colour};color:{fg};font-weight:600;font-size:12px;">'
        f"{status}</span>"
    )


def _row_style(row: pd.Series) -> list[str]:
    """Pandas Styler row callback — tint failed rows red, running yellow."""
    bg = ""
    status = row.get("status")
    if status == "failed":
        bg = f"background-color: {COLOR_OFF_TARGET}33"  # 20%-ish opacity
    elif status == "running":
        bg = "background-color: #fef3c7"
    elif status == "success":
        bg = f"background-color: {COLOR_IN_TARGET}1a"
    return [bg] * len(row)


@st.fragment(run_every=REFRESH_SECONDS)
def _render_grid() -> None:
    """The auto-refreshing core of the page.

    Wrapped in ``st.fragment(run_every=...)`` so only this block reruns
    every minute — the sidebar + page header stay stable. The filter
    widgets live OUTSIDE the fragment so changing them doesn't bounce
    the user back to the default view on the next tick.
    """
    job_filter = tuple(st.session_state.get("sys_status_jobs", ()))
    status_filter = tuple(st.session_state.get("sys_status_statuses", ()))
    df = recent_job_runs(
        limit=ROWS_LIMIT,
        job_filter=job_filter,
        status_filter=status_filter,
    )
    if df.empty:
        st.info("No job runs match the current filters.")
        return

    df = df.copy()
    df["duration"] = df["duration_seconds"].apply(_format_duration)

    # Re-run links column — owner-only by construction; the page guard
    # blocks non-owners. ``LinkColumn`` opens in a new tab by default.
    df["rerun_url"] = df["job_name"].apply(_rerun_url)

    st.dataframe(
        df[
            [
                "job_name",
                "started_at",
                "duration",
                "status",
                "rows_written",
                "error_text_snippet",
                "rerun_url",
            ]
        ],
        use_container_width=True,
        hide_index=True,
        column_config={
            "job_name": st.column_config.TextColumn("Job", width="medium"),
            "started_at": st.column_config.DatetimeColumn(
                "Started", format="YYYY-MM-DD HH:mm:ss", width="medium"
            ),
            "duration": st.column_config.TextColumn("Duration", width="small"),
            "status": st.column_config.TextColumn("Status", width="small"),
            "rows_written": st.column_config.NumberColumn("Rows", width="small"),
            "error_text_snippet": st.column_config.TextColumn(
                "Error (first 200 chars)", width="large"
            ),
            "rerun_url": st.column_config.LinkColumn(
                "Re-run",
                width="small",
                display_text="Run in GH Actions ↗",
                help=(
                    "Opens the workflow's Run-workflow page. Pick "
                    "your branch and click 'Run workflow'."
                ),
            ),
        },
        key="sys_status_grid",
    )
    csv_download_button(
        df, filename="ops_job_runs.csv", key="sys_status_csv"
    )


def main() -> None:
    if not st.session_state.get("user_email"):
        st.warning("Please log in via the main page.")
        return
    if not is_owner(st.session_state.get("user_role")):
        st.error("This page is owner-only.")
        return

    render_sidebar()
    st.title("System status")
    st.caption(
        f"Last 50 ``ops_job_runs`` rows. Auto-refreshes every "
        f"{REFRESH_SECONDS}s. App env: `{settings.app_env}`."
    )

    job_options = distinct_job_names()
    cols = st.columns([2, 2, 6])
    with cols[0]:
        st.multiselect(
            "Job name",
            options=job_options,
            default=[],
            key="sys_status_jobs",
            placeholder="All jobs",
        )
    with cols[1]:
        st.multiselect(
            "Status",
            options=("running", "success", "failed"),
            default=[],
            key="sys_status_statuses",
            placeholder="All statuses",
        )

    _render_grid()


main()
