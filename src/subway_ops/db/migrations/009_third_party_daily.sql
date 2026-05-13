-- 009_third_party_daily.sql
-- Raw envelope + per-day totals + per-day-per-provider staging for the
-- ThirdPartyDailySalesSummary endpoint.

CREATE TABLE IF NOT EXISTS raw_third_party_daily (
    id          BIGSERIAL PRIMARY KEY,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    start_date  DATE NOT NULL,
    end_date    DATE NOT NULL,
    payload     JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_raw_third_party_daily_dates
    ON raw_third_party_daily (start_date, end_date);

CREATE TABLE IF NOT EXISTS stg_3p_daily (
    restaurant_number   TEXT NOT NULL REFERENCES ref_stores(store_number),
    business_date       DATE NOT NULL,
    total_sales         NUMERIC(12,4),
    total_net_sales     NUMERIC(12,4),
    total_transactions  INTEGER,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (restaurant_number, business_date)
);

CREATE INDEX IF NOT EXISTS idx_stg_3p_daily_business_date
    ON stg_3p_daily (business_date);

CREATE TABLE IF NOT EXISTS stg_3p_daily_provider (
    restaurant_number  TEXT NOT NULL REFERENCES ref_stores(store_number),
    business_date      DATE NOT NULL,
    provider           TEXT NOT NULL,
    transactions       INTEGER,
    net_sales          NUMERIC(12,4),
    sales              NUMERIC(12,4),
    ingested_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (restaurant_number, business_date, provider)
);

CREATE INDEX IF NOT EXISTS idx_stg_3p_daily_provider_business_date
    ON stg_3p_daily_provider (business_date);
