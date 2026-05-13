-- 012_mart_field_manager_portfolio.sql
-- One row per (field_manager_name, week_end_date) — the FM-level rollup
-- read by the dashboard's "field manager portfolio" view. Sales-weighted
-- KPIs and store-in-target counts. Targets live in subway_ops.config:
-- portfolio thresholds are tighter (20% / 25%) than the per-store ones
-- (22% / 28%) the source rows are flagged against.

CREATE TABLE IF NOT EXISTS mart_field_manager_portfolio (
    field_manager_name                  TEXT NOT NULL REFERENCES ref_field_managers(name),
    week_end_date                       DATE NOT NULL,

    store_count                         INTEGER NOT NULL,
    store_count_in_target_food          INTEGER NOT NULL,
    store_count_in_target_labor         INTEGER NOT NULL,

    total_net_sales_weighted            NUMERIC(14,4),
    portfolio_food_cost_pct             NUMERIC(8,6),
    portfolio_labor_cost_pct            NUMERIC(8,6),

    is_food_cost_in_portfolio_target    BOOLEAN GENERATED ALWAYS AS (
        CASE WHEN portfolio_food_cost_pct IS NULL THEN NULL
             ELSE portfolio_food_cost_pct <= 0.20 END
    ) STORED,
    is_labor_cost_in_portfolio_target   BOOLEAN GENERATED ALWAYS AS (
        CASE WHEN portfolio_labor_cost_pct IS NULL THEN NULL
             ELSE portfolio_labor_cost_pct <= 0.25 END
    ) STORED,

    refreshed_at                        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (field_manager_name, week_end_date)
);

CREATE INDEX IF NOT EXISTS idx_mart_fm_portfolio_week_end
    ON mart_field_manager_portfolio (week_end_date);
