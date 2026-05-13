"""Parse every recorded FreshConnect fixture against its Pydantic model.

These tests run if and only if ``tests/fixtures/recorded/`` exists locally
(gitignored — populated by ``scripts/discovery.py``). They give the operator
a quick way to verify that the live API still matches the models without
re-running the discovery script.

In CI / fresh checkouts the fixtures directory is empty and every test is
skipped.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

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

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "recorded"

# Each entry: (fixture filename, callable that parses the raw JSON).
# Keep this list in sync with ``scripts/discovery.py``'s registry.
_PARSERS: list[tuple[str, Callable[[Any], BaseModel | list[BaseModel]]]] = [
    ("restaurants.json", lambda d: [RestaurantListItem.model_validate(x) for x in d]),
    ("daily_sales_summary.json", DailySalesSummaryResponse.model_validate),
    ("sales_summary.json", SalesSummaryResponse.model_validate),
    ("daily_timeclock.json", DailyTimeclockResponse.model_validate),
    ("inventory_movement.json", InventoryMovementResponse.model_validate),
    ("paid_outs_and_no_sales.json", PaidOutsAndNoSalesResponse.model_validate),
    ("third_party_daily_sales_summary.json", ThirdPartyDailySalesSummaryResponse.model_validate),
    ("third_party_sales_summary.json", ThirdPartySalesSummaryResponse.model_validate),
    ("third_party_transaction_summary.json", ThirdPartyTransactionSummaryResponse.model_validate),
    ("tips_details.json", TipsDetailsResponse.model_validate),
    ("transaction_summary.json", TransactionSummaryResponse.model_validate),
    ("transaction_details.json", TransactionDetailsResponse.model_validate),
    ("waste_bread_credits.json", WasteBreadCreditsResponse.model_validate),
    ("wisr.json", WisrResponse.model_validate),
    ("control_sheet.json", ControlSheetResponse.model_validate),
]


@pytest.mark.parametrize(("filename", "parser"), _PARSERS, ids=[p[0] for p in _PARSERS])
def test_recorded_fixture_parses(
    filename: str, parser: Callable[[Any], BaseModel | list[BaseModel]]
) -> None:
    path = FIXTURES_DIR / filename
    if not path.exists():
        pytest.skip(f"No recorded fixture at {path} — run scripts/discovery.py to populate")

    raw = json.loads(path.read_text(encoding="utf-8"))
    parser(raw)  # raises ValidationError on schema drift
