-- 021_people.sql
-- The people schema: persons, assignments, effective-dated wages, identity log.
--
-- SPEC-PPL-001 §5 is the shape authority for every table below; codex/06-PEOPLE
-- is the design authority behind it. Anchors: AC-011, AC-014, AC-022, AC-031.
--
-- The central inherited rule (codex 06): a person is ONE record with MANY store
-- assignments. Everything here follows from that. The system currently knows
-- stores and clerk PINs; after this migration it can know people.
--
-- Nothing here backfills. T-0006 runs the first derivation.

-- ---------------------------------------------------------------------------
-- ref_employees — the person
-- ---------------------------------------------------------------------------
-- Deliberately has NO natural-key UNIQUE constraint, and that absence is a
-- decision rather than an omission (PLAN §6, B-0014 → B). Measured on real
-- data: 250 distinct clerk_ids across 399 (clerk_id, store) pairs, and 56
-- clerk_ids carry more than one name — PIN 8 appears under 5 different names at
-- 5 stores. There is no field, and no combination of fields, that identifies a
-- human here. Any UNIQUE we invented would either reject legitimate rows or
-- silently fuse two people. Linking is a rule in code (AC-005), repaired by an
-- explicit office merge, and the log below is its audit trail.
CREATE TABLE IF NOT EXISTS ref_employees (
    employee_id             BIGSERIAL PRIMARY KEY,

    display_name            TEXT NOT NULL,

    -- AC-028: an office-typed name survives every later derivation run. The
    -- flag is what makes that enforceable — without it, the derivation cannot
    -- tell a name it generated from a name a human corrected, and would
    -- overwrite the correction on the next nightly pass.
    display_name_is_manual  BOOLEAN NOT NULL DEFAULT false,

    -- AC-031. Both nullable, both unique: identifiers, not credentials. B-0015
    -- chose Discord OAuth with phone as the fallback for anyone not on Discord,
    -- so a person may have either, both, or neither while the rollout runs.
    -- NG-004 fences the authentication FLOW out of this spec entirely — storing
    -- these is in scope, using them to log anyone in is not.
    phone                   TEXT UNIQUE,
    discord_user_id         TEXT UNIQUE,

    hire_date               DATE,

    -- AC-022. Termination sets these two and deletes nothing (INV-009): the
    -- row stays, the hours stay in every mart (INV-010), and AC-024 reactivates
    -- THIS row if the person clocks in again rather than creating a second one.
    termination_date        DATE,
    is_active               BOOLEAN NOT NULL DEFAULT true,

    -- AC-007: a merged person's row is retained and marked, never deleted. The
    -- self-reference is what "marked merged" means physically — follow it to
    -- find who absorbed them.
    merged_into             BIGINT REFERENCES ref_employees(employee_id),

    -- The bridge to the admin surface, nullable because the overwhelming
    -- majority of the 250 people here will never have a dashboard login.
    -- codex 06 (line 95) is explicit that this is a link, "not a merge".
    user_email              TEXT REFERENCES ref_users(email),

    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- ref_employee_assignments — one person's presence at one store
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ref_employee_assignments (
    assignment_id    BIGSERIAL PRIMARY KEY,

    employee_id      BIGINT NOT NULL REFERENCES ref_employees(employee_id),
    store_number     TEXT NOT NULL REFERENCES ref_stores(store_number),
    clerk_id         TEXT NOT NULL,

    -- observed_name is what the POS actually sent, stored unchanged (AC-026);
    -- normalized_name is it lowercased, trimmed and whitespace-collapsed, and
    -- is half of the linking key in AC-005. Both nullable: SPEC §5 declares
    -- neither NOT NULL, and a stub can exist before a name is seen.
    observed_name    TEXT,
    normalized_name  TEXT,

    -- codex 06 "Roles": role is a property of the ASSIGNMENT, not of the
    -- person, because someone can be a shift lead at one store and crew at
    -- another. AC-029 resolves the highest across active assignments when a
    -- single role is needed; AC-030 uses the per-assignment role for
    -- store-scoped permissions.
    --
    -- No CHECK constraint here, deliberately. SPEC §5 specifies exactly
    -- `role: TEXT NOT NULL DEFAULT 'crew'` and no more. T-0003's audit was RED
    -- partly for adding structure past the stated shape (B-0026 → D-030), and
    -- the lesson generalises: the licensed shape is the shape. If this column
    -- should be constrained to codex 06's six, that is a spec amendment and a
    -- later migration, not a decision to make here.
    role             TEXT NOT NULL DEFAULT 'crew',

    is_active        BOOLEAN NOT NULL DEFAULT true,

    -- The join key back to stg_timeclock, which keys on exactly this pair.
    -- INV-003 (an assignment references exactly one person) rests on it, and it
    -- is what makes the derivation idempotent (INV-002): re-running over the
    -- same timeclock rows finds the assignment already present.
    UNIQUE (store_number, clerk_id)
);

-- AC-005's lookup: given a new (clerk_id, normalized_name), is there already an
-- assignment matching on BOTH? Every derivation run asks this once per pair.
CREATE INDEX IF NOT EXISTS idx_assignment_clerk_normalized
    ON ref_employee_assignments (clerk_id, normalized_name);

-- ---------------------------------------------------------------------------
-- ref_employee_wages — effective-dated, never updated in place
-- ---------------------------------------------------------------------------
-- Wages exist in NO upstream system (D-020): FreshConnect has none, and this is
-- the missing input that has left mart_store_weekly.labor_cost_pct NULL since
-- it was written. Every row here is hand-keyed by a human, which is exactly why
-- set_by and set_at are NOT NULL.
CREATE TABLE IF NOT EXISTS ref_employee_wages (
    employee_id     BIGINT NOT NULL REFERENCES ref_employees(employee_id),
    effective_date  DATE NOT NULL,

    -- codex 02: money is NUMERIC(12,4), never float. AC-014's rejection of zero
    -- and negative lives in the CHECK rather than in Python because INV-007
    -- turns on it — a missing wage must read as NULL/absent, never as a rate of
    -- zero, or an incomplete person's hours cost nothing and the labor-dollar
    -- total is quietly wrong instead of loudly partial.
    hourly_rate     NUMERIC(12,4) NOT NULL CHECK (hourly_rate > 0),

    set_by          TEXT NOT NULL,
    set_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- AC-011: recording a wage INSERTs; it never modifies an existing row. This
    -- PK is what makes "never updated in place" a property of the database
    -- rather than a habit of the caller — a second rate for the same person on
    -- the same date is refused outright, so a raise cannot rewrite last month.
    PRIMARY KEY (employee_id, effective_date)
);

-- ---------------------------------------------------------------------------
-- ops_employee_identity_log — append-only audit of merge and split
-- ---------------------------------------------------------------------------
-- AC-007 and AC-008 both append exactly one row here. B-0014's accepted cost is
-- that ~149 pairs need manual merging, so this table will carry real volume of
-- human decisions, and it is the only place recording who fused two people's
-- histories and why.
CREATE TABLE IF NOT EXISTS ops_employee_identity_log (
    -- A surrogate key, following ops_worklist_items (migration 020). SPEC §5
    -- names the columns but no key; a log table with no primary key cannot
    -- address its own rows, and every ops_* table in this schema has one.
    log_id            BIGSERIAL PRIMARY KEY,

    action            TEXT NOT NULL CHECK (action IN ('merge', 'split')),

    -- These three are nullable because the two actions populate different
    -- subsets: a merge names from and to, a split names an assignment and the
    -- person it moved to. SPEC §5 declares no NOT NULL on any of them and this
    -- migration does not add one — a CHECK enforcing "merge needs from, split
    -- needs assignment_id" would be exactly the unlicensed structure that
    -- B-0026 found in T-0003. If the shape should be tighter, that is a spec
    -- amendment.
    from_employee_id  BIGINT REFERENCES ref_employees(employee_id),
    to_employee_id    BIGINT REFERENCES ref_employees(employee_id),
    assignment_id     BIGINT REFERENCES ref_employee_assignments(assignment_id),

    -- AC-007 records "actor, time and reason", so all three are required.
    actor             TEXT NOT NULL,
    at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    reason            TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- ref_users.role — widen the CHECK, in a NEW migration
-- ---------------------------------------------------------------------------
-- SPEC §5: the CHECK expands to add `store_manager`, `office` and `crew`.
-- Migration 001 created it as ('owner', 'field_manager', 'readonly'); 001 is
-- merged and therefore frozen absolutely (codex 02, D-032), so the constraint
-- is dropped and recreated HERE rather than edited there.
--
-- **On the two role vocabularies, because a merged comment gets this wrong.**
-- Migration 020 says of ops_worklist_items.assigned_role that it is
-- "duplicated with ref_users.role, which T-0004 widens to the same six". That
-- is incorrect, and 020 cannot be edited to fix it, so the correction lives
-- here. The two sets are six each and they are NOT the same six:
--
--   ops_worklist_items.assigned_role  owner · field_manager · office ·
--                                     store_manager · shift_lead · crew
--   ref_users.role (after this)       owner · field_manager · office ·
--                                     store_manager · crew · readonly
--
-- They differ by `shift_lead` and `readonly`, and the difference is real rather
-- than an oversight. The first is codex 06's JOB ladder — what someone does on
-- a shift, and who a worklist item can be assigned to. The second is an ACCESS
-- vocabulary for the admin surface: `readonly` is a lender or mentor view
-- (codex 00) and is nobody's job, while `shift_lead` carries no admin access
-- distinct from crew's. Adding `shift_lead` here is not licensed by SPEC §5,
-- which names three additions and only three.
ALTER TABLE ref_users DROP CONSTRAINT IF EXISTS ref_users_role_check;

ALTER TABLE ref_users ADD CONSTRAINT ref_users_role_check
    CHECK (role IN ('owner', 'field_manager', 'office',
                    'store_manager', 'crew', 'readonly'));
