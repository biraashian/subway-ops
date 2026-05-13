-- 003_daily_sales.sql
-- Raw + staging tables for the DailySalesSummary endpoint.

CREATE TABLE IF NOT EXISTS raw_daily_sales (
    id            BIGSERIAL PRIMARY KEY,
    fetched_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    start_date    DATE NOT NULL,
    end_date      DATE NOT NULL,
    payload       JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_raw_daily_sales_dates
    ON raw_daily_sales (start_date, end_date);

CREATE TABLE IF NOT EXISTS stg_daily_sales (
    restaurant_number          TEXT NOT NULL REFERENCES ref_stores(store_number),
    business_date              DATE NOT NULL,
    net_sales                  NUMERIC(12,4) NOT NULL,
    tax                        NUMERIC(12,4) NOT NULL,
    units                      INTEGER NOT NULL,
    transactions               INTEGER NOT NULL,
    cash_card_total            NUMERIC(12,4) NOT NULL,
    third_party_sales          NUMERIC(12,4) NOT NULL,
    third_party_transactions   INTEGER NOT NULL,
    hours_worked               NUMERIC(8,2) NOT NULL,
    ingested_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (restaurant_number, business_date)
);

CREATE INDEX IF NOT EXISTS idx_stg_daily_sales_date
    ON stg_daily_sales (business_date);
