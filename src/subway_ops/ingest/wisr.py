"""Ingest pipeline for the FreshConnect ``wisr`` endpoint.

The endpoint returns Subway's gold-standard weekly food-cost analysis. The
response is dense: per (store, weekEnd) it carries six nested rollup
sections plus a long ``inventoryItems`` list (~120 ingredients per store).

We persist:
- ``raw_wisr`` — the JSONB envelope log.
- ``stg_wisr_weekly`` — one wide row per (store, week_end_date) with every
  rollup flattened.
- ``stg_wisr_inventory_items`` — one row per (store, week_end_date, item).

As with ``controlsheet``, the column list is generated from Python
field-section tables so the on-disk DDL and the upsert payload can never
drift. Run ``python -m subway_ops.ingest.wisr --print-ddl`` to regenerate
the migration.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from typing import Any

import structlog
from sqlalchemy import text

from subway_ops.db.connection import get_engine
from subway_ops.db.job_runs import track_job
from subway_ops.db.upsert import upsert_rows
from subway_ops.freshconnect.client import FreshConnectClient
from subway_ops.freshconnect.models import WisrResponse, WisrRow

MAX_STORES_PER_CALL = 25
JOB_NAME = "ingest_wisr"

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Field-section definitions
# ---------------------------------------------------------------------------

# Short section prefixes keep flattened column names readable and avoid
# clashes between sub-fields that happen to share a name across sections
# (e.g. salesSummaryItems.costOfGoods vs inventoryCategoriesSummary.costOfGoods).
_SECTION_PREFIX = {
    "adjusted_cost_of_goods": "acg",
    "inventory_categories_summary": "ics",
    "sales_summary_items": "ssi",
    "units_summary_items": "usi",
    "catering_summary_items": "csi",
    "distribution_costs": "dc",
}

# adjustedCostOfGoods.<field>: 3 cols each (quantity, value, percentage)
_ACG_FIELDS = (
    "free_units", "employee_free", "employee_discounts",
    "other_discount_value", "fvm_discounts_value",
    "misc_and_drink_disc_value", "total_discount_value",
    "discount_value_pct_of_sales", "adjusted_cost_of_goods",
)
_ACG_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("quantity", "NUMERIC(12,4)"),
    ("value", "NUMERIC(12,4)"),
    ("percentage", "NUMERIC(10,6)"),
)

# inventoryCategoriesSummary.<field>: 5 cols each
_ICS_FIELDS = (
    "cheese", "meat_protein", "bread_carrier", "veggies", "toppings",
    "papergoods", "units_cost", "drinks_cost", "misc_cost", "cost_of_goods",
    "distribution_cost",
)
_ICS_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("value_used", "NUMERIC(12,4)"),
    ("value_diff", "NUMERIC(12,4)"),
    ("actual_percentage", "NUMERIC(10,6)"),
    ("expected_percentage", "NUMERIC(10,6)"),
    ("percentage_diff", "NUMERIC(10,6)"),
)

# salesSummaryItems.<field>: 2 cols each (value, percentage)
_SSI_FIELDS = (
    "unit_sales", "catering_sales", "drink_sales", "misc_sales",
    "net_subway_sales", "gas", "electric", "telephone", "garbage",
    "insurance", "rent", "laundry", "misc", "repair_maintenance",
    "operating_expenses", "labor_and_taxes", "cost_of_goods", "royalty",
    "faf", "local_advertising", "total_expenses", "balance",
    "financial_strength", "loans",
)
_SSI_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("value", "NUMERIC(12,4)"),
    ("percentage", "NUMERIC(10,6)"),
)

# unitsSummaryItems.<field>: 2 cols each (quantity, percentage)
_USI_FIELDS = (
    "footlong", "six_inch", "three_inch_and_muffin", "salads", "pizza",
    "other_units", "total_units", "drinks",
)
_USI_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("quantity", "NUMERIC(12,4)"),
    ("percentage", "NUMERIC(10,6)"),
)

# cateringSummaryItems.<field>: 2 cols each (quantity, value)
_CSI_FIELDS = ("giant_subs", "sandwich_platters", "boxed_meals", "dessert_platters")
_CSI_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("quantity", "NUMERIC(12,4)"),
    ("value", "NUMERIC(12,4)"),
)

# distributionCosts.<field>: 2 cols each (value_used, actual_percent)
_DC_FIELDS = (
    "delivery_fee", "distributor_credits", "annual_ipc_patronage",
    "distribution_costs",
)
_DC_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("value_used", "NUMERIC(12,4)"),
    ("actual_percent", "NUMERIC(10,6)"),
)

# cashBreadOverShortTotals: two sub-objects (cash, bread) x 8 day keys.
_CBOST_SUBS = (
    ("cash", "cash_daily_figures"),
    ("bread", "bread_daily_figures"),
)
_CBOST_DAYS = (
    ("wed", "wednesday"), ("thu", "thursday"), ("fri", "friday"),
    ("sat", "saturday"), ("sun", "sunday"), ("mon", "monday"),
    ("tue", "tuesday"), ("total", "total"),
)


# Top-level scalars on WisrRow.
_TOP_LEVEL_COLS: tuple[tuple[str, str, str], ...] = (
    # (db_column, model_attribute, sql_type)
    ("total_inventory_value", "total_inventory_value", "NUMERIC(12,4)"),
    ("customer_count", "customer_count", "NUMERIC(12,4)"),
    ("units_per_customer", "units_per_customer", "NUMERIC(10,6)"),
    ("factor", "factor", "NUMERIC(10,6)"),
    ("average_ticket", "average_ticket", "NUMERIC(10,6)"),
)


def _section_columns(
    prefix: str,
    fields: tuple[str, ...],
    suffixes: tuple[tuple[str, str], ...],
) -> list[tuple[str, str]]:
    cols: list[tuple[str, str]] = []
    for field in fields:
        for suffix, sql_type in suffixes:
            cols.append((f"{prefix}_{field}_{suffix}", sql_type))
    return cols


def _cbost_columns() -> list[tuple[str, str]]:
    cols: list[tuple[str, str]] = []
    for sub_short, _attr in _CBOST_SUBS:
        for day_short, _day_long in _CBOST_DAYS:
            cols.append((f"cbost_{sub_short}_{day_short}", "NUMERIC(12,4)"))
    return cols


def column_definitions() -> list[tuple[str, str]]:
    """Every non-key column on ``stg_wisr_weekly`` in DDL order."""
    cols: list[tuple[str, str]] = [(name, typ) for (name, _attr, typ) in _TOP_LEVEL_COLS]
    sp = _SECTION_PREFIX
    cols.extend(_section_columns(sp["adjusted_cost_of_goods"], _ACG_FIELDS, _ACG_SUFFIXES))
    cols.extend(
        _section_columns(sp["inventory_categories_summary"], _ICS_FIELDS, _ICS_SUFFIXES)
    )
    cols.extend(_section_columns(sp["sales_summary_items"], _SSI_FIELDS, _SSI_SUFFIXES))
    cols.extend(_section_columns(sp["units_summary_items"], _USI_FIELDS, _USI_SUFFIXES))
    cols.extend(_section_columns(sp["catering_summary_items"], _CSI_FIELDS, _CSI_SUFFIXES))
    cols.extend(_section_columns(sp["distribution_costs"], _DC_FIELDS, _DC_SUFFIXES))
    cols.extend(_cbost_columns())
    return cols


# ---------------------------------------------------------------------------
# DDL generation
# ---------------------------------------------------------------------------


def generate_ddl() -> str:
    cols = column_definitions()
    width = max(len(c) for c, _ in cols)

    lines = [
        "-- 007_wisr.sql",
        "-- Raw envelope plus flattened weekly + per-item staging for wisr.",
        "-- Generated by subway_ops.ingest.wisr.column_definitions().",
        "-- Re-run `python -m subway_ops.ingest.wisr --print-ddl` to regenerate.",
        "",
        "CREATE TABLE IF NOT EXISTS raw_wisr (",
        "    id            BIGSERIAL PRIMARY KEY,",
        "    fetched_at    TIMESTAMPTZ NOT NULL DEFAULT now(),",
        "    week_end_date DATE NOT NULL,",
        "    payload       JSONB NOT NULL",
        ");",
        "",
        "CREATE INDEX IF NOT EXISTS idx_raw_wisr_week_end",
        "    ON raw_wisr (week_end_date);",
        "",
        "CREATE TABLE IF NOT EXISTS stg_wisr_weekly (",
        "    restaurant_number  TEXT NOT NULL REFERENCES ref_stores(store_number),",
        "    week_end_date      DATE NOT NULL,",
    ]
    for name, typ in cols:
        lines.append(f"    {name.ljust(width)}  {typ},")
    lines.extend([
        "    ingested_at        TIMESTAMPTZ NOT NULL DEFAULT now(),",
        "    PRIMARY KEY (restaurant_number, week_end_date)",
        ");",
        "",
        "CREATE INDEX IF NOT EXISTS idx_stg_wisr_weekly_week_end",
        "    ON stg_wisr_weekly (week_end_date);",
        "",
        "CREATE TABLE IF NOT EXISTS stg_wisr_inventory_items (",
        "    restaurant_number    TEXT NOT NULL REFERENCES ref_stores(store_number),",
        "    week_end_date        DATE NOT NULL,",
        "    item_name            TEXT NOT NULL,",
        "    open_qty             NUMERIC(12,4),",
        "    delivered_qty        NUMERIC(12,4),",
        "    left_qty             NUMERIC(12,4),",
        "    used_qty             NUMERIC(12,4),",
        "    pos_difference       NUMERIC(12,4),",
        "    recorded_waste       NUMERIC(12,4),",
        "    cost                 NUMERIC(12,4),",
        "    value_used           NUMERIC(12,4),",
        "    value_difference     NUMERIC(12,4),",
        "    actual_percentage    NUMERIC(10,6),",
        "    expected_percentage  NUMERIC(10,6),",
        "    diff_percentage      NUMERIC(10,6),",
        "    ingested_at          TIMESTAMPTZ NOT NULL DEFAULT now(),",
        "    PRIMARY KEY (restaurant_number, week_end_date, item_name)",
        ");",
        "",
        "CREATE INDEX IF NOT EXISTS idx_stg_wisr_inventory_items_week_end",
        "    ON stg_wisr_inventory_items (week_end_date);",
        "",
    ])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Row flattening
# ---------------------------------------------------------------------------


def flatten_weekly(row: WisrRow, week_end: date) -> dict[str, Any]:
    """Map a parsed ``WisrRow`` into the wide stg_wisr_weekly shape."""
    out: dict[str, Any] = {
        "restaurant_number": row.restaurant_number,
        "week_end_date": week_end,
    }
    for db_col, model_attr, _typ in _TOP_LEVEL_COLS:
        out[db_col] = getattr(row, model_attr)

    _emit_qvp_section(
        out, "acg", row.adjusted_cost_of_goods, _ACG_FIELDS,
    )
    _emit_ics_section(
        out, "ics", row.inventory_categories_summary, _ICS_FIELDS,
    )
    _emit_value_pct_section(
        out, "ssi", row.sales_summary_items, _SSI_FIELDS,
    )
    _emit_qty_pct_section(
        out, "usi", row.units_summary_items, _USI_FIELDS,
    )
    _emit_qty_value_section(
        out, "csi", row.catering_summary_items, _CSI_FIELDS,
    )
    _emit_dc_section(out, "dc", row.distribution_costs, _DC_FIELDS)

    cbost = row.cash_bread_over_short_totals
    for sub_short, sub_attr in _CBOST_SUBS:
        sub_model = getattr(cbost, sub_attr)
        for day_short, day_long in _CBOST_DAYS:
            out[f"cbost_{sub_short}_{day_short}"] = getattr(sub_model, day_long)
    return out


def _emit_qvp_section(
    out: dict[str, Any], prefix: str, section_model: Any, fields: tuple[str, ...]
) -> None:
    for field in fields:
        sub = getattr(section_model, field)
        out[f"{prefix}_{field}_quantity"] = sub.quantity
        out[f"{prefix}_{field}_value"] = sub.value
        out[f"{prefix}_{field}_percentage"] = sub.percentage


def _emit_ics_section(
    out: dict[str, Any], prefix: str, section_model: Any, fields: tuple[str, ...]
) -> None:
    for field in fields:
        sub = getattr(section_model, field)
        out[f"{prefix}_{field}_value_used"] = sub.value_used
        out[f"{prefix}_{field}_value_diff"] = sub.value_diff
        out[f"{prefix}_{field}_actual_percentage"] = sub.actual_percentage
        out[f"{prefix}_{field}_expected_percentage"] = sub.expected_percentage
        out[f"{prefix}_{field}_percentage_diff"] = sub.percentage_diff


def _emit_value_pct_section(
    out: dict[str, Any], prefix: str, section_model: Any, fields: tuple[str, ...]
) -> None:
    for field in fields:
        sub = getattr(section_model, field)
        out[f"{prefix}_{field}_value"] = sub.value
        out[f"{prefix}_{field}_percentage"] = sub.percentage


def _emit_qty_pct_section(
    out: dict[str, Any], prefix: str, section_model: Any, fields: tuple[str, ...]
) -> None:
    for field in fields:
        sub = getattr(section_model, field)
        out[f"{prefix}_{field}_quantity"] = sub.quantity
        out[f"{prefix}_{field}_percentage"] = sub.percentage


def _emit_qty_value_section(
    out: dict[str, Any], prefix: str, section_model: Any, fields: tuple[str, ...]
) -> None:
    for field in fields:
        sub = getattr(section_model, field)
        out[f"{prefix}_{field}_quantity"] = sub.quantity
        out[f"{prefix}_{field}_value"] = sub.value


def _emit_dc_section(
    out: dict[str, Any], prefix: str, section_model: Any, fields: tuple[str, ...]
) -> None:
    for field in fields:
        sub = getattr(section_model, field)
        out[f"{prefix}_{field}_value_used"] = sub.value_used
        out[f"{prefix}_{field}_actual_percent"] = sub.actual_percent


def flatten_inventory_items(row: WisrRow, week_end: date) -> list[dict[str, Any]]:
    return [
        {
            "restaurant_number": row.restaurant_number,
            "week_end_date": week_end,
            "item_name": it.name,
            "open_qty": it.open,
            "delivered_qty": it.delivered,
            "left_qty": it.left,
            "used_qty": it.used,
            "pos_difference": it.pos_difference,
            "recorded_waste": it.recorded_waste,
            "cost": it.cost,
            "value_used": it.value_used,
            "value_difference": it.value_difference,
            "actual_percentage": it.actual_percentage,
            "expected_percentage": it.expected_percentage,
            "diff_percentage": it.diff_percentage,
        }
        for it in row.inventory_items
    ]


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _active_store_numbers() -> list[str]:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT store_number FROM ref_stores "
                "WHERE is_active = true ORDER BY store_number"
            )
        ).all()
    return [str(r[0]) for r in rows]


def _store_raw(week_end: date, payload: Any) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO raw_wisr (week_end_date, payload) "
                "VALUES (:we, CAST(:p AS JSONB))"
            ),
            {"we": week_end, "p": json.dumps(payload)},
        )


def _chunk(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _dedupe(rows: list[dict[str, Any]], key: tuple[str, ...]) -> list[dict[str, Any]]:
    seen: dict[tuple[Any, ...], dict[str, Any]] = {}
    for r in rows:
        seen[tuple(r[c] for c in key)] = r
    return list(seen.values())


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def ingest(
    week_end: date,
    store_numbers: list[str] | None = None,
    *,
    client: FreshConnectClient | None = None,
) -> int:
    """Ingest Wisr rollups + per-item rows for a single week-end Tuesday.

    Returns total rows written across ``stg_wisr_weekly`` and
    ``stg_wisr_inventory_items``.
    """
    if store_numbers is None:
        store_numbers = _active_store_numbers()
    if not store_numbers:
        log.warning("ingest_wisr_no_stores")
        return 0

    batches = _chunk(store_numbers, MAX_STORES_PER_CALL)
    log.info(
        "ingest_wisr_plan",
        store_count=len(store_numbers),
        batch_count=len(batches),
        week_end=str(week_end),
    )

    total_weekly = 0
    total_items = 0
    owns_client = client is None

    with track_job(JOB_NAME) as meta:
        meta["week_end"] = week_end.isoformat()
        meta["store_count"] = len(store_numbers)
        meta["batch_count"] = len(batches)

        c = client or FreshConnectClient()
        try:
            for stores in batches:
                payload = c.get_wisr(stores, week_end)
                _store_raw(week_end, payload)
                parsed = WisrResponse.model_validate(payload)

                weekly_rows: list[dict[str, Any]] = []
                item_rows: list[dict[str, Any]] = []
                for row in parsed.data:
                    weekly_rows.append(flatten_weekly(row, week_end))
                    item_rows.extend(flatten_inventory_items(row, week_end))

                item_rows = _dedupe(
                    item_rows,
                    ("restaurant_number", "week_end_date", "item_name"),
                )

                weekly_written = upsert_rows(
                    "stg_wisr_weekly",
                    weekly_rows,
                    key_cols=["restaurant_number", "week_end_date"],
                )
                items_written = upsert_rows(
                    "stg_wisr_inventory_items",
                    item_rows,
                    key_cols=["restaurant_number", "week_end_date", "item_name"],
                )
                total_weekly += weekly_written
                total_items += items_written
                log.info(
                    "ingest_wisr_batch_done",
                    stores=stores,
                    week_end=str(week_end),
                    weekly_rows=weekly_written,
                    item_rows=items_written,
                )
        finally:
            if owns_client:
                c.close()

        meta["weekly_rows"] = total_weekly
        meta["item_rows"] = total_items
        meta["rows_written"] = total_weekly + total_items

    return total_weekly + total_items


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--print-ddl",
        action="store_true",
        help="Print the generated migration DDL to stdout and exit.",
    )
    args = parser.parse_args(argv)
    if args.print_ddl:
        print(generate_ddl())
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(_main())
