-- 010_mart_store_daily.sql
-- One row per (store, business_date) with every daily-grain KPI joined
-- and computed. This is what the dashboard's "current week" view and
-- 30-day trend charts read. The refresh module
-- (subway_ops.transform.mart_store_daily) rebuilds this from the stg_*
-- tables — never write here directly from ingest code.

CREATE TABLE IF NOT EXISTS mart_store_daily (
    restaurant_number          TEXT NOT NULL REFERENCES ref_stores(store_number),
    business_date              DATE NOT NULL,

    -- From stg_daily_sales:
    net_sales                  NUMERIC(12,4),
    tax                        NUMERIC(12,4),
    transactions               INTEGER,
    units                      INTEGER,
    hours_worked               NUMERIC(8,2),

    -- Derived from stg_daily_sales:
    sales_per_labor_hour       NUMERIC(12,4) GENERATED ALWAYS AS (
        CASE WHEN hours_worked > 0 THEN net_sales / hours_worked ELSE NULL END
    ) STORED,
    average_ticket             NUMERIC(12,4) GENERATED ALWAYS AS (
        CASE WHEN transactions > 0 THEN net_sales / transactions ELSE NULL END
    ) STORED,

    -- From stg_3p_daily:
    third_party_sales          NUMERIC(12,4),
    third_party_transactions   INTEGER,
    third_party_pct            NUMERIC(8,4) GENERATED ALWAYS AS (
        CASE WHEN net_sales > 0 THEN third_party_sales / net_sales ELSE NULL END
    ) STORED,

    -- From stg_inventory_movement_totals (metric_name = 'COST OF GOODS COST'):
    daily_inventory_cost       NUMERIC(12,4),
    daily_inventory_waste      NUMERIC(12,4),

    -- From stg_cash_drops:
    cash_drop_count            INTEGER,

    -- Derived:
    food_cost_pct              NUMERIC(8,4) GENERATED ALWAYS AS (
        CASE WHEN net_sales > 0 THEN daily_inventory_cost / net_sales ELSE NULL END
    ) STORED,

    refreshed_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (restaurant_number, business_date)
);

CREATE INDEX IF NOT EXISTS idx_mart_daily_date
    ON mart_store_daily (business_date);
