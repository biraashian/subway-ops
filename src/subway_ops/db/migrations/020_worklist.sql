-- 020_worklist.sql
-- ops_worklist_items — the system spine (codex/02-DATA-MODEL).
--
-- Every reconciliation exception, expiry nudge, ungraded task and pending
-- approval emits one row here. One table, one screen, and the answer to
-- "what needs a human today". A capability that detects a problem but emits
-- no worklist item has produced a report, not a resolution.
--
-- Created by SPEC-PPL-001 (AC-018, AC-020) because PPL is the first consumer;
-- SPEC-APP-001 builds the screen, not the table. The shape below is codex 02's
-- stated definition, so nothing here is invented: typed, role-assigned, with a
-- state, a due date, and a reference back to whatever produced it.
--
-- The coupling to a producing subsystem is carried entirely by (kind,
-- subject_ref). No producer-specific columns, ever — the moment this table
-- grows an `employee_id`, Phase B's reconcilers have to grow their own, and
-- the single pane stops being single.

CREATE TABLE IF NOT EXISTS ops_worklist_items (
    id             BIGSERIAL PRIMARY KEY,

    -- What kind of thing needs doing, e.g. 'employee_incomplete'. Free text by
    -- design: a CHECK constraint here would mean every new producer in Phases
    -- B-E needs a migration before it can raise its first item.
    kind           TEXT NOT NULL,

    -- Opaque pointer back to the subject, interpreted by the producer.
    -- TEXT rather than a typed FK because subjects span employees, deposits,
    -- chargebacks, certificates and store tasks.
    subject_ref    TEXT NOT NULL,

    -- The role ladder from codex/00-INSTITUTION. A CHECK rather than an FK
    -- because there is no ref_roles table and inventing one is outside this
    -- task's DELIVERABLES. Constrained rather than free text because a typo'd
    -- role assigns the item to nobody and it stays invisible forever.
    --
    -- **Duplicated with ref_users.role**, which T-0004 widens to the same six.
    -- Same precedent as migration 014's 5/50 thresholds: any change to the
    -- ladder needs a new migration touching both. Documented rather than
    -- abstracted — a shared roles table is a founder decision, not a
    -- build-time one.
    assigned_role  TEXT NOT NULL
                   CHECK (assigned_role IN ('owner', 'field_manager', 'office',
                                            'store_manager', 'shift_lead', 'crew')),

    summary        TEXT NOT NULL,
    due_date       DATE,

    state          TEXT NOT NULL DEFAULT 'open'
                   CHECK (state IN ('open', 'in_progress', 'resolved', 'dismissed')),

    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at    TIMESTAMPTZ,
    resolved_by    TEXT
);

-- AC-018's "SHALL NOT open a duplicate while one is already open" enforced in
-- the database rather than by a SELECT-then-INSERT in Python. Two concurrent
-- callers racing on the same subject would both see "no open item" and both
-- insert; a partial unique index makes the second one fail instead.
--
-- Partial on the two live states so that resolving an item frees the subject
-- to raise a fresh one later — a wage supplied and then removed must be able
-- to reopen.
CREATE UNIQUE INDEX IF NOT EXISTS uq_worklist_open_subject
    ON ops_worklist_items (kind, subject_ref)
    WHERE state IN ('open', 'in_progress');

-- The worklist screen's primary read: everything open for my role, oldest due
-- first. Partial for the same reason — resolved items are history, not work.
CREATE INDEX IF NOT EXISTS idx_worklist_role_due
    ON ops_worklist_items (assigned_role, due_date)
    WHERE state IN ('open', 'in_progress');
