-- 005_paidouts_no_sales.sql
-- Raw envelope + typed staging for the PaidOutsAndNoSales endpoint.
--
-- The endpoint returns two parallel arrays (noSales and paidOuts); each
-- lands in its own stg table keyed on the natural composite. The
-- stg_cash_drops view is the operator-friendly filter for the no-sale
-- subtype that drives the reconciliation flow.

CREATE TABLE IF NOT EXISTS raw_paidouts_no_sales (
    id          BIGSERIAL PRIMARY KEY,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    start_date  DATE NOT NULL,
    end_date    DATE NOT NULL,
    payload     JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_raw_paidouts_no_sales_dates
    ON raw_paidouts_no_sales (start_date, end_date);

CREATE TABLE IF NOT EXISTS stg_no_sales (
    restaurant_number  TEXT NOT NULL REFERENCES ref_stores(store_number),
    event_time         TIMESTAMP NOT NULL,
    business_date      DATE NOT NULL,
    clerk_id           TEXT NOT NULL,
    clerk_name         TEXT,
    no_sale_type       TEXT NOT NULL,
    reason_type        TEXT,
    reason             TEXT,
    ingested_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (restaurant_number, event_time, clerk_id, no_sale_type)
);

CREATE INDEX IF NOT EXISTS idx_stg_no_sales_business_date
    ON stg_no_sales (business_date);

CREATE TABLE IF NOT EXISTS stg_paid_outs (
    restaurant_number  TEXT NOT NULL REFERENCES ref_stores(store_number),
    event_time         TIMESTAMP NOT NULL,
    business_date      DATE NOT NULL,
    clerk_id           TEXT NOT NULL,
    clerk_name         TEXT,
    amount             NUMERIC(12,4) NOT NULL,
    reason             TEXT,
    comment            TEXT,
    ingested_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (restaurant_number, event_time, clerk_id, amount, reason)
);

CREATE INDEX IF NOT EXISTS idx_stg_paid_outs_business_date
    ON stg_paid_outs (business_date);

CREATE OR REPLACE VIEW stg_cash_drops AS
SELECT * FROM stg_no_sales WHERE no_sale_type = 'cash drop';
