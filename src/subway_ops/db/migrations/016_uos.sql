-- 016_uos.sql
-- University of Subway training-compliance pipeline. Two tables:
--
--   raw_uos_emails       — append-only log of every Gmail message we've
--                          fetched, keyed by gmail_message_id so a re-fetch
--                          never duplicates. The whole Gmail payload lands
--                          in the JSONB column so we can reparse if the
--                          parser ever changes.
--
--   stg_uos_compliance   — one row per (store, report_date, employee,
--                          course). status is normalised at parse time
--                          to 'complete' / 'overdue' / 'pending'; the
--                          parser is lenient on input strings and logs
--                          unrecognised values to ops_job_runs.metadata.

CREATE TABLE IF NOT EXISTS raw_uos_emails (
    id                BIGSERIAL PRIMARY KEY,
    fetched_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    gmail_message_id  TEXT UNIQUE NOT NULL,
    received_at       TIMESTAMPTZ NOT NULL,
    subject           TEXT,
    attachment_count  INTEGER,
    payload           JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS stg_uos_compliance (
    restaurant_number  TEXT NOT NULL REFERENCES ref_stores(store_number),
    report_date        DATE NOT NULL,
    employee_name      TEXT NOT NULL,
    course_name        TEXT NOT NULL,
    completion_status  TEXT NOT NULL
        CHECK (completion_status IN ('complete', 'overdue', 'pending')),
    completed_at       DATE,
    ingested_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (restaurant_number, report_date, employee_name, course_name)
);

CREATE INDEX IF NOT EXISTS idx_stg_uos_store_date
    ON stg_uos_compliance (restaurant_number, report_date);
