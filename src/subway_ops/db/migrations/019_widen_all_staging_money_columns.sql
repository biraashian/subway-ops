-- Sweep: widen every NUMERIC(12,4) money column across the staging layer.
-- Wisr produces occasional anomaly values >= 100M; same risk exists on
-- ControlSheet, InventoryMovement, and DailySales for stores with
-- one-off POS/inventory misreports. NUMERIC(18,4) holds up to ±99T
-- which is well past any realistic Subway store dollar amount.

DO $$
DECLARE
    rec RECORD;
BEGIN
    FOR rec IN
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND data_type = 'numeric'
          AND numeric_precision = 12
          AND numeric_scale = 4
          AND table_name LIKE 'stg_%'
    LOOP
        EXECUTE format(
            'ALTER TABLE %I ALTER COLUMN %I TYPE NUMERIC(18,4)',
            rec.table_name, rec.column_name
        );
        RAISE NOTICE 'Widened %.%', rec.table_name, rec.column_name;
    END LOOP;
END $$;
