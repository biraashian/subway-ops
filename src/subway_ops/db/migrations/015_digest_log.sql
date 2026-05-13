-- 015_digest_log.sql
-- One row per week_end whose digest has been sent. Drives the
-- "already sent" guard in scripts/send_weekly_digest.py so a manual
-- workflow_dispatch re-trigger never spams operators twice.

CREATE TABLE IF NOT EXISTS ops_digest_log (
    week_end_date    DATE PRIMARY KEY,
    sent_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    recipient_count  INTEGER NOT NULL,
    subject          TEXT NOT NULL
);
