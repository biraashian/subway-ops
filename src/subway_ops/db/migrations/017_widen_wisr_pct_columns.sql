-- Widen percentage columns in stg_wisr_inventory_items to handle
-- real-world inventory anomalies (one-off adjustments, tiny denominators)
-- that can produce percentages well beyond ±100.
--
-- Before: NUMERIC(8,6) → range ±99.999999
-- After:  NUMERIC(12,6) → range ±999,999.999999
--
-- The scale stays at 6 (six decimal places of precision); only the
-- precision (total digit count) grows.

ALTER TABLE stg_wisr_inventory_items
    ALTER COLUMN actual_percentage   TYPE NUMERIC(12,6),
    ALTER COLUMN expected_percentage TYPE NUMERIC(12,6),
    ALTER COLUMN diff_percentage     TYPE NUMERIC(12,6);

-- Same fix on stg_wisr_weekly for any percentage-typed columns there.
-- Apply liberally; widening NUMERIC is safe and non-destructive.
DO $$
DECLARE
    col_name TEXT;
BEGIN
    FOR col_name IN
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'stg_wisr_weekly'
          AND data_type = 'numeric'
          AND numeric_precision = 8
          AND numeric_scale = 6
    LOOP
        EXECUTE format(
            'ALTER TABLE stg_wisr_weekly ALTER COLUMN %I TYPE NUMERIC(12,6)',
            col_name
        );
    END LOOP;
END $$;
