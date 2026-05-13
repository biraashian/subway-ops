-- 008_timeclock.sql
-- Raw envelope + typed staging for the DailyTimeclock endpoint.

CREATE TABLE IF NOT EXISTS raw_timeclock (
    id          BIGSERIAL PRIMARY KEY,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    start_date  DATE NOT NULL,
    end_date    DATE NOT NULL,
    payload     JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_raw_timeclock_dates
    ON raw_timeclock (start_date, end_date);

CREATE TABLE IF NOT EXISTS stg_timeclock (
    restaurant_number  TEXT NOT NULL REFERENCES ref_stores(store_number),
    clerk_id           TEXT NOT NULL,
    clock_in           TIMESTAMP NOT NULL,
    clock_out          TIMESTAMP,
    business_date      DATE NOT NULL,
    employee_name      TEXT,
    hours_before_adj   NUMERIC(8,4),
    hours_after_adj    NUMERIC(8,4),
    adj_amount         NUMERIC(8,4),
    ingested_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (restaurant_number, clerk_id, clock_in)
);

CREATE INDEX IF NOT EXISTS idx_stg_timeclock_business_date
    ON stg_timeclock (business_date);
