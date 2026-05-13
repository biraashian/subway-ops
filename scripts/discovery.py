"""FreshConnect endpoint discovery script.

Hits every documented FreshConnect endpoint once against a single store with
the smallest valid window, records the raw response under
``tests/fixtures/recorded/<endpoint>.json``, attempts to parse each response
with its Pydantic model, and writes ``docs/api_field_coverage.md`` summarising
what the API returned versus what our models expect.

Run this whenever the API doc PDFs change or you suspect schema drift. It is
read-only against the API, safe to re-run (overwrites fixtures), and wraps
itself in ``track_job("discovery")`` so each invocation is auditable.

Usage:
    uv run python scripts/discovery.py                # picks the first
                                                       # active store from
                                                       # ref_stores
    uv run python scripts/discovery.py --store 4092   # explicit store
    uv run python scripts/discovery.py --no-db        # skip the DB lookup
                                                       # entirely; --store
                                                       # then required

Rate-limit handling: if the API returns 429, the script stops gracefully and
prints the list of endpoints completed so the operator knows where to resume
tomorrow (quota resets at midnight UTC).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import structlog
from pydantic import BaseModel, ValidationError
from sqlalchemy import text

from subway_ops.calendar import business_date_now, previous_business_week
from subway_ops.db.connection import get_engine
from subway_ops.db.job_runs import track_job
from subway_ops.freshconnect.client import (
    FreshConnectClient,
    RateLimitError,
)
from subway_ops.freshconnect.models import (
    ControlSheetResponse,
    DailySalesSummaryResponse,
    DailyTimeclockResponse,
    InventoryMovementResponse,
    PaidOutsAndNoSalesResponse,
    RestaurantListItem,
    SalesSummaryResponse,
    ThirdPartyDailySalesSummaryResponse,
    ThirdPartySalesSummaryResponse,
    ThirdPartyTransactionSummaryResponse,
    TipsDetailsResponse,
    TransactionDetailsResponse,
    TransactionSummaryResponse,
    WasteBreadCreditsResponse,
    WisrResponse,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "recorded"
COVERAGE_DOC = REPO_ROOT / "docs" / "api_field_coverage.md"
SLEEP_BETWEEN_ENDPOINTS_S = 5.0

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Endpoint registry
# ---------------------------------------------------------------------------

# Each fetcher takes (client, store, day, week_end) and returns parsed JSON.
# Each validator turns raw JSON into a Pydantic instance (or a list, for the
# bare-list /Restaurants endpoint).


@dataclass
class EndpointDef:
    name: str
    url_pattern: str
    fetcher: Callable[[FreshConnectClient, str, date, date], Any]
    validator: Callable[[Any], BaseModel | list[BaseModel]]


def _build_registry() -> list[EndpointDef]:
    return [
        EndpointDef(
            name="restaurants",
            url_pattern="/Restaurants",
            fetcher=lambda c, _s, _d, _w: c.get("/Restaurants"),
            validator=lambda data: [RestaurantListItem.model_validate(x) for x in data],
        ),
        EndpointDef(
            name="daily_sales_summary",
            url_pattern="/DailySalesSummary/{stores}/startDate/{d}/endDate/{d}",
            fetcher=lambda c, s, d, _w: c.get_daily_sales_summary([s], d, d),
            validator=DailySalesSummaryResponse.model_validate,
        ),
        EndpointDef(
            name="sales_summary",
            url_pattern="/SalesSummary/{stores}/startDate/{d}/endDate/{d}",
            fetcher=lambda c, s, d, _w: c.get(
                f"/SalesSummary/{s}"
                f"/startDate/{d.isoformat()}/endDate/{d.isoformat()}"
            ),
            validator=SalesSummaryResponse.model_validate,
        ),
        EndpointDef(
            name="daily_timeclock",
            url_pattern="/DailyTimeclock/{stores}/startDate/{d}/endDate/{d}",
            fetcher=lambda c, s, d, _w: c.get_daily_timeclock([s], d, d),
            validator=DailyTimeclockResponse.model_validate,
        ),
        EndpointDef(
            name="inventory_movement",
            url_pattern="/InventoryMovement/{stores}/startDate/{d}/endDate/{d}",
            fetcher=lambda c, s, d, _w: c.get_inventory_movement([s], d, d),
            validator=InventoryMovementResponse.model_validate,
        ),
        EndpointDef(
            name="paid_outs_and_no_sales",
            url_pattern="/PaidOutsAndNoSales/{stores}/startDate/{d}/endDate/{d}",
            fetcher=lambda c, s, d, _w: c.get_paidouts_and_no_sales([s], d, d),
            validator=PaidOutsAndNoSalesResponse.model_validate,
        ),
        EndpointDef(
            name="third_party_daily_sales_summary",
            url_pattern="/ThirdPartyDailySalesSummary/{stores}/startDate/{d}/endDate/{d}",
            fetcher=lambda c, s, d, _w: c.get_third_party_daily([s], d, d),
            validator=ThirdPartyDailySalesSummaryResponse.model_validate,
        ),
        EndpointDef(
            name="third_party_sales_summary",
            url_pattern="/ThirdPartySalesSummary/{stores}/startDate/{d}/endDate/{d}",
            fetcher=lambda c, s, d, _w: c.get(
                f"/ThirdPartySalesSummary/{s}"
                f"/startDate/{d.isoformat()}/endDate/{d.isoformat()}"
            ),
            validator=ThirdPartySalesSummaryResponse.model_validate,
        ),
        EndpointDef(
            name="third_party_transaction_summary",
            url_pattern="/ThirdPartyTransactionSummary/{stores}/startDate/{d}/endDate/{d}",
            fetcher=lambda c, s, d, _w: c.get(
                f"/ThirdPartyTransactionSummary/{s}"
                f"/startDate/{d.isoformat()}/endDate/{d.isoformat()}"
            ),
            validator=ThirdPartyTransactionSummaryResponse.model_validate,
        ),
        EndpointDef(
            name="tips_details",
            url_pattern="/TipsDetails/{store}/startDate/{d}/endDate/{d}",
            fetcher=lambda c, s, d, _w: c.get_tips_details(s, d, d),
            validator=TipsDetailsResponse.model_validate,
        ),
        EndpointDef(
            name="transaction_summary",
            url_pattern="/TransactionSummary/{stores}/startDate/{d}/endDate/{d}",
            fetcher=lambda c, s, d, _w: c.get(
                f"/TransactionSummary/{s}"
                f"/startDate/{d.isoformat()}/endDate/{d.isoformat()}"
            ),
            validator=TransactionSummaryResponse.model_validate,
        ),
        EndpointDef(
            name="transaction_details",
            url_pattern="/TransactionDetails/{store}/startDate/{d}/endDate/{d}",
            fetcher=lambda c, s, d, _w: c.get_transaction_details(s, d, d),
            validator=TransactionDetailsResponse.model_validate,
        ),
        EndpointDef(
            name="waste_bread_credits",
            url_pattern="/WasteBreadCredits/{stores}/startDate/{d}/endDate/{d}",
            fetcher=lambda c, s, d, _w: c.get_waste_bread_credits([s], d, d),
            validator=WasteBreadCreditsResponse.model_validate,
        ),
        EndpointDef(
            name="wisr",
            url_pattern="/wisr/{stores}/{week_end}",
            fetcher=lambda c, s, _d, w: c.get_wisr([s], w),
            validator=WisrResponse.model_validate,
        ),
        EndpointDef(
            name="control_sheet",
            url_pattern="/controlsheet/{stores}/{week_end}",
            fetcher=lambda c, s, _d, w: c.get_control_sheet([s], w),
            validator=ControlSheetResponse.model_validate,
        ),
    ]


# ---------------------------------------------------------------------------
# Per-endpoint runner
# ---------------------------------------------------------------------------


@dataclass
class EndpointResult:
    name: str
    url_pattern: str
    success: bool
    raw_top_level_keys: list[str]
    parse_error: str | None
    http_status: int | None  # set when the HTTP call itself failed


def _run_endpoint(
    client: FreshConnectClient,
    ep: EndpointDef,
    store: str,
    day: date,
    week_end: date,
) -> EndpointResult:
    log.info(
        "discovery_endpoint_start",
        endpoint=ep.name,
        store=store,
        day=str(day),
        week_end=str(week_end),
    )

    raw = ep.fetcher(client, store, day, week_end)

    # Persist the raw JSON before doing anything else — even a failed parse
    # should leave a fixture on disk for later analysis.
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    (FIXTURES_DIR / f"{ep.name}.json").write_text(
        json.dumps(raw, indent=2, default=str), encoding="utf-8"
    )

    parse_error: str | None = None
    try:
        ep.validator(raw)
    except ValidationError as exc:
        parse_error = str(exc)

    return EndpointResult(
        name=ep.name,
        url_pattern=ep.url_pattern,
        success=parse_error is None,
        raw_top_level_keys=_top_level_keys(raw),
        parse_error=parse_error,
        http_status=None,
    )


def _top_level_keys(raw: Any) -> list[str]:
    if isinstance(raw, dict):
        return sorted(raw.keys())
    if isinstance(raw, list) and raw and isinstance(raw[0], dict):
        return sorted(raw[0].keys())
    return []


# ---------------------------------------------------------------------------
# Store picker
# ---------------------------------------------------------------------------


def _pick_store_from_db() -> str | None:
    """Return the first active store_number in ref_stores, or None on failure."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT store_number FROM ref_stores "
                    "WHERE is_active = true ORDER BY store_number LIMIT 1"
                )
            ).first()
        return None if row is None else str(row[0])
    except Exception as exc:  # diagnostics path
        log.warning("discovery_db_lookup_failed", error=str(exc))
        return None


# ---------------------------------------------------------------------------
# Coverage report
# ---------------------------------------------------------------------------


def _write_coverage_report(
    results: list[EndpointResult], store: str, day: date, week_end: date
) -> None:
    COVERAGE_DOC.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# FreshConnect API field coverage")
    lines.append("")
    lines.append(
        f"Generated by `scripts/discovery.py` on {date.today().isoformat()} "
        f"using store **{store}**, business date **{day.isoformat()}**, "
        f"weekEndDate **{week_end.isoformat()}**."
    )
    lines.append("")
    lines.append(
        "For each endpoint: the URL pattern, the top-level keys we saw, and "
        "whether the recorded fixture parsed cleanly against the Pydantic "
        "model in `subway_ops.freshconnect.models`. Any Pydantic validation "
        "error is shown verbatim so it can be reconciled by editing the "
        "relevant model."
    )
    lines.append("")

    ok_count = sum(1 for r in results if r.success)
    lines.append(
        f"**Result:** {ok_count} / {len(results)} endpoints parsed without error."
    )
    lines.append("")

    for r in results:
        lines.append(f"## {r.name}")
        lines.append("")
        lines.append(f"- URL pattern: `{r.url_pattern}`")
        lines.append(f"- Parse status: {'✅ parsed' if r.success else '❌ failed'}")
        if r.raw_top_level_keys:
            keys = ", ".join(f"`{k}`" for k in r.raw_top_level_keys)
            lines.append(f"- Top-level keys: {keys}")
        else:
            lines.append("- Top-level keys: _(empty or non-object response)_")
        if r.parse_error:
            lines.append("")
            lines.append("**Pydantic validation error:**")
            lines.append("")
            lines.append("```")
            lines.append(r.parse_error.strip())
            lines.append("```")
        lines.append("")

    COVERAGE_DOC.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--store",
        help="Restaurant number to query. Defaults to the first active store "
        "in ref_stores; falls back to failing fast if neither --store nor a "
        "DB connection is available.",
    )
    p.add_argument(
        "--no-db",
        action="store_true",
        help="Skip the DB lookup for picking a default store. --store becomes required.",
    )
    p.add_argument(
        "--sleep",
        type=float,
        default=SLEEP_BETWEEN_ENDPOINTS_S,
        help=f"Seconds to sleep between endpoints (default: {SLEEP_BETWEEN_ENDPOINTS_S}).",
    )
    p.add_argument(
        "--no-track",
        action="store_true",
        help="Skip recording this run in ops_job_runs (use when DB is unreachable).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    structlog.configure(processors=[structlog.dev.ConsoleRenderer()])

    store = args.store
    if not store and not args.no_db:
        store = _pick_store_from_db()
    if not store:
        sys.stderr.write(
            "No store specified and none discoverable from ref_stores. "
            "Re-run with --store <restaurant_number>.\n"
        )
        return 2

    today = business_date_now()
    yesterday = today - timedelta(days=1)
    _, prev_week_end = previous_business_week(today)

    log.info(
        "discovery_start",
        store=store,
        day=str(yesterday),
        week_end=str(prev_week_end),
    )

    registry = _build_registry()
    results: list[EndpointResult] = []

    def _run() -> None:
        with FreshConnectClient() as client:
            for i, ep in enumerate(registry):
                try:
                    res = _run_endpoint(client, ep, store, yesterday, prev_week_end)
                except RateLimitError:
                    completed = [r.name for r in results]
                    sys.stderr.write(
                        "Daily rate limit hit. Resume tomorrow after 17:00 PT "
                        "(00:00 UTC).\n"
                    )
                    sys.stderr.write(f"Endpoints completed: {completed}\n")
                    sys.stderr.write(
                        f"Endpoint that hit the limit: {ep.name}. "
                        f"Remaining: {[e.name for e in registry[i + 1 :]]}\n"
                    )
                    raise
                results.append(res)
                if res.success:
                    log.info("discovery_endpoint_ok", endpoint=ep.name)
                else:
                    log.warning(
                        "discovery_endpoint_parse_failed",
                        endpoint=ep.name,
                        first_error=(res.parse_error or "")[:200],
                    )
                if i < len(registry) - 1:
                    time.sleep(args.sleep)

    if args.no_track:
        _run()
    else:
        with track_job("discovery") as meta:
            meta["store"] = store
            meta["day"] = yesterday.isoformat()
            meta["week_end"] = prev_week_end.isoformat()
            _run()
            meta["endpoints_completed"] = [r.name for r in results]
            meta["parse_failures"] = [r.name for r in results if not r.success]
            meta["rows_written"] = len(results)

    _write_coverage_report(results, store, yesterday, prev_week_end)

    ok = sum(1 for r in results if r.success)
    print(
        f"Discovery complete: {ok}/{len(results)} endpoints parsed. "
        f"Fixtures in {FIXTURES_DIR.relative_to(REPO_ROOT)}; "
        f"report in {COVERAGE_DOC.relative_to(REPO_ROOT)}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
