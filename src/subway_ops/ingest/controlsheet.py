"""Ingest pipeline for the FreshConnect ``controlsheet`` endpoint.

ControlSheet is the richest endpoint: per store per closed business week,
the API returns six nested sections (cash control, bread, labor, metrics,
sales itemization, unit itemization), most of which are dicts keyed by day
of week. We flatten every dict into one column per (field x day) plus a
footer column that absorbs either ``total`` or ``average`` depending on
which the API emits for that field. The result is a very wide
``stg_controlsheet_weekly`` table (~330 columns) keyed on
``(restaurant_number, week_end_date)``.

The schema is derived from the field tables defined below: the migration
runner only sees the resulting SQL, but the same Python definitions are
reused by ``flatten_row`` so the DDL and the upsert payload stay in sync.

Public surface:

    ingest(week_end, store_numbers=None, *, client=None) -> int

A small CLI is provided for emitting the table DDL exactly once:

    uv run python -m subway_ops.ingest.controlsheet --print-ddl
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from typing import Any

import structlog
from sqlalchemy import text

from subway_ops.db.connection import get_engine
from subway_ops.db.job_runs import track_job
from subway_ops.db.upsert import upsert_rows
from subway_ops.freshconnect.client import FreshConnectClient
from subway_ops.freshconnect.models import ControlSheetResponse, ControlSheetRow

MAX_STORES_PER_CALL = 40
JOB_NAME = "ingest_controlsheet"

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Field-by-field section definitions
# ---------------------------------------------------------------------------
#
# Each section maps an API camelCase field name to whether the API also
# emits a paired ``percentage`` value alongside the day-of-week dict. The
# footer column (``*_total``) is always present and absorbs either ``total``
# or ``average`` — labor and rate-like metrics use ``average`` upstream.

DAYS_DAILY = ("wed", "thu", "fri", "sat", "sun", "mon", "tue")
FOOTER_COL = "total"  # captures total OR average from the model


CASH_CONTROL_FIELDS: tuple[tuple[str, bool], ...] = (
    ("closingGrandTotal", False), ("openingGrandTotal", False),
    ("adjustments", False), ("adjustedProceeds", False),
    ("openingCash", False), ("paidouts", False), ("creditSales", False),
    ("requiredCash", False), ("actualCash", False), ("overShort", False),
    ("closingKeep", False), ("depositInBank", False), ("cashcards", False),
    ("debit", False), ("visaAndMastercard", False), ("discover", False),
    ("americanExpress", False), ("cateringCallCenter", False),
    ("other", False), ("payPal", False), ("cashRoundingAdjustment", False),
)

BREAD_FIELDS: tuple[tuple[str, bool], ...] = (
    ("opening", False), ("delivered", False), ("credits", False),
    ("left", False), ("used", False), ("sold", False), ("overShort", False),
    ("breadLeft", False), ("breadOverShort", False),
    ("flatbreadLeft", False), ("flatbreadOverShort", False),
    ("saladLeft", False), ("saladOverShort", False),
    ("muffinLeft", False), ("muffinOverShort", False),
    ("pizzaLeft", False), ("pizzaOverShort", False),
    ("otherLeft", False), ("otherOverShort", False),
)

LABOR_FIELDS: tuple[tuple[str, bool], ...] = (
    ("hoursOpen", False), ("hoursWorked", False),
    ("productivity", False), ("salesPerLaborHour", False),
)

METRICS_FIELDS: tuple[tuple[str, bool], ...] = (
    ("factor", False), ("customerCount", False), ("averageTicket", False),
)

# salesItemization: most fields include a percentage, five do not (see the
# live-fixture exploration in Task 1.3 / api_field_coverage.md).
SALES_ITEMIZATION_FIELDS: tuple[tuple[str, bool], ...] = (
    ("totalSubwaySales", True), ("footlong", True), ("sixInch", True),
    ("threeInch", True), ("muffinMelt", True), ("salad", True),
    ("pizza", True), ("otherCarrier", True), ("addOn", True),
    ("catering", True), ("unitCouponsDiscounts", True),
    ("unitRefunds", True), ("unitVoids", True), ("totalUnitsSales", True),
    ("fountain", True), ("bottledBeverage", True), ("hotBeverage", True),
    ("otherBeverage", True), ("drinksCouponsDiscounts", True),
    ("drinksRefunds", True), ("drinksVoids", True),
    ("totalDrinksSales", True), ("chips", True), ("cookies", True),
    ("soups", True), ("otherMisc", True), ("miscCouponsDiscounts", True),
    ("miscRefunds", True), ("miscVoids", True), ("totalMiscSales", True),
    ("cashCardSales", False), ("adjSalesTaxAndFees", False),
    ("taxAndFeeAdjustments", True), ("adjOtherReceipts", False),
    ("adjCoBrandSales", False), ("otherAdjustments", True),
)

UNIT_ITEMIZATION_FIELDS: tuple[tuple[str, bool], ...] = (
    ("footlong", True), ("sixInch", True), ("threeInch", True),
    ("muffinMelt", True), ("salad", True), ("pizza", True),
    ("otherCarrier", True), ("catering", True),
    ("employeeAndFreeUnits", True), ("totalUnits", False),
    ("allUnitsSold", False), ("drink", True),
    ("drinkPercentage", False),  # day values ARE percentages; footer is average
)

SECTION_PREFIX = {
    "cash_control": ("cash_control", CASH_CONTROL_FIELDS),
    "bread": ("bread", BREAD_FIELDS),
    "labor": ("labor", LABOR_FIELDS),
    "metrics": ("metrics", METRICS_FIELDS),
    "sales_itemization": ("sales_itemization", SALES_ITEMIZATION_FIELDS),
    "unit_itemization": ("unit_itemization", UNIT_ITEMIZATION_FIELDS),
}


# ---------------------------------------------------------------------------
# Snake-case helper & column generation
# ---------------------------------------------------------------------------


def _to_snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _section_columns(prefix: str, fields: tuple[tuple[str, bool], ...]) -> list[tuple[str, str]]:
    """Return ``(column_name, sql_type)`` pairs for a section.

    Daily and footer columns are ``NUMERIC(12,4)``; percentage columns are
    ``NUMERIC(8,4)``.
    """
    cols: list[tuple[str, str]] = []
    for api_name, has_pct in fields:
        base = _to_snake(api_name)
        for day in DAYS_DAILY:
            cols.append((f"{prefix}_{base}_{day}", "NUMERIC(12,4)"))
        cols.append((f"{prefix}_{base}_{FOOTER_COL}", "NUMERIC(12,4)"))
        if has_pct:
            cols.append((f"{prefix}_{base}_percentage", "NUMERIC(8,4)"))
    return cols


_SUMMARY_COLUMNS: list[tuple[str, str]] = [
    ("cost_of_good_percentage", "NUMERIC(8,4)"),
    ("cost_of_units_percentage", "NUMERIC(8,4)"),
    ("drink_cost_percentage", "NUMERIC(8,4)"),
    ("adjusted_cost_of_goods_percentage", "NUMERIC(8,4)"),
    ("adjusted_cost_of_units_percentage", "NUMERIC(8,4)"),
    ("misc_cost_percentage", "NUMERIC(8,4)"),
    ("productivity", "NUMERIC(8,4)"),
    ("factor", "NUMERIC(8,4)"),
    ("customer_count", "INTEGER"),
    ("net_sales", "NUMERIC(12,4)"),
]


def column_definitions() -> list[tuple[str, str]]:
    """Return every non-key column as ``(name, sql_type)`` in DDL order."""
    cols: list[tuple[str, str]] = list(_SUMMARY_COLUMNS)
    for prefix, fields in SECTION_PREFIX.values():
        cols.extend(_section_columns(prefix, fields))
    return cols


# ---------------------------------------------------------------------------
# DDL generation (for migration authoring; not a runtime concern)
# ---------------------------------------------------------------------------


def generate_ddl() -> str:
    cols = column_definitions()
    lines = [
        "-- 004_controlsheet.sql",
        "-- Raw + flattened-weekly staging for the controlsheet endpoint.",
        "-- This file was generated from subway_ops.ingest.controlsheet.column_definitions().",
        "-- Re-run `python -m subway_ops.ingest.controlsheet --print-ddl` to regenerate.",
        "",
        "CREATE TABLE IF NOT EXISTS raw_controlsheet (",
        "    id            BIGSERIAL PRIMARY KEY,",
        "    fetched_at    TIMESTAMPTZ NOT NULL DEFAULT now(),",
        "    week_end_date DATE NOT NULL,",
        "    payload       JSONB NOT NULL",
        ");",
        "",
        "CREATE INDEX IF NOT EXISTS idx_raw_controlsheet_week_end",
        "    ON raw_controlsheet (week_end_date);",
        "",
        "CREATE TABLE IF NOT EXISTS stg_controlsheet_weekly (",
        "    restaurant_number  TEXT NOT NULL REFERENCES ref_stores(store_number),",
        "    week_end_date      DATE NOT NULL,",
    ]
    width = max(len(c) for c, _ in cols)
    for name, typ in cols:
        lines.append(f"    {name.ljust(width)}  {typ},")
    lines.extend(
        [
            "    ingested_at        TIMESTAMPTZ NOT NULL DEFAULT now(),",
            "    PRIMARY KEY (restaurant_number, week_end_date)",
            ");",
            "",
            "CREATE INDEX IF NOT EXISTS idx_stg_controlsheet_week_end",
            "    ON stg_controlsheet_weekly (week_end_date);",
            "",
        ]
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Row flattening
# ---------------------------------------------------------------------------


def _dow_to_dict(prefix: str, field_snake: str, dow: Any, has_pct: bool) -> dict[str, Any]:
    """Pull daily, footer and (optionally) percentage values from a ``DaysOfWeek``."""
    out: dict[str, Any] = {}
    for day in DAYS_DAILY:
        out[f"{prefix}_{field_snake}_{day}"] = getattr(dow, day)
    # Some sections emit "average" instead of "total"; collapse both into one col.
    footer = dow.total if dow.total is not None else dow.average
    out[f"{prefix}_{field_snake}_{FOOTER_COL}"] = footer
    if has_pct:
        out[f"{prefix}_{field_snake}_percentage"] = dow.percentage
    return out


def flatten_row(row: ControlSheetRow) -> dict[str, Any]:
    """Map a parsed ControlSheet row to a flat stg dict."""
    out: dict[str, Any] = {
        "restaurant_number": row.summary.store_number,
        "week_end_date": row.summary.week_end_date.date(),
        "cost_of_good_percentage": row.summary.cost_of_good_percentage,
        "cost_of_units_percentage": row.summary.cost_of_units_percentage,
        "drink_cost_percentage": row.summary.drink_cost_percentage,
        "adjusted_cost_of_goods_percentage": row.summary.adjusted_cost_of_goods_percentage,
        "adjusted_cost_of_units_percentage": row.summary.adjusted_cost_of_units_percentage,
        "misc_cost_percentage": row.summary.misc_cost_percentage,
        "productivity": row.summary.productivity,
        "factor": row.summary.factor,
        "customer_count": row.summary.customer_count,
        "net_sales": row.summary.net_sales,
    }

    section_models = {
        "cash_control": row.cash_control,
        "bread": row.bread,
        "labor": row.labor,
        "metrics": row.metrics,
        "sales_itemization": row.sales_itemization,
        "unit_itemization": row.unit_itemization,
    }
    for section_key, (prefix, fields) in SECTION_PREFIX.items():
        section_model = section_models[section_key]
        for api_name, has_pct in fields:
            snake = _to_snake(api_name)
            dow = getattr(section_model, snake)
            out.update(_dow_to_dict(prefix, snake, dow, has_pct))
    return out


# ---------------------------------------------------------------------------
# Persistence + entry point
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
                "INSERT INTO raw_controlsheet (week_end_date, payload) "
                "VALUES (:we, CAST(:payload AS JSONB))"
            ),
            {"we": week_end, "payload": json.dumps(payload)},
        )


def _chunk(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def ingest(
    week_end: date,
    store_numbers: list[str] | None = None,
    *,
    client: FreshConnectClient | None = None,
) -> int:
    """Ingest ControlSheet rows for a single week-end Tuesday.

    Args:
        week_end: The Tuesday closing the business week to fetch. Pass an
            already-resolved business date (the calendar helper
            ``previous_business_week`` returns one).
        store_numbers: Specific stores to query. ``None`` means every
            active store in ``ref_stores``.
        client: Optional pre-built FreshConnect client (for tests).

    Returns:
        Number of rows written to ``stg_controlsheet_weekly``.
    """
    if store_numbers is None:
        store_numbers = _active_store_numbers()
    if not store_numbers:
        log.warning("ingest_controlsheet_no_stores")
        return 0

    batches = _chunk(store_numbers, MAX_STORES_PER_CALL)
    log.info(
        "ingest_controlsheet_plan",
        store_count=len(store_numbers),
        batch_count=len(batches),
        week_end=str(week_end),
    )

    total_rows = 0
    owns_client = client is None

    with track_job(JOB_NAME) as meta:
        meta["week_end"] = week_end.isoformat()
        meta["store_count"] = len(store_numbers)
        meta["batch_count"] = len(batches)

        c = client or FreshConnectClient()
        try:
            for stores in batches:
                payload = c.get_control_sheet(stores, week_end)
                _store_raw(week_end, payload)
                parsed = ControlSheetResponse.model_validate(payload)
                stg_rows = [flatten_row(r) for r in parsed.data]
                written = upsert_rows(
                    "stg_controlsheet_weekly",
                    stg_rows,
                    key_cols=["restaurant_number", "week_end_date"],
                )
                total_rows += written
                log.info(
                    "ingest_controlsheet_batch_done",
                    stores=stores,
                    week_end=str(week_end),
                    rows=written,
                )
        finally:
            if owns_client:
                c.close()

        meta["rows_written"] = total_rows

    return total_rows


# ---------------------------------------------------------------------------
# CLI: emit DDL
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
