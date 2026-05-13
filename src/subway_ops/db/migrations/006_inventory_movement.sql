-- 006_inventory_movement.sql
-- Raw envelope + per-item and per-day-total staging for the
-- InventoryMovement endpoint.

CREATE TABLE IF NOT EXISTS raw_inventory_movement (
    id          BIGSERIAL PRIMARY KEY,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    start_date  DATE NOT NULL,
    end_date    DATE NOT NULL,
    payload     JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_raw_inventory_movement_dates
    ON raw_inventory_movement (start_date, end_date);

CREATE TABLE IF NOT EXISTS stg_inventory_movement (
    restaurant_number  TEXT NOT NULL REFERENCES ref_stores(store_number),
    business_date      DATE NOT NULL,
    item_category      TEXT NOT NULL,       -- e.g. "Bread", "Cheese"
    inventory_item     TEXT NOT NULL,       -- e.g. "Bread, White, 80/1"
    unit_of_measure    TEXT,
    unit_cost          NUMERIC(12,4),
    delivery           NUMERIC(12,4),
    transfer           NUMERIC(12,4),
    total_cost         NUMERIC(12,4),
    waste              NUMERIC(12,4),
    waste_value        NUMERIC(12,4),
    ingested_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (restaurant_number, business_date, inventory_item)
);

CREATE INDEX IF NOT EXISTS idx_stg_inventory_movement_business_date
    ON stg_inventory_movement (business_date);

CREATE TABLE IF NOT EXISTS stg_inventory_movement_totals (
    restaurant_number  TEXT NOT NULL REFERENCES ref_stores(store_number),
    business_date      DATE NOT NULL,
    metric_name        TEXT NOT NULL,       -- e.g. "UNITS COST"
    total_cost         NUMERIC(12,4),
    waste_value        NUMERIC(12,4),
    ingested_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (restaurant_number, business_date, metric_name)
);

CREATE INDEX IF NOT EXISTS idx_stg_inventory_movement_totals_date
    ON stg_inventory_movement_totals (business_date);
