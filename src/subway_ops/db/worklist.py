"""The worklist — the one screen that says what needs a human today.

``ops_worklist_items`` is the system spine (codex/02-DATA-MODEL). Every
reconciliation exception, expiry nudge, ungraded task and pending approval
lands here, and the worklist screen is the single place any of it surfaces.

This module is deliberately generic and lives in ``db/`` rather than under
``people/``: SPEC-PPL-001 is merely the first consumer, and every later phase
writes to the same table. All coupling to a producing subsystem is carried by
``(kind, subject_ref)`` — no producer ever gets its own column.

Anchors: SPEC-PPL-001 AC-018, AC-020.
"""

from __future__ import annotations

from datetime import date

import structlog

from subway_ops.db.connection import execute_sql

log = structlog.get_logger(__name__)

#: States in which an item still represents outstanding work. The partial
#: unique index in migration 020 is defined over exactly these, so this tuple
#: and that index must agree.
LIVE_STATES: tuple[str, ...] = ("open", "in_progress")


def open_item(
    *,
    kind: str,
    subject_ref: str,
    assigned_role: str,
    summary: str,
    due_date: date | None = None,
) -> int | None:
    """Open a worklist item for ``(kind, subject_ref)``, unless one is live.

    Returns the new item's id, or ``None`` when a live item already exists for
    that subject — AC-018's "SHALL NOT open a duplicate while one is already
    open for that person".

    The no-duplicate rule is enforced by the partial unique index in migration
    020, not by a read-then-write here. ``ON CONFLICT DO NOTHING`` against that
    index is atomic; a `SELECT` followed by an `INSERT` would let two concurrent
    callers both observe "nothing open" and both insert.

    A ``None`` return is an ordinary outcome, not a failure. Callers that sweep
    a whole population (see ``people.completeness``) will get ``None`` for every
    subject that already has an item, which is exactly the desired quiet.
    """
    rows = execute_sql(
        """
        INSERT INTO ops_worklist_items
            (kind, subject_ref, assigned_role, summary, due_date)
        VALUES (:kind, :subject_ref, :assigned_role, :summary, :due_date)
        ON CONFLICT (kind, subject_ref)
            WHERE state IN ('open', 'in_progress')
            DO NOTHING
        RETURNING id
        """,
        {
            "kind": kind,
            "subject_ref": subject_ref,
            "assigned_role": assigned_role,
            "summary": summary,
            "due_date": due_date,
        },
    )
    if not rows:
        return None

    item_id = int(rows[0][0])
    log.info(
        "worklist_item_opened",
        item_id=item_id,
        kind=kind,
        subject_ref=subject_ref,
        assigned_role=assigned_role,
    )
    return item_id


def resolve_item(kind: str, subject_ref: str, *, resolved_by: str | None = None) -> int:
    """Resolve every live item for ``(kind, subject_ref)``. Returns the count.

    AC-020's "WHEN the last missing field is supplied, the roster service SHALL
    resolve the open worklist item".

    Resolving a subject with nothing open returns ``0`` rather than raising —
    callers sweep populations and "already fine" is not an error. The partial
    unique index means the count is at most one in practice; the query is
    written as a set operation anyway so that a historical duplicate, if one
    ever predated the index, cannot leave a straggler behind.

    Resolved items are never deleted (codex/00-INSTITUTION: nothing is deleted).
    They stay as the record that the work was done and when.
    """
    rows = execute_sql(
        """
        UPDATE ops_worklist_items
           SET state       = 'resolved',
               resolved_at = now(),
               resolved_by = :resolved_by
         WHERE kind = :kind
           AND subject_ref = :subject_ref
           AND state IN ('open', 'in_progress')
        RETURNING id
        """,
        {"kind": kind, "subject_ref": subject_ref, "resolved_by": resolved_by},
    )
    count = len(rows)
    if count:
        log.info(
            "worklist_items_resolved",
            kind=kind,
            subject_ref=subject_ref,
            count=count,
            resolved_by=resolved_by,
        )
    return count
