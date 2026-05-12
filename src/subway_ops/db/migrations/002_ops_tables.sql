-- 002_ops_tables.sql
-- Operational metadata: migration ledger and per-job-run audit trail.

CREATE TABLE IF NOT EXISTS ops_migrations (
    filename     TEXT PRIMARY KEY,
    applied_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    checksum     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_job_runs (
    id           BIGSERIAL PRIMARY KEY,
    job_name     TEXT NOT NULL,
    started_at   TIMESTAMPTZ NOT NULL,
    finished_at  TIMESTAMPTZ,
    status       TEXT NOT NULL CHECK (status IN ('running','success','failed')),
    rows_written INTEGER,
    error_text   TEXT,
    metadata     JSONB
);

CREATE INDEX IF NOT EXISTS idx_job_runs_name_started
    ON ops_job_runs (job_name, started_at DESC);
