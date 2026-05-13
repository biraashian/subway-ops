"""Reconciliation review page.

Operators land here once a week to compare each store's POS-recorded
``depositInBank`` against what actually showed up in the bank. When the
two match within tolerance there's nothing to do; when they don't, the
operator enters the actual amount and optionally a note. Saved entries
flow into ``ops_variance_entries`` (audit-logged with ``entered_by`` +
``entered_at``) and the recon mart's status column reflects the
operator's correction on the next refresh.

Filters: week range (default = last 4 closed Tuesdays), store filter
(respects visible_stores()), status multiselect. The data editor
disables every column except ``actual_bank_deposit`` and ``note`` so
the operator can only change the inputs they own.

Save flow:
1. Diff the editor's current state against the snapshot we cached on
   first render.
2. UPSERT any row whose ``actual_bank_deposit`` is non-null and changed
   (or whose ``note`` changed alongside an existing entry).
3. DELETE rows where the operator cleared a previously-entered amount
   — gated by a confirmation checkbox to avoid accidents.
4. Re-run the recon mart refresh for each touched week so the status
   chip flips immediately.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import streamlit as st

from subway_ops.dashboard.components import KEY_FILTER_STATUS
from subway_ops.dashboard.components.helpers import csv_download_button
from subway_ops.dashboard.components.sidebar import render_sidebar
from subway_ops.dashboard.data import (
    delete_variance_entries,
    recent_week_ends,
    recon_review_table,
    save_variance_entries,
)
from subway_ops.transform import mart_recon_weekly

DEFAULT_WEEK_RANGE = 4
STATUS_OPTIONS = ("unverified", "flagged", "escalated", "clean")
EDITOR_KEY = "recon_editor"
SNAPSHOT_KEY = "recon_snapshot"


def _filters(visible_stores: list[str]) -> tuple[list[date], list[str], list[str]]:
    cols = st.columns([2, 2, 2])
    with cols[0]:
        all_weeks = recent_week_ends(13)
        default_weeks = all_weeks[:DEFAULT_WEEK_RANGE]
        weeks = st.multiselect(
            "Weeks",
            options=all_weeks,
            default=default_weeks,
            format_func=lambda d: d.isoformat(),
            key="recon_filter_weeks",
        )
    with cols[1]:
        stores = st.multiselect(
            "Stores",
            options=visible_stores,
            default=visible_stores,
            key="recon_filter_stores",
        )
    with cols[2]:
        default_statuses = list(STATUS_OPTIONS)
        statuses = st.multiselect(
            "Status",
            options=STATUS_OPTIONS,
            default=st.session_state.get(KEY_FILTER_STATUS, default_statuses)
            if set(st.session_state.get(KEY_FILTER_STATUS, [])) <= set(STATUS_OPTIONS)
            else default_statuses,
            key="recon_filter_statuses",
        )
    return weeks, stores, statuses


def _diff_rows(
    original: pd.DataFrame, edited: pd.DataFrame
) -> tuple[list[dict[str, Any]], list[tuple[str, date]]]:
    """Return ``(upserts, deletes)`` from comparing the two frames.

    - ``upserts`` are rows whose new ``actual_bank_deposit`` is non-null
      AND differs from the snapshot's value (or whose note changed while
      a non-null amount is present).
    - ``deletes`` are rows whose ``actual_bank_deposit`` was non-null
      and is now null (operator cleared the entry).
    """
    upserts: list[dict[str, Any]] = []
    deletes: list[tuple[str, date]] = []

    merge_keys = ["restaurant_number", "week_end_date"]
    merged = edited.merge(
        original,
        on=merge_keys,
        suffixes=("_new", "_old"),
        how="left",
    )

    for _, row in merged.iterrows():
        new_actual = row.get("actual_bank_deposit_new")
        old_actual = row.get("actual_bank_deposit_old")
        new_note = row.get("note_new")
        old_note = row.get("note_old")

        new_actual_null = new_actual is None or pd.isna(new_actual)
        old_actual_null = old_actual is None or pd.isna(old_actual)

        if not old_actual_null and new_actual_null:
            deletes.append((str(row["restaurant_number"]), row["week_end_date"]))
            continue

        amount_changed = (
            not new_actual_null
            and (old_actual_null or float(new_actual) != float(old_actual))
        )
        note_changed = (str(new_note or "") != str(old_note or "")) and not new_actual_null

        if amount_changed or note_changed:
            upserts.append(
                {
                    "restaurant_number": str(row["restaurant_number"]),
                    "week_end_date": row["week_end_date"],
                    "actual_bank_deposit": float(new_actual)
                    if not new_actual_null else None,
                    "note": None if pd.isna(new_note) else new_note,
                }
            )

    return upserts, deletes


def _refresh_touched_weeks(weeks: set[date]) -> None:
    for w in sorted(weeks):
        mart_recon_weekly.refresh_for_week(w)


def _save(
    original: pd.DataFrame,
    edited: pd.DataFrame,
    *,
    entered_by: str,
    allow_delete: bool,
) -> tuple[int, int, set[date]]:
    upserts, deletes = _diff_rows(original, edited)
    if deletes and not allow_delete:
        st.warning(
            f"{len(deletes)} row(s) had their actual deposit cleared. "
            "Tick **Confirm deletions** below and save again to remove them."
        )
        deletes = []

    touched_weeks: set[date] = set()
    for r in upserts:
        touched_weeks.add(r["week_end_date"])
    for _, w in deletes:
        touched_weeks.add(w)

    n_upserted = save_variance_entries(upserts, entered_by=entered_by) if upserts else 0
    n_deleted = delete_variance_entries(deletes) if deletes else 0

    if touched_weeks:
        _refresh_touched_weeks(touched_weeks)
    return n_upserted, n_deleted, touched_weeks


def main() -> None:
    if not st.session_state.get("user_email"):
        st.warning("Please log in via the main page.")
        return

    render_sidebar()
    st.title("Reconciliation review")
    visible = list(st.session_state.get("assigned_stores", []))
    if not visible:
        st.error("No stores visible for your role.")
        return

    weeks, stores, statuses = _filters(visible)
    if not weeks or not stores or not statuses:
        st.info("Pick at least one week, store, and status to view rows.")
        return

    df = recon_review_table(tuple(weeks), tuple(stores), tuple(statuses))
    if df.empty:
        st.info("No reconciliation rows match the current filters.")
        return

    # Snapshot the row identifiers + the editable values so we can diff
    # later. Keep a per-week-range cache so a filter change starts a
    # fresh snapshot.
    snapshot_id = (tuple(weeks), tuple(stores), tuple(statuses))
    if st.session_state.get(SNAPSHOT_KEY + "_id") != snapshot_id:
        st.session_state[SNAPSHOT_KEY] = df[
            ["restaurant_number", "week_end_date", "actual_bank_deposit", "note"]
        ].copy()
        st.session_state[SNAPSHOT_KEY + "_id"] = snapshot_id

    edited = st.data_editor(
        df,
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        disabled=[
            "restaurant_number", "store_name", "week_end_date",
            "pos_deposit_in_bank", "variance", "status",
            "entered_by", "entered_at",
        ],
        column_config={
            "restaurant_number": st.column_config.TextColumn("Store #", width="small"),
            "store_name": st.column_config.TextColumn("Name", width="medium"),
            "week_end_date": st.column_config.DateColumn("Week ending", width="small"),
            "pos_deposit_in_bank": st.column_config.NumberColumn(
                "POS deposit", format="$%.2f", width="small"
            ),
            "actual_bank_deposit": st.column_config.NumberColumn(
                "Actual deposit", format="$%.2f", width="small",
                help="Operator-entered. Clear the cell to remove an entry.",
            ),
            "variance": st.column_config.NumberColumn(
                "Variance", format="$%.2f", width="small"
            ),
            "status": st.column_config.TextColumn("Status", width="small"),
            "note": st.column_config.TextColumn("Note", width="medium"),
            "entered_by": st.column_config.TextColumn("Last edited by", width="small"),
            "entered_at": st.column_config.DatetimeColumn(
                "Last edited at", width="small", format="YYYY-MM-DD HH:mm"
            ),
        },
        key=EDITOR_KEY,
    )
    csv_download_button(
        edited, filename="reconciliation.csv", key="recon_csv"
    )

    allow_delete = st.checkbox(
        "Confirm deletions (required to remove a previously-entered amount)",
        value=False,
        key="recon_allow_delete",
    )
    if st.button("Save changes", type="primary", key="recon_save_button"):
        n_up, n_del, touched = _save(
            st.session_state[SNAPSHOT_KEY],
            edited,
            entered_by=st.session_state["user_email"],
            allow_delete=allow_delete,
        )
        if n_up == 0 and n_del == 0:
            st.toast("No changes to save.")
        else:
            st.toast(
                f"Saved {n_up} change(s), removed {n_del} entry(ies), "
                f"refreshed {len(touched)} week(s).",
                icon="✅",
            )
            # Refreshing the snapshot ID forces a re-snapshot on next render.
            st.session_state.pop(SNAPSHOT_KEY + "_id", None)
            recon_review_table.clear()
            st.rerun()


main()
