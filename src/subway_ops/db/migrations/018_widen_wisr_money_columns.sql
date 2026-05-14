-- The previous migration (017) widened percentage columns. Backfill still
-- fails on a different overflow: NUMERIC(12,4) money columns (value_used,
-- value_difference, cost) can't hold Wisr's occasional anomaly values
-- (>= 100 million). Widen to NUMERIC(18,4), capping at ±99 trillion —
-- absurdly safe for any real-world inventory value.

ALTER TABLE stg_wisr_inventory_items
    ALTER COLUMN open_qty         TYPE NUMERIC(18,4),
    ALTER COLUMN delivered_qty    TYPE NUMERIC(18,4),
    ALTER COLUMN left_qty         TYPE NUMERIC(18,4),
    ALTER COLUMN used_qty         TYPE NUMERIC(18,4),
    ALTER COLUMN pos_difference   TYPE NUMERIC(18,4),
    ALTER COLUMN recorded_waste   TYPE NUMERIC(18,4),
    ALTER COLUMN cost             TYPE NUMERIC(18,4),
    ALTER COLUMN value_used       TYPE NUMERIC(18,4),
    ALTER COLUMN value_difference TYPE NUMERIC(18,4);

-- Same liberalisation on stg_wisr_weekly's NUMERIC(12,4) columns.
DO $$
DECLARE
    col_name TEXT;
BEGIN
    FOR col_name IN
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'stg_wisr_weekly'
          AND data_type = 'numeric'
          AND numeric_precision = 12
          AND numeric_scale = 4
    LOOP
        EXECUTE format(
            'ALTER TABLE stg_wisr_weekly ALTER COLUMN %I TYPE NUMERIC(18,4)',
            col_name
        );
    END LOOP;
END $$;
