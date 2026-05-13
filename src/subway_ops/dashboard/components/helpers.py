"""Small page-agnostic UI helpers.

Lives next to the colour palette so a page only ever imports from
``subway_ops.dashboard.components``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import streamlit as st


def humanize_relative(ts: datetime | pd.Timestamp, now: datetime | None = None) -> str:
    """Render ``ts`` as a coarse relative phrase: "12 minutes ago", "3 hours
    ago", "yesterday", "5 days ago".

    Both ``ts`` and ``now`` may be timezone-aware or naive; if either
    is naive we assume it's already in UTC. Future timestamps render as
    "just now" (no negative-time language).
    """
    now = now or datetime.now(UTC)
    moment = ts.to_pydatetime() if isinstance(ts, pd.Timestamp) else ts
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    delta = now - moment
    if delta <= timedelta(seconds=30):
        return "just now"
    if delta < timedelta(minutes=1):
        return f"{int(delta.total_seconds())} seconds ago"
    if delta < timedelta(hours=1):
        mins = int(delta.total_seconds() // 60)
        return f"{mins} minute{'s' if mins != 1 else ''} ago"
    if delta < timedelta(days=1):
        hrs = int(delta.total_seconds() // 3600)
        return f"{hrs} hour{'s' if hrs != 1 else ''} ago"
    days = delta.days
    if days == 1:
        return "yesterday"
    return f"{days} days ago"


def csv_download_button(
    df: pd.DataFrame,
    *,
    filename: str,
    label: str = "Download CSV",
    key: str | None = None,
) -> None:
    """Render an ``st.download_button`` that hands the operator a CSV.

    Silently no-ops on empty frames (nothing to download). Pages that
    show multiple tables must pass distinct ``key`` values so Streamlit
    doesn't collapse them into one widget.
    """
    if df is None or df.empty:
        return
    st.download_button(
        label=label,
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=filename,
        mime="text/csv",
        key=key,
    )
