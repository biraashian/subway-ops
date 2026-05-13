-- 013_backfill_progress.sql
-- One row per (endpoint, window) successfully ingested by the backfill
-- script. ``scripts/backfill.py`` consults this table to skip already-
-- completed windows, making the whole 12-month backfill safely
-- resumable across rate-limit interruptions.

CREATE TABLE IF NOT EXISTS ops_backfill_progress (
    job_name     TEXT NOT NULL,
    endpoint     TEXT NOT NULL,
    window_start DATE NOT NULL,
    window_end   DATE NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (job_name, endpoint, window_start, window_end)
);

CREATE INDEX IF NOT EXISTS idx_ops_backfill_progress_endpoint
    ON ops_backfill_progress (endpoint, window_start);
