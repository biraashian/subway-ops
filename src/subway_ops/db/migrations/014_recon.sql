-- 014_recon.sql
-- Reconciliation: the operator-entered actual bank deposit per
-- (store, week) lives in ops_variance_entries; the auto-computed mart
-- joins POS deposit (from ControlSheet) with that entry and surfaces a
-- status chip. Generated columns own the variance math and the four-
-- way status bucketing, so Python never has to recompute them.
--
-- The 5 / 50 dollar thresholds are duplicated here from
-- subway_ops.config.VARIANCE_FLAGGED_USD / VARIANCE_ESCALATED_USD —
-- GENERATED columns can't reference Python constants. **Keep these
-- two in sync**: any change to the Python constants requires a new
-- migration that ALTER COLUMNs the status expression.

CREATE TABLE IF NOT EXISTS ops_variance_entries (
    restaurant_number    TEXT NOT NULL REFERENCES ref_stores(store_number),
    week_end_date        DATE NOT NULL,
    actual_bank_deposit  NUMERIC(12,4) NOT NULL,
    entered_by           TEXT NOT NULL REFERENCES ref_users(email),
    entered_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    note                 TEXT,
    PRIMARY KEY (restaurant_number, week_end_date)
);

CREATE INDEX IF NOT EXISTS idx_ops_variance_entries_week_end
    ON ops_variance_entries (week_end_date);

CREATE TABLE IF NOT EXISTS mart_recon_weekly (
    restaurant_number    TEXT NOT NULL REFERENCES ref_stores(store_number),
    week_end_date        DATE NOT NULL,
    pos_deposit_in_bank  NUMERIC(12,4),
    actual_bank_deposit  NUMERIC(12,4),

    variance             NUMERIC(12,4) GENERATED ALWAYS AS (
        CASE
            WHEN actual_bank_deposit IS NULL THEN NULL
            ELSE pos_deposit_in_bank - actual_bank_deposit
        END
    ) STORED,

    status               TEXT GENERATED ALWAYS AS (
        CASE
            WHEN actual_bank_deposit IS NULL THEN 'unverified'
            WHEN ABS(pos_deposit_in_bank - actual_bank_deposit) <= 5  THEN 'clean'
            WHEN ABS(pos_deposit_in_bank - actual_bank_deposit) <= 50 THEN 'flagged'
            ELSE 'escalated'
        END
    ) STORED,

    refreshed_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (restaurant_number, week_end_date)
);

CREATE INDEX IF NOT EXISTS idx_mart_recon_weekly_week_end
    ON mart_recon_weekly (week_end_date);

CREATE INDEX IF NOT EXISTS idx_mart_recon_weekly_status
    ON mart_recon_weekly (status);
