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

#: States in which an existing item suppresses a new one for the same subject.
#: The partial unique index ``uq_worklist_open_subject`` in migration 020 is
#: defined over exactly these, so this tuple and that index must agree — and so
#: must the ``WHERE`` clause on ``open_item``'s ``ON CONFLICT``, which Postgres
#: uses to infer which partial index it is talking about.
#:
#: ``dismissed`` is here per D-029: producers are sweeps, so without it a
#: dismissal is undone by the next cycle.
SUPPRESSING_STATES: tuple[str, ...] = ("open", "in_progress", "dismissed")

#: States that ``resolve_item`` closes out. Deliberately NOT the same tuple.
#:
#: D-029 makes dismissal durable and "undone only by an explicit reopen", so
#: resolving a subject must not quietly clear a dismissed item — that would
#: undo the dismissal by a side door, and the reopen path belongs to
#: SPEC-APP-001. The two tuples answer different questions: one is "may a new
#: item be raised?", the other is "what does resolution close?"
LIVE_STATES: tuple[str, ...] = ("open", "in_progress")


def open_item(
    *,
    kind: str,
    subject_ref: str,
    assigned_role: str,
    summary: str,
    due_date: date | None = None,
) -> int | None:
    """Open a worklist item for ``(kind, subject_ref)``, unless one suppresses.

    Returns the new item's id, or ``None`` when a suppressing item already
    exists for that subject — AC-018's "SHALL NOT open a duplicate while an item
    for that person is in a suppressing state". Per D-029 those states are
    ``open``, ``in_progress`` and ``dismissed``; a ``resolved`` item suppresses
    nothing, so a subject that goes bad again raises a fresh item.

    The no-duplicate rule is enforced by the partial unique index in migration
    020, not by a read-then-write here. ``ON CONFLICT DO NOTHING`` against that
    index is atomic; a `SELECT` followed by an `INSERT` would let two concurrent
    callers both observe "nothing open" and both insert.

    A ``None`` return is an ordinary outcome, not a failure. Callers that sweep
    a whole population (see ``people.completeness``) will get ``None`` for every
    subject that already has an item, which is exactly the desired quiet — and
    for a dismissed subject that quiet is the point, not a side effect.
    """
    rows = execute_sql(
        """
        INSERT INTO ops_worklist_items
            (kind, subject_ref, assigned_role, summary, due_date)
        VALUES (:kind, :subject_ref, :assigned_role, :summary, :due_date)
        ON CONFLICT (kind, subject_ref)
            WHERE state IN ('open', 'in_progress', 'dismissed')
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


def resolve_item(kind: str, subject_ref: str) -> int:
    """Resolve every live item for ``(kind, subject_ref)``. Returns the count.

    AC-020's "WHEN the last missing field is supplied, the roster service SHALL
    resolve the open worklist item".

    Resolving a subject with nothing open returns ``0`` rather than raising —
    callers sweep populations and "already fine" is not an error. The partial
    unique index means the count is at most one in practice; the query is
    written as a set operation anyway so that a historical duplicate, if one
    ever predated the index, cannot leave a straggler behind.

    **A dismissed item is not resolved here**, which is why this reads
    ``LIVE_STATES`` and not ``SUPPRESSING_STATES``. D-029 makes dismissal
    durable and undone only by an explicit reopen; clearing it as a side effect
    of the underlying problem being fixed would be that reopen happening by
    accident, without anyone deciding it. The consequence is deliberate and
    recorded: a dismissed subject stays quiet even after the problem is fixed
    and later recurs, until a human reopens it.

    There is no actor parameter (D-030). ``resolved_at`` records when; nothing
    in this system can honestly say who until SPEC-APP-001 builds the screen
    where a human clicks the button.

    Resolved items are never deleted (codex/00-INSTITUTION: nothing is deleted).
    They stay as the record that the work was done and when.
    """
    rows = execute_sql(
        """
        UPDATE ops_worklist_items
           SET state       = 'resolved',
               resolved_at = now()
         WHERE kind = :kind
           AND subject_ref = :subject_ref
           AND state IN ('open', 'in_progress')
        RETURNING id
        """,
        {"kind": kind, "subject_ref": subject_ref},
    )
    count = len(rows)
    if count:
        log.info(
            "worklist_items_resolved",
            kind=kind,
            subject_ref=subject_ref,
            count=count,
        )
    return count
