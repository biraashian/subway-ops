-- 011_mart_store_weekly.sql
-- One row per (store, week_end_date Tuesday). Joins the wide ControlSheet
-- weekly rollup with the WISR weekly rollup. Percentages are stored as
-- fractional values (0.22 == 22%) so the GENERATED target flags can be
-- written naturally and compared against TARGET_FOOD_COST_STORE etc.
--
-- Refresh logic in subway_ops.transform.mart_store_weekly handles the
-- whole-percent → fractional conversion for WISR fields.

CREATE TABLE IF NOT EXISTS mart_store_weekly (
    restaurant_number             TEXT NOT NULL REFERENCES ref_stores(store_number),
    week_end_date                 DATE NOT NULL,
    week_start_date               DATE GENERATED ALWAYS AS
        (week_end_date - INTERVAL '6 days') STORED,

    -- ControlSheet rollups (already weekly totals or averages):
    net_sales_total               NUMERIC(12,4),
    transactions_total            INTEGER,
    units_total                   INTEGER,
    hours_worked_total            NUMERIC(8,2),
    cash_overshort_total          NUMERIC(12,4),
    bread_overshort_total         NUMERIC(12,4),
    deposit_in_bank_total         NUMERIC(12,4),
    customer_count                INTEGER,
    factor                        NUMERIC(10,4),
    average_ticket                NUMERIC(10,4),
    productivity                  NUMERIC(10,4),

    -- WISR rollups (stored as fractional after dividing the API's whole
    -- percent by 100):
    food_cost_actual_pct          NUMERIC(8,6),
    food_cost_expected_pct        NUMERIC(8,6),
    food_cost_diff_pct            NUMERIC(8,6),
    adjusted_cost_of_goods_pct    NUMERIC(8,6),
    total_inventory_value         NUMERIC(12,4),
    distribution_cost_value       NUMERIC(12,4),

    -- Labor cost: not yet derivable from ControlSheet alone. Stays NULL
    -- until we land an hourly-wage source (planned post-Phase-3); the
    -- is_labor_cost_in_target flag below will then activate.
    -- TODO(labor): plug in wage table and compute hours_worked * wage_rate.
    labor_cost_pct                NUMERIC(8,6),

    -- Target flags (thresholds live in subway_ops.config — keep in sync):
    is_food_cost_in_target        BOOLEAN GENERATED ALWAYS AS (
        CASE WHEN food_cost_actual_pct IS NULL THEN NULL
             ELSE food_cost_actual_pct <= 0.22 END
    ) STORED,
    is_labor_cost_in_target       BOOLEAN GENERATED ALWAYS AS (
        CASE WHEN labor_cost_pct IS NULL THEN NULL
             ELSE labor_cost_pct <= 0.28 END
    ) STORED,

    refreshed_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (restaurant_number, week_end_date)
);

CREATE INDEX IF NOT EXISTS idx_mart_weekly_week_end
    ON mart_store_weekly (week_end_date);
