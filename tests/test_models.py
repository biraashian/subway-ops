"""Parser smoke tests for every FreshConnect response model.

Each test feeds the model the JSON sample from the FreshConnect API
documentation PDFs (docs/freshconnect/APIUrlsDocumentation.pdf) and
asserts that parsing succeeds and key fields land correctly. Task 1.3
will replace these inline samples with recorded live fixtures.
"""

from __future__ import annotations

from decimal import Decimal

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

# ---------------------------------------------------------------------------
# Restaurants
# ---------------------------------------------------------------------------


def test_restaurants_parses_doc_sample() -> None:
    items = [
        RestaurantListItem.model_validate(x)
        for x in [
            {"restaurantNumber": "111111"},
            {"restaurantNumber": "222222"},
            {"restaurantNumber": "333333"},
        ]
    ]
    assert [i.restaurant_number for i in items] == ["111111", "222222", "333333"]


def test_restaurants_accepts_typo_alias() -> None:
    """Some sample payloads use the misspelled key 'resturantNumber'."""
    item = RestaurantListItem.model_validate({"resturantNumber": "44444"})
    assert item.restaurant_number == "44444"


# ---------------------------------------------------------------------------
# DailySalesSummary
# ---------------------------------------------------------------------------


def test_daily_sales_summary_parses_doc_sample() -> None:
    payload = {
        "startDate": "2024-01-01T00:00:00",
        "endDate": "2024-01-02T00:00:00",
        "data": [
            {
                "date": "2024-01-01T00:00:00",
                "restaurantNumber": "11111",
                "netSales": 67.71,
                "tax": 16.49,
                "units": 7,
                "transactions": 5,
                "cashCardTotal": 0,
                "thirdPartySales": 67.71,
                "thirdPartyTransactions": 5,
                "hoursWorked": 53.82,
            },
            {
                "date": "2024-01-02T00:00:00",
                "restaurantNumber": "22222",
                "netSales": 98.46,
                "tax": 30.83,
                "units": 15,
                "transactions": 9,
                "cashCardTotal": 0,
                "thirdPartySales": 111.4,
                "thirdPartyTransactions": 10,
                "hoursWorked": 33.28,
            },
        ],
    }
    resp = DailySalesSummaryResponse.model_validate(payload)
    assert len(resp.data) == 2
    assert resp.data[0].net_sales == Decimal("67.71")
    assert resp.data[1].restaurant_number == "22222"
    assert resp.data[1].third_party_transactions == 10


# ---------------------------------------------------------------------------
# SalesSummary
# ---------------------------------------------------------------------------


def test_sales_summary_parses_doc_sample() -> None:
    payload = {
        "startDate": "2024-01-01T00:00:00",
        "endDate": "2024-01-04T00:00:00",
        "data": [
            {
                "restaurantNumber": "11111",
                "netSales": 790.9,
                "tax": 217.03,
                "units": 89,
                "transactions": 55,
                "cashCardTotal": 0,
                "thirdPartySales": 571.39,
                "thirdPartyTransactions": 43,
                "hoursWorked": 214.46,
            }
        ],
    }
    resp = SalesSummaryResponse.model_validate(payload)
    assert resp.data[0].hours_worked == Decimal("214.46")


# ---------------------------------------------------------------------------
# DailyTimeclock
# ---------------------------------------------------------------------------


def test_daily_timeclock_parses_doc_sample() -> None:
    payload = {
        "startDate": "2024-08-13T12:50:12.465Z",
        "endDate": "2024-08-13T12:50:12.465Z",
        "data": [
            {
                "restaurantNumber": "11111",
                "clerkId": "131",
                "employeeName": "John Smith",
                "clockIn": "2024-08-13T08:00:00",
                "clockOut": "2024-08-13T16:15:00",
                "hoursBeforeAdj": 8.25,
                "hoursAfterAdj": 8.25,
                "adjAmount": 0,
            }
        ],
    }
    resp = DailyTimeclockResponse.model_validate(payload)
    assert resp.data[0].clerk_id == "131"


# ---------------------------------------------------------------------------
# InventoryMovement
# ---------------------------------------------------------------------------


def test_inventory_movement_parses_doc_sample() -> None:
    payload = {
        "startDate": "2024-01-01T00:00:00",
        "endDate": "2024-01-04T00:00:00",
        "data": [
            {
                "store": "11111",
                "date": "2024-01-01T00:00:00",
                "totals": [
                    {"name": "UNITS COST", "totalCost": 1963.76, "wasteValue": 65.88}
                ],
                "items": [
                    {
                        "item": "Bread",
                        "inventoryItem": "Bread, White, 80/1",
                        "unitOfMeasure": "each",
                        "unitCost": 10.23,
                        "delivery": 10.0,
                        "transfer": 12.0,
                        "totalCost": 234.12,
                        "waste": 1.0,
                        "wasteValue": 10.23,
                    }
                ],
            }
        ],
    }
    resp = InventoryMovementResponse.model_validate(payload)
    day = resp.data[0]
    assert day.store == "11111"
    assert day.totals[0].name == "UNITS COST"
    assert day.items[0].unit_of_measure == "each"


# ---------------------------------------------------------------------------
# PaidOutsAndNoSales
# ---------------------------------------------------------------------------


def test_paid_outs_and_no_sales_parses_doc_sample() -> None:
    payload = {
        "startDate": "2026-01-01T00:00:00",
        "endDate": "2026-01-02T00:00:00",
        "data": {
            "noSales": [
                {
                    "restaurantNumber": "11111",
                    "time": "2026-01-01T17:03:06.3",
                    "clerkId": "131",
                    "clerkName": "John, Smith",
                    "noSaleType": "cash in",
                    "reasonType": "",
                    "reason": "",
                },
                {
                    "restaurantNumber": "22222",
                    "time": "2026-01-01T17:00:44.447",
                    "clerkId": "131",
                    "clerkName": "John, Smith",
                    "noSaleType": "no sale",
                    "reasonType": "Custom",
                    "reason": "Wrong change given to customer",
                },
            ],
            "paidOuts": [
                {
                    "restaurantNumber": "11111",
                    "time": "2026-01-01T12:22:12.057",
                    "clerkId": "6008",
                    "clerkName": "John, Smith",
                    "amount": 4.29,
                    "reason": "Tips",
                    "comment": "01/01",
                }
            ],
        },
    }
    resp = PaidOutsAndNoSalesResponse.model_validate(payload)
    assert len(resp.data.no_sales) == 2
    assert resp.data.paid_outs[0].amount == Decimal("4.29")


# ---------------------------------------------------------------------------
# ThirdPartyDailySalesSummary
# ---------------------------------------------------------------------------


def test_third_party_daily_sales_summary_parses_doc_sample() -> None:
    payload = {
        "startDate": "2024-01-01T00:00:00",
        "endDate": "2024-01-02T00:00:00",
        "data": [
            {
                "date": "2024-01-01T00:00:00",
                "restaurantNumber": "11111",
                "totalSales": 500.00,
                "totalNetSales": 450.00,
                "totalTransactions": 78,
                "providers": [
                    {
                        "provider": "DoorDash",
                        "transactions": 11,
                        "netSales": 23.4,
                        "sales": 34.3,
                    },
                    {
                        "provider": "UberEats",
                        "transactions": 16,
                        "netSales": 25.4,
                        "sales": 38.3,
                    },
                ],
            }
        ],
    }
    resp = ThirdPartyDailySalesSummaryResponse.model_validate(payload)
    assert resp.data[0].total_sales == Decimal("500.00")
    assert resp.data[0].providers[1].provider == "UberEats"


# ---------------------------------------------------------------------------
# ThirdPartySalesSummary
# ---------------------------------------------------------------------------


def test_third_party_sales_summary_parses_doc_sample() -> None:
    payload = {
        "startDate": "2024-01-01T00:00:00",
        "endDate": "2024-01-02T00:00:00",
        "data": [
            {
                "restaurantNumber": "11111",
                "totalSales": 345.34,
                "totalNetSales": 324.54,
                "totalTransactions": 78,
                "providers": [
                    {
                        "provider": "DoorDash",
                        "transactions": 11,
                        "netSales": 23.4,
                        "sales": 34.3,
                    }
                ],
            }
        ],
    }
    resp = ThirdPartySalesSummaryResponse.model_validate(payload)
    assert resp.data[0].total_transactions == 78


# ---------------------------------------------------------------------------
# ThirdPartyTransactionSummary
# ---------------------------------------------------------------------------


def test_third_party_transaction_summary_parses_doc_sample() -> None:
    payload = {
        "startDate": "2024-01-01T00:00:00",
        "endDate": "2024-01-02T00:00:00",
        "data": [
            {
                "restaurantNumber": "11111",
                "date": "2024-01-01T00:00:00",
                "time": "2024-01-01T12:23:27",
                "receiptNumber": 1,
                "total": 2.81,
                "netTotal": 2.69,
                "tax": 0.12,
                "taxInclusiveAmount": 0,
                "channel": "uber",
                "type": "Sale",
            },
            {
                "restaurantNumber": "11111",
                "date": "2024-01-01T00:00:00",
                "time": "2024-01-01T12:25:12",
                "receiptNumber": 2,
                "total": 1.81,
                "netTotal": 1.69,
                "tax": 1.12,
                "taxInclusiveAmount": 0,
                "channel": "uber",
                "type": "Refund",
            },
        ],
    }
    resp = ThirdPartyTransactionSummaryResponse.model_validate(payload)
    assert resp.data[1].type == "Refund"


# ---------------------------------------------------------------------------
# TipsDetails
# ---------------------------------------------------------------------------


def test_tips_details_parses_doc_sample() -> None:
    payload = {
        "startDate": "2025-01-01T00:00:00",
        "endDate": "2025-01-02T00:00:00",
        "data": [
            {
                "restaurantNumber": "11111",
                "date": "2025-01-02T00:00:00",
                "time": "2025-01-02T17:20:41",
                "receiptNumber": 0,
                "netTotal": 1.59,
                "total": 1.78,
                "tax": 0.19,
                "tip": 0.51,
                "employeeSplitTip": 0.17,
                "channel": "Channel",
                "amountTendered": 1.78,
                "employeesAtTimeOfTip": [
                    {"clerkId": "1", "employeeName": "Jim Jimson"},
                    {"clerkId": "3", "employeeName": "Tom Tomson"},
                    {"clerkId": "4", "employeeName": "Don Donson"},
                ],
            }
        ],
    }
    resp = TipsDetailsResponse.model_validate(payload)
    row = resp.data[0]
    assert row.tip == Decimal("0.51")
    assert len(row.employees_at_time_of_tip) == 3
    assert row.employees_at_time_of_tip[2].employee_name == "Don Donson"


# ---------------------------------------------------------------------------
# TransactionSummary
# ---------------------------------------------------------------------------


def test_transaction_summary_parses_doc_sample() -> None:
    payload = {
        "startDate": "2024-01-01T00:00:00",
        "endDate": "2024-01-01T00:00:00",
        "data": [
            {
                "restaurantNumber": "11111",
                "date": "2024-01-01T00:00:00",
                "time": "2024-01-01T12:23:27",
                "type": "Sale",
                "receiptNumber": 1,
                "channel": "uber",
                "saleType": "DriveThru",
                "clerkId": "808192673",
                "clerkName": "John Smith",
                "total": 2.81,
                "netTotal": 2.69,
                "tax": 0.12,
                "taxInclusiveAmount": 0,
                "taxableAmount": 2.69,
                "units": 1,
                "orderSource": "Subway POS",
                "deliveryProvider": "",
                "deliveryPartner": "",
            },
            {
                "restaurantNumber": "11111",
                "date": "2024-01-01T00:00:00",
                "time": "2024-01-01T15:31:14",
                "type": "Void",
                "receiptNumber": 4,
                "channel": "Grubhub",
                "saleType": "EatIn",
                "clerkId": "546395952",
                "clerkName": "John Smith",
                "total": -4.47,
                "netTotal": -4.19,
                "tax": -0.28,
                "taxInclusiveAmount": 0,
                "taxableAmount": -4.19,
                "units": -1,
                "orderSource": "Subway POS",
                "deliveryProvider": "Grubhub",
                "deliveryPartner": "",
            },
        ],
    }
    resp = TransactionSummaryResponse.model_validate(payload)
    assert resp.data[1].units == -1
    assert resp.data[1].total == Decimal("-4.47")


# ---------------------------------------------------------------------------
# TransactionDetails
# ---------------------------------------------------------------------------


def test_transaction_details_parses_doc_sample() -> None:
    payload = {
        "startDate": "2024-06-02T00:00:00",
        "endDate": "2024-06-02T00:00:00",
        "data": [
            {
                "restaurantNumber": "11111",
                "date": "2024-06-02T00:00:00",
                "time": "2024-06-02T00:22:34.153",
                "type": "Sale",
                "receiptNumber": 718875,
                "channel": "Technology Pavilion",
                "saleType": "DriveThru",
                "clerkId": "1635",
                "clerkName": "John Smith",
                "total": 17.93,
                "netTotal": 16.98,
                "tax": 0.95,
                "taxInclusiveAmount": 0.0,
                "taxableAmount": 16.98,
                "units": 1,
                "orderSource": "Drive Thru",
                "deliveryProvider": "",
                "deliveryPartner": "",
                "items": [
                    {
                        "description": "Ham FtLong",
                        "category": "FootLong",
                        "department": "Footlong Sub",
                        "originalPrice": 11.89,
                        "adjustedPrice": 11.89,
                        "tax": 0.5945,
                        "taxInclusiveAmount": 0.0,
                        "quantity": 1,
                        "priceOverride": False,
                        "discountCode": "",
                        "discount": "",
                        "plu": "111000004",
                        "type": "Sale",
                    }
                ],
                "tenders": [
                    {
                        "description": "DebitCard",
                        "amount": 17.93,
                        "changeAmount": 0.0,
                        "tipAmount": 0.0,
                        "referenceNumber": "34543gYr34tRG34",
                        "cardLastFour": "4316",
                    }
                ],
                "loyalty": [
                    {
                        "basePointsEarned": 24,
                        "bonusPointsEarned": 0,
                        "baseMoneyEarned": 0.24,
                        "bonusMoneyEarned": 0.0,
                        "pointsConverted": 93,
                        "rewardMoneyRedeemed": 2.5,
                        "memberType": "MobileApp",
                        "providerType": "Simplicity",
                    }
                ],
                "taxes": [
                    {"description": "Goods and Services T", "amount": 0.85},
                    {"description": "Bottle Deposit", "amount": 0.1},
                ],
                "discounts": [],
                "nonSubwayItems": [
                    {
                        "description": "door dash dasher tip",
                        "category": "Door Dash",
                        "department": "NonSubway",
                        "originalPrice": 2.99,
                        "adjustedPrice": 2.99,
                        "tax": 0,
                        "taxInclusiveAmount": 0,
                        "quantity": 2,
                        "priceOverride": False,
                        "discountCode": "",
                        "discount": "",
                        "plu": "123456789",
                        "type": "Sale",
                    }
                ],
            },
            {
                "restaurantNumber": "11111",
                "date": "2024-06-02T00:00:00",
                "time": "2024-06-02T01:21:21.757",
                "type": "Sale",
                "receiptNumber": 718877,
                "channel": "Technology Pavilion",
                "saleType": "DriveThru",
                "clerkId": "1635",
                "clerkName": "John Smith",
                "total": 27.92,
                "netTotal": 26.5,
                "tax": 1.42,
                "taxInclusiveAmount": 0.0,
                "taxableAmount": 26.5,
                "units": 2,
                "orderSource": "Drive Thru",
                "deliveryProvider": "",
                "deliveryPartner": "",
                "items": [],
                "tenders": [],
                "loyalty": [],
                "taxes": [],
                "discounts": [
                    {
                        "description": "CAN - Fresh Value Meal",
                        "quantity": 1,
                        "wholeOrderDiscountValue": 0.0,
                        "isWholeOrderDiscount": False,
                        "wholeOrderDiscountType": "",
                    }
                ],
                "nonSubwayItems": [],
            },
        ],
    }
    resp = TransactionDetailsResponse.model_validate(payload)
    row0 = resp.data[0]
    assert row0.items[0].plu == "111000004"
    assert row0.tenders[0].card_last_four == "4316"
    assert row0.loyalty[0].member_type == "MobileApp"
    assert row0.non_subway_items[0].category == "Door Dash"
    assert resp.data[1].discounts[0].is_whole_order_discount is False


# ---------------------------------------------------------------------------
# WasteBreadCredits
# ---------------------------------------------------------------------------


def test_waste_bread_credits_parses_doc_sample() -> None:
    payload = {
        "startDate": "2024-01-01T00:00:00",
        "endDate": "2024-01-04T00:00:00",
        "data": {
            "waste": [
                {
                    "resturantNumber": "11111",
                    "time": "2024-01-01T10:30:00",
                    "clerkId": "1635",
                    "clerkName": "John Smith",
                    "receiptNumber": "4534534",
                    "item": "Chips",
                    "quantity": 2,
                    "itemPrice": 1.2,
                    "totalPrice": 2.4,
                    "reason": "Dropped",
                }
            ],
            "breadCredit": [
                {
                    "resturantNumber": "11111",
                    "time": "2024-01-01T10:35:00",
                    "clerkId": "1635",
                    "clerkName": "John Smith",
                    "receiptNumber": "453452",
                    "item": "Plain 6 inch",
                    "quantity": 1,
                    "itemPrice": 2.0,
                    "totalPrice": 2.0,
                    "reason": "Stale",
                }
            ],
        },
    }
    resp = WasteBreadCreditsResponse.model_validate(payload)
    assert resp.data.waste[0].restaurant_number == "11111"
    assert resp.data.bread_credit[0].reason == "Stale"


# ---------------------------------------------------------------------------
# Wisr
# ---------------------------------------------------------------------------


_WISR_QVP_EMPTY = {"quantity": 0, "value": 0, "percentage": 0}


def _make_inv_cat() -> dict[str, float]:
    return {
        "valueUsed": 0,
        "valueDiff": 0,
        "actualPercentage": 0,
        "expectedPercentage": 0,
        "percentageDiff": 0,
    }


def _make_value_pct() -> dict[str, float]:
    return {"value": 0, "percentage": 0}


def _make_quantity_pct() -> dict[str, float]:
    return {"quantity": 0, "percentage": 0}


def _make_quantity_value() -> dict[str, float]:
    return {"quantity": 0, "value": 0}


def _make_dist_cost() -> dict[str, float]:
    return {"valueUsed": 0, "actualPercent": 0}


def test_wisr_parses_doc_sample() -> None:
    payload = {
        "weekEndDate": "2025-04-15T00:00:00",
        "data": [
            {
                "restaurantNumber": "111111",
                "totalInventoryValue": 2026.1329,
                "adjustedCostOfGoods": {
                    "freeUnits": {
                        "quantity": 6.0,
                        "value": 33.96,
                        "percentage": 5.066,
                    },
                    "employeeFree": _WISR_QVP_EMPTY,
                    "employeeDiscounts": _WISR_QVP_EMPTY,
                    "otherDiscountValue": _WISR_QVP_EMPTY,
                    "fvmDiscountsValue": _WISR_QVP_EMPTY,
                    "miscAndDrinkDiscValue": _WISR_QVP_EMPTY,
                    "totalDiscountValue": _WISR_QVP_EMPTY,
                    "discountValuePctOfSales": {
                        "quantity": None,
                        "value": None,
                        "percentage": 7.9422,
                    },
                    "adjustedCostOfGoods": {
                        "quantity": None,
                        "value": None,
                        "percentage": 25.2293,
                    },
                },
                "inventoryCategoriesSummary": {
                    "cheese": _make_inv_cat(),
                    "meatProtein": _make_inv_cat(),
                    "breadCarrier": _make_inv_cat(),
                    "veggies": _make_inv_cat(),
                    "toppings": _make_inv_cat(),
                    "papergoods": _make_inv_cat(),
                    "unitsCost": _make_inv_cat(),
                    "drinksCost": _make_inv_cat(),
                    "miscCost": _make_inv_cat(),
                    "costOfGoods": _make_inv_cat(),
                    "distributionCost": {
                        "valueUsed": -53.7036,
                        "valueDiff": None,
                        "actualPercentage": -0.6363,
                        "expectedPercentage": None,
                        "percentageDiff": None,
                    },
                },
                "salesSummaryItems": {
                    "unitSales": _make_value_pct(),
                    "cateringSales": _make_value_pct(),
                    "drinkSales": _make_value_pct(),
                    "miscSales": _make_value_pct(),
                    "netSubwaySales": _make_value_pct(),
                    "gas": _make_value_pct(),
                    "electric": _make_value_pct(),
                    "telephone": _make_value_pct(),
                    "garbage": _make_value_pct(),
                    "insurance": _make_value_pct(),
                    "rent": _make_value_pct(),
                    "laundry": _make_value_pct(),
                    "misc": _make_value_pct(),
                    "repairMaintenance": _make_value_pct(),
                    "operatingExpenses": _make_value_pct(),
                    "laborAndTaxes": _make_value_pct(),
                    "costOfGoods": _make_value_pct(),
                    "royalty": _make_value_pct(),
                    "faf": _make_value_pct(),
                    "localAdvertising": _make_value_pct(),
                    "totalExpenses": _make_value_pct(),
                    "balance": _make_value_pct(),
                    "financialStrength": {"value": 48.0, "percentage": None},
                    "loans": _make_value_pct(),
                },
                "unitsSummaryItems": {
                    "footlong": _make_quantity_pct(),
                    "sixInch": _make_quantity_pct(),
                    "threeInchAndMuffin": _make_quantity_pct(),
                    "salads": _make_quantity_pct(),
                    "pizza": _make_quantity_pct(),
                    "otherUnits": _make_quantity_pct(),
                    "totalUnits": _make_quantity_pct(),
                    "drinks": _make_quantity_pct(),
                },
                "cateringSummaryItems": {
                    "giantSubs": _make_quantity_value(),
                    "sandwichPlatters": _make_quantity_value(),
                    "boxedMeals": _make_quantity_value(),
                    "dessertPlatters": _make_quantity_value(),
                },
                "distributionCosts": {
                    "deliveryFee": _make_dist_cost(),
                    "distributorCredits": _make_dist_cost(),
                    "annualIpcPatronage": _make_dist_cost(),
                    "distributionCosts": _make_dist_cost(),
                },
                "customerCount": 662.0,
                "unitsPerCustomer": 1.2598,
                "factor": 8.3882,
                "averageTicket": 12.7498,
                "inventoryItems": [
                    {
                        "name": "Cheese, Sliced cheese",
                        "open": 38.0,
                        "delivered": 38.0,
                        "left": 30.0,
                        "used": 46.0,
                        "posDifference": 4.6744,
                        "recordedWaste": 0.0,
                        "cost": 2.8097,
                        "valueUsed": 129.2458,
                        "valueDifference": 13.1336,
                        "actualPercentage": 1.8475,
                        "expectedPercentage": 2.0352,
                        "diffPercentage": 0.1877,
                    },
                    {
                        "name": "Other NCOG Drinks Summary",
                        "open": None,
                        "delivered": None,
                        "left": None,
                        "used": None,
                        "posDifference": None,
                        "recordedWaste": None,
                        "cost": None,
                        "valueUsed": 0.0,
                        "valueDifference": 0.0,
                        "actualPercentage": 0.0,
                        "expectedPercentage": 0.0,
                        "diffPercentage": 0.0,
                    },
                ],
                "cashBreadOverShortTotals": {
                    "cashDailyFigures": {
                        "wednesday": -0.15,
                        "thursday": 6.6,
                        "friday": -6.52,
                        "saturday": -0.2,
                        "sunday": -0.33,
                        "monday": -0.1,
                        "tuesday": -0.04,
                        "total": -0.74,
                    },
                    "breadDailyFigures": {
                        "wednesday": -0.67,
                        "thursday": -0.67,
                        "friday": -0.83,
                        "saturday": 0.5,
                        "sunday": -0.5,
                        "monday": -0.67,
                        "tuesday": 0.0,
                        "total": -2.84,
                    },
                },
            }
        ],
    }
    resp = WisrResponse.model_validate(payload)
    row = resp.data[0]
    assert row.restaurant_number == "111111"
    assert row.total_inventory_value == Decimal("2026.1329")
    assert row.adjusted_cost_of_goods.free_units.value == Decimal("33.96")
    assert row.inventory_items[1].open is None
    assert row.cash_bread_over_short_totals.cash_daily_figures.total == Decimal("-0.74")


# ---------------------------------------------------------------------------
# ControlSheet
# ---------------------------------------------------------------------------


def _dow(total: float | None = 0.0) -> dict[str, float | None]:
    return {
        "wed": 0,
        "thu": 0,
        "fri": 0,
        "sat": 0,
        "sun": 0,
        "mon": 0,
        "tue": 0,
        "total": total,
    }


def _dow_avg(average: float = 0.0) -> dict[str, float]:
    return {
        "wed": 0,
        "thu": 0,
        "fri": 0,
        "sat": 0,
        "sun": 0,
        "mon": 0,
        "tue": 0,
        "average": average,
    }


def _dow_pct(total: float | None = 0.0, percentage: float | None = None) -> dict[str, float | None]:
    base = _dow(total)
    if percentage is not None:
        base["percentage"] = percentage
    return base


def test_control_sheet_parses_doc_sample() -> None:
    cash_keys = [
        "closingGrandTotal", "openingGrandTotal", "adjustments", "adjustedProceeds",
        "openingCash", "paidouts", "creditSales", "requiredCash", "actualCash",
        "overShort", "closingKeep", "depositInBank", "cashcards", "debit",
        "visaAndMastercard", "discover", "americanExpress", "cateringCallCenter",
        "other", "payPal", "cashRoundingAdjustment",
    ]
    bread_keys = [
        "opening", "delivered", "credits", "left", "used", "sold", "overShort",
        "breadLeft", "breadOverShort", "flatbreadLeft", "flatbreadOverShort",
        "saladLeft", "saladOverShort", "muffinLeft", "muffinOverShort",
        "pizzaLeft", "pizzaOverShort", "otherLeft", "otherOverShort",
    ]
    sales_keys = [
        "totalSubwaySales", "footlong", "sixInch", "threeInch", "muffinMelt",
        "salad", "pizza", "otherCarrier", "addOn", "catering",
        "unitCouponsDiscounts", "unitRefunds", "unitVoids", "totalUnitsSales",
        "fountain", "bottledBeverage", "hotBeverage", "otherBeverage",
        "drinksCouponsDiscounts", "drinksRefunds", "drinksVoids", "totalDrinksSales",
        "chips", "cookies", "soups", "otherMisc", "miscCouponsDiscounts",
        "miscRefunds", "miscVoids", "totalMiscSales", "cashCardSales",
        "adjSalesTaxAndFees", "taxAndFeeAdjustments", "adjOtherReceipts",
        "adjCoBrandSales", "otherAdjustments",
    ]
    unit_keys = [
        "footlong", "sixInch", "threeInch", "muffinMelt", "salad", "pizza",
        "otherCarrier", "catering", "employeeAndFreeUnits", "totalUnits",
        "allUnitsSold", "drink", "drinkPercentage",
    ]

    payload = {
        "weekEndDate": "2025-04-14T00:00:00",
        "data": [
            {
                "summary": {
                    "weekEndDate": "2025-04-15T00:00:00",
                    "storeNumber": "25785",
                    "costOfGoodPercentage": -0.2196,
                    "costOfUnitsPercentage": -0.2619,
                    "drinkCostPercentage": -1.2532,
                    "adjustedCostOfGoodsPercentage": -0.1914,
                    "adjustedCostOfUnitsPercentage": -0.2297,
                    "miscCostPercentage": -1.2532,
                    "productivity": 5.86,
                    "factor": 8.9491,
                    "customerCount": 376,
                    "netSales": 5705.48,
                },
                "cashControl": {k: _dow() for k in cash_keys},
                "bread": {k: _dow() for k in bread_keys},
                "labor": {
                    "hoursOpen": _dow(total=89),
                    "hoursWorked": _dow(total=93.75),
                    "productivity": _dow_avg(average=5.86),
                    "salesPerLaborHour": _dow_avg(average=60.86),
                },
                "metrics": {
                    "factor": _dow_avg(average=8.9491),
                    "customerCount": _dow(total=376),
                    "averageTicket": _dow_avg(average=15.17),
                },
                "salesItemization": {k: _dow_pct(total=0, percentage=0) for k in sales_keys},
                "unitItemization": {k: _dow_pct(total=0, percentage=0) for k in unit_keys},
            }
        ],
    }
    # totalSubwaySales does not include a percentage in the doc sample —
    # remove it to keep extra="forbid" happy as the API would.
    del payload["data"][0]["salesItemization"]["totalSubwaySales"]["percentage"]
    del payload["data"][0]["salesItemization"]["cashCardSales"]["percentage"]
    del payload["data"][0]["salesItemization"]["adjSalesTaxAndFees"]["percentage"]
    del payload["data"][0]["salesItemization"]["adjOtherReceipts"]["percentage"]
    del payload["data"][0]["salesItemization"]["adjCoBrandSales"]["percentage"]
    del payload["data"][0]["unitItemization"]["totalUnits"]["percentage"]
    del payload["data"][0]["unitItemization"]["allUnitsSold"]["percentage"]
    del payload["data"][0]["unitItemization"]["drink"]["percentage"]

    resp = ControlSheetResponse.model_validate(payload)
    row = resp.data[0]
    assert row.summary.store_number == "25785"
    assert row.summary.customer_count == 376
    assert row.labor.hours_open.total == Decimal("89")
    assert row.labor.productivity.average == Decimal("5.86")
    assert row.cash_control.closing_grand_total.wed == Decimal("0")
    assert row.unit_itemization.drink_percentage.percentage == Decimal("0")
