"""Pydantic v2 models for every FreshConnect endpoint response.

Conventions:
- Every model uses ``ConfigDict(populate_by_name=True, extra="forbid")``.
  Unknown fields fail loudly so schema drift surfaces immediately.
- Python field names are snake_case; the API's camelCase keys are mapped
  through ``Field(alias=...)`` or ``AliasChoices`` (used for the known
  ``restaurantNumber`` / ``resturantNumber`` typo).
- Money fields use ``Decimal``. Floats are never used for currency.
- Datetimes use ``datetime``. The API emits ISO-8601 strings without a
  timezone (e.g. ``"2025-04-15T00:00:00"``); we treat them as naive at the
  model layer and the storage layer attaches America/Los_Angeles.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

# Type aliases — kept as plain assignments (not PEP-695 `type` statements)
# because Pydantic resolves the annotation directly to ``Decimal`` for
# validation. ``Money`` and ``Percentage`` exist for readability only.
Money = Decimal
Percentage = Decimal

_RESTAURANT_NUMBER_ALIASES = AliasChoices("restaurantNumber", "resturantNumber")


class _FCModel(BaseModel):
    """Base for every FreshConnect model — strict, alias-aware."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


# ---------------------------------------------------------------------------
# Shared / repeating shapes
# ---------------------------------------------------------------------------


class DaysOfWeek(_FCModel):
    """``{wed, thu, fri, sat, sun, mon, tue, ...}`` sub-object.

    Different ControlSheet sections include different "footer" keys:
    - cash/bread/sales sections use ``total``;
    - labor and rate metrics use ``average``;
    - itemized sales/units sections also include ``percentage``.

    Every footer key is optional, so a single model covers all variants.
    """

    wed: Decimal | None = None
    thu: Decimal | None = None
    fri: Decimal | None = None
    sat: Decimal | None = None
    sun: Decimal | None = None
    mon: Decimal | None = None
    tue: Decimal | None = None
    total: Decimal | None = None
    average: Decimal | None = None
    percentage: Percentage | None = None


class DaysOfWeekLong(_FCModel):
    """Long-day-name variant used by Wisr's ``cashBreadOverShortTotals``."""

    wednesday: Decimal | None = None
    thursday: Decimal | None = None
    friday: Decimal | None = None
    saturday: Decimal | None = None
    sunday: Decimal | None = None
    monday: Decimal | None = None
    tuesday: Decimal | None = None
    total: Decimal | None = None


# ---------------------------------------------------------------------------
# Restaurants
# ---------------------------------------------------------------------------


class RestaurantListItem(_FCModel):
    restaurant_number: str = Field(validation_alias=_RESTAURANT_NUMBER_ALIASES)


# ---------------------------------------------------------------------------
# DailySalesSummary
# ---------------------------------------------------------------------------


class DailySalesRow(_FCModel):
    date: datetime
    restaurant_number: str = Field(validation_alias=_RESTAURANT_NUMBER_ALIASES)
    net_sales: Money = Field(alias="netSales")
    tax: Money
    units: int
    transactions: int
    cash_card_total: Money = Field(alias="cashCardTotal")
    third_party_sales: Money = Field(alias="thirdPartySales")
    third_party_transactions: int = Field(alias="thirdPartyTransactions")
    hours_worked: Decimal = Field(alias="hoursWorked")


class DailySalesSummaryResponse(_FCModel):
    start_date: datetime = Field(alias="startDate")
    end_date: datetime = Field(alias="endDate")
    data: list[DailySalesRow]


# ---------------------------------------------------------------------------
# SalesSummary
# ---------------------------------------------------------------------------


class SalesSummaryRow(_FCModel):
    restaurant_number: str = Field(validation_alias=_RESTAURANT_NUMBER_ALIASES)
    net_sales: Money = Field(alias="netSales")
    tax: Money
    units: int
    transactions: int
    cash_card_total: Money = Field(alias="cashCardTotal")
    third_party_sales: Money = Field(alias="thirdPartySales")
    third_party_transactions: int = Field(alias="thirdPartyTransactions")
    hours_worked: Decimal = Field(alias="hoursWorked")


class SalesSummaryResponse(_FCModel):
    start_date: datetime = Field(alias="startDate")
    end_date: datetime = Field(alias="endDate")
    data: list[SalesSummaryRow]


# ---------------------------------------------------------------------------
# DailyTimeclock
# ---------------------------------------------------------------------------


class TimeclockEntry(_FCModel):
    """Live API (2026-05-12) returns ``hoursAfterAdj``/``hoursBeforeAdj``/
    ``adjAmount`` per the field table in the FreshConnect docs. The doc's JSON
    sample uses different keys (``hours``/``totalAdj``/``totalBeforeAdj``);
    we trust the field table and the live payload."""

    restaurant_number: str = Field(validation_alias=_RESTAURANT_NUMBER_ALIASES)
    clerk_id: str = Field(alias="clerkId")
    employee_name: str = Field(alias="employeeName")
    clock_in: datetime = Field(alias="clockIn")
    clock_out: datetime = Field(alias="clockOut")
    hours_before_adj: Decimal = Field(alias="hoursBeforeAdj")
    hours_after_adj: Decimal = Field(alias="hoursAfterAdj")
    adj_amount: Decimal = Field(alias="adjAmount")


class DailyTimeclockResponse(_FCModel):
    start_date: datetime = Field(alias="startDate")
    end_date: datetime = Field(alias="endDate")
    data: list[TimeclockEntry]


# ---------------------------------------------------------------------------
# InventoryMovement
# ---------------------------------------------------------------------------


class InventoryTotal(_FCModel):
    name: str
    total_cost: Money = Field(alias="totalCost")
    waste_value: Money = Field(alias="wasteValue")


class InventoryMovementItem(_FCModel):
    item: str
    inventory_item: str = Field(alias="inventoryItem")
    unit_of_measure: str = Field(alias="unitOfMeasure")
    unit_cost: Money = Field(alias="unitCost")
    delivery: Decimal
    transfer: Decimal
    total_cost: Money = Field(alias="totalCost")
    waste: Decimal
    waste_value: Money = Field(alias="wasteValue")


class InventoryMovementDay(_FCModel):
    store: str
    date: datetime
    totals: list[InventoryTotal]
    items: list[InventoryMovementItem]


class InventoryMovementResponse(_FCModel):
    start_date: datetime = Field(alias="startDate")
    end_date: datetime = Field(alias="endDate")
    data: list[InventoryMovementDay]


# ---------------------------------------------------------------------------
# PaidOutsAndNoSales
# ---------------------------------------------------------------------------


class NoSaleEvent(_FCModel):
    restaurant_number: str = Field(validation_alias=_RESTAURANT_NUMBER_ALIASES)
    time: datetime
    clerk_id: str = Field(alias="clerkId")
    clerk_name: str = Field(alias="clerkName")
    no_sale_type: str = Field(alias="noSaleType")
    reason_type: str = Field(alias="reasonType")
    reason: str


class PaidOutEvent(_FCModel):
    restaurant_number: str = Field(validation_alias=_RESTAURANT_NUMBER_ALIASES)
    time: datetime
    clerk_id: str = Field(alias="clerkId")
    clerk_name: str = Field(alias="clerkName")
    amount: Money
    reason: str
    comment: str


class PaidOutsAndNoSalesData(_FCModel):
    no_sales: list[NoSaleEvent] = Field(alias="noSales")
    paid_outs: list[PaidOutEvent] = Field(alias="paidOuts")


class PaidOutsAndNoSalesResponse(_FCModel):
    start_date: datetime = Field(alias="startDate")
    end_date: datetime = Field(alias="endDate")
    data: PaidOutsAndNoSalesData


# ---------------------------------------------------------------------------
# ThirdPartyDailySalesSummary
# ---------------------------------------------------------------------------


class ThirdPartyProvider(_FCModel):
    provider: str
    transactions: int
    net_sales: Money = Field(alias="netSales")
    sales: Money


class ThirdPartyDailyRow(_FCModel):
    date: datetime
    restaurant_number: str = Field(validation_alias=_RESTAURANT_NUMBER_ALIASES)
    total_sales: Money = Field(alias="totalSales")
    total_net_sales: Money = Field(alias="totalNetSales")
    total_transactions: int = Field(alias="totalTransactions")
    providers: list[ThirdPartyProvider]


class ThirdPartyDailySalesSummaryResponse(_FCModel):
    start_date: datetime = Field(alias="startDate")
    end_date: datetime = Field(alias="endDate")
    data: list[ThirdPartyDailyRow]


# ---------------------------------------------------------------------------
# ThirdPartySalesSummary
# ---------------------------------------------------------------------------


class ThirdPartySalesSummaryRow(_FCModel):
    restaurant_number: str = Field(validation_alias=_RESTAURANT_NUMBER_ALIASES)
    total_sales: Money = Field(alias="totalSales")
    total_net_sales: Money = Field(alias="totalNetSales")
    total_transactions: int = Field(alias="totalTransactions")
    providers: list[ThirdPartyProvider]


class ThirdPartySalesSummaryResponse(_FCModel):
    start_date: datetime = Field(alias="startDate")
    end_date: datetime = Field(alias="endDate")
    data: list[ThirdPartySalesSummaryRow]


# ---------------------------------------------------------------------------
# ThirdPartyTransactionSummary
# ---------------------------------------------------------------------------


class ThirdPartyTransactionRow(_FCModel):
    restaurant_number: str = Field(validation_alias=_RESTAURANT_NUMBER_ALIASES)
    date: datetime
    time: datetime
    receipt_number: int = Field(alias="receiptNumber")
    total: Money
    net_total: Money = Field(alias="netTotal")
    tax: Money
    tax_inclusive_amount: Money = Field(alias="taxInclusiveAmount")
    channel: str
    type: str


class ThirdPartyTransactionSummaryResponse(_FCModel):
    start_date: datetime = Field(alias="startDate")
    end_date: datetime = Field(alias="endDate")
    data: list[ThirdPartyTransactionRow]


# ---------------------------------------------------------------------------
# TipsDetails
# ---------------------------------------------------------------------------


class TipsEmployee(_FCModel):
    clerk_id: str = Field(alias="clerkId")
    employee_name: str = Field(alias="employeeName")


class TipsDetailRow(_FCModel):
    restaurant_number: str = Field(validation_alias=_RESTAURANT_NUMBER_ALIASES)
    date: datetime
    time: datetime
    receipt_number: int = Field(alias="receiptNumber")
    net_total: Money = Field(alias="netTotal")
    total: Money
    tax: Money
    tip: Money
    employee_split_tip: Money = Field(alias="employeeSplitTip")
    channel: str
    amount_tendered: Money = Field(alias="amountTendered")
    employees_at_time_of_tip: list[TipsEmployee] = Field(alias="employeesAtTimeOfTip")


class TipsDetailsResponse(_FCModel):
    start_date: datetime = Field(alias="startDate")
    end_date: datetime = Field(alias="endDate")
    data: list[TipsDetailRow]


# ---------------------------------------------------------------------------
# TransactionSummary & TransactionDetails
# ---------------------------------------------------------------------------


class _TransactionHeader(_FCModel):
    restaurant_number: str = Field(validation_alias=_RESTAURANT_NUMBER_ALIASES)
    date: datetime
    time: datetime
    type: str
    receipt_number: int = Field(alias="receiptNumber")
    channel: str
    sale_type: str = Field(alias="saleType")
    clerk_id: str = Field(alias="clerkId")
    clerk_name: str = Field(alias="clerkName")
    total: Money
    net_total: Money = Field(alias="netTotal")
    tax: Money
    tax_inclusive_amount: Money = Field(alias="taxInclusiveAmount")
    taxable_amount: Money = Field(alias="taxableAmount")
    units: int
    order_source: str = Field(alias="orderSource")
    delivery_provider: str = Field(alias="deliveryProvider")
    delivery_partner: str = Field(alias="deliveryPartner")


class TransactionSummaryRow(_TransactionHeader):
    """TransactionSummary rows are the header only — no nested arrays."""


class TransactionSummaryResponse(_FCModel):
    start_date: datetime = Field(alias="startDate")
    end_date: datetime = Field(alias="endDate")
    data: list[TransactionSummaryRow]


class TransactionItem(_FCModel):
    description: str
    category: str
    department: str
    original_price: Money = Field(alias="originalPrice")
    adjusted_price: Money = Field(alias="adjustedPrice")
    tax: Money
    tax_inclusive_amount: Money = Field(alias="taxInclusiveAmount")
    quantity: int
    price_override: bool = Field(alias="priceOverride")
    discount_code: str = Field(alias="discountCode")
    discount: str
    plu: str
    type: str


class Tender(_FCModel):
    description: str
    amount: Money
    change_amount: Money = Field(alias="changeAmount")
    tip_amount: Money = Field(alias="tipAmount")
    reference_number: str = Field(alias="referenceNumber")
    # Live API uses ``cardLast4`` and emits null for non-card tenders; the
    # doc sample shows ``cardLastFour``. Accept either name and allow None.
    card_last_four: str | None = Field(
        default=None,
        validation_alias=AliasChoices("cardLast4", "cardLastFour"),
    )


class LoyaltyEntry(_FCModel):
    base_points_earned: int = Field(alias="basePointsEarned")
    bonus_points_earned: int = Field(alias="bonusPointsEarned")
    base_money_earned: Money = Field(alias="baseMoneyEarned")
    bonus_money_earned: Money = Field(alias="bonusMoneyEarned")
    points_converted: int = Field(alias="pointsConverted")
    reward_money_redeemed: Money = Field(alias="rewardMoneyRedeemed")
    member_type: str = Field(alias="memberType")
    provider_type: str = Field(alias="providerType")


class TaxBreakdown(_FCModel):
    description: str
    amount: Money


class Discount(_FCModel):
    description: str
    quantity: int
    whole_order_discount_value: Money = Field(alias="wholeOrderDiscountValue")
    is_whole_order_discount: bool = Field(alias="isWholeOrderDiscount")
    whole_order_discount_type: str = Field(alias="wholeOrderDiscountType")


class TransactionDetailRow(_TransactionHeader):
    items: list[TransactionItem]
    tenders: list[Tender]
    loyalty: list[LoyaltyEntry]
    taxes: list[TaxBreakdown]
    discounts: list[Discount]
    non_subway_items: list[TransactionItem] = Field(alias="nonSubwayItems")


class TransactionDetailsResponse(_FCModel):
    start_date: datetime = Field(alias="startDate")
    end_date: datetime = Field(alias="endDate")
    data: list[TransactionDetailRow]


# ---------------------------------------------------------------------------
# WasteBreadCredits
# ---------------------------------------------------------------------------


class WasteBreadCreditItem(_FCModel):
    # Sample uses the API typo "resturantNumber" exclusively here.
    restaurant_number: str = Field(validation_alias=_RESTAURANT_NUMBER_ALIASES)
    time: datetime
    clerk_id: str = Field(alias="clerkId")
    clerk_name: str = Field(alias="clerkName")
    receipt_number: str = Field(alias="receiptNumber")
    item: str
    quantity: int
    item_price: Money = Field(alias="itemPrice")
    total_price: Money = Field(alias="totalPrice")
    reason: str


class WasteBreadCreditsData(_FCModel):
    waste: list[WasteBreadCreditItem]
    bread_credit: list[WasteBreadCreditItem] = Field(alias="breadCredit")


class WasteBreadCreditsResponse(_FCModel):
    start_date: datetime = Field(alias="startDate")
    end_date: datetime = Field(alias="endDate")
    data: WasteBreadCreditsData


# ---------------------------------------------------------------------------
# Wisr
# ---------------------------------------------------------------------------


class WisrQvpItem(_FCModel):
    """Quantity / Value / Percentage triplet used in adjustedCostOfGoods."""

    quantity: Decimal | None = None
    value: Decimal | None = None
    percentage: Percentage | None = None


class AdjustedCostOfGoods(_FCModel):
    free_units: WisrQvpItem = Field(alias="freeUnits")
    employee_free: WisrQvpItem = Field(alias="employeeFree")
    employee_discounts: WisrQvpItem = Field(alias="employeeDiscounts")
    other_discount_value: WisrQvpItem = Field(alias="otherDiscountValue")
    fvm_discounts_value: WisrQvpItem = Field(alias="fvmDiscountsValue")
    misc_and_drink_disc_value: WisrQvpItem = Field(alias="miscAndDrinkDiscValue")
    total_discount_value: WisrQvpItem = Field(alias="totalDiscountValue")
    discount_value_pct_of_sales: WisrQvpItem = Field(alias="discountValuePctOfSales")
    adjusted_cost_of_goods: WisrQvpItem = Field(alias="adjustedCostOfGoods")


class InventoryCategoryStats(_FCModel):
    value_used: Decimal | None = Field(default=None, alias="valueUsed")
    value_diff: Decimal | None = Field(default=None, alias="valueDiff")
    actual_percentage: Percentage | None = Field(default=None, alias="actualPercentage")
    expected_percentage: Percentage | None = Field(default=None, alias="expectedPercentage")
    percentage_diff: Percentage | None = Field(default=None, alias="percentageDiff")


class InventoryCategoriesSummary(_FCModel):
    cheese: InventoryCategoryStats
    meat_protein: InventoryCategoryStats = Field(alias="meatProtein")
    bread_carrier: InventoryCategoryStats = Field(alias="breadCarrier")
    veggies: InventoryCategoryStats
    toppings: InventoryCategoryStats
    papergoods: InventoryCategoryStats
    units_cost: InventoryCategoryStats = Field(alias="unitsCost")
    drinks_cost: InventoryCategoryStats = Field(alias="drinksCost")
    misc_cost: InventoryCategoryStats = Field(alias="miscCost")
    cost_of_goods: InventoryCategoryStats = Field(alias="costOfGoods")
    distribution_cost: InventoryCategoryStats = Field(alias="distributionCost")


class WisrValuePercent(_FCModel):
    value: Decimal | None = None
    percentage: Percentage | None = None


class SalesSummaryItems(_FCModel):
    unit_sales: WisrValuePercent = Field(alias="unitSales")
    catering_sales: WisrValuePercent = Field(alias="cateringSales")
    drink_sales: WisrValuePercent = Field(alias="drinkSales")
    misc_sales: WisrValuePercent = Field(alias="miscSales")
    net_subway_sales: WisrValuePercent = Field(alias="netSubwaySales")
    gas: WisrValuePercent
    electric: WisrValuePercent
    telephone: WisrValuePercent
    garbage: WisrValuePercent
    insurance: WisrValuePercent
    rent: WisrValuePercent
    laundry: WisrValuePercent
    misc: WisrValuePercent
    repair_maintenance: WisrValuePercent = Field(alias="repairMaintenance")
    operating_expenses: WisrValuePercent = Field(alias="operatingExpenses")
    labor_and_taxes: WisrValuePercent = Field(alias="laborAndTaxes")
    cost_of_goods: WisrValuePercent = Field(alias="costOfGoods")
    royalty: WisrValuePercent
    faf: WisrValuePercent
    local_advertising: WisrValuePercent = Field(alias="localAdvertising")
    total_expenses: WisrValuePercent = Field(alias="totalExpenses")
    balance: WisrValuePercent
    financial_strength: WisrValuePercent = Field(alias="financialStrength")
    loans: WisrValuePercent


class WisrQuantityPercent(_FCModel):
    quantity: Decimal | None = None
    percentage: Percentage | None = None


class UnitsSummaryItems(_FCModel):
    footlong: WisrQuantityPercent
    six_inch: WisrQuantityPercent = Field(alias="sixInch")
    three_inch_and_muffin: WisrQuantityPercent = Field(alias="threeInchAndMuffin")
    salads: WisrQuantityPercent
    pizza: WisrQuantityPercent
    other_units: WisrQuantityPercent = Field(alias="otherUnits")
    total_units: WisrQuantityPercent = Field(alias="totalUnits")
    drinks: WisrQuantityPercent


class WisrQuantityValue(_FCModel):
    quantity: Decimal | None = None
    value: Decimal | None = None


class CateringSummaryItems(_FCModel):
    giant_subs: WisrQuantityValue = Field(alias="giantSubs")
    sandwich_platters: WisrQuantityValue = Field(alias="sandwichPlatters")
    boxed_meals: WisrQuantityValue = Field(alias="boxedMeals")
    dessert_platters: WisrQuantityValue = Field(alias="dessertPlatters")


class DistributionCostItem(_FCModel):
    value_used: Decimal | None = Field(default=None, alias="valueUsed")
    actual_percent: Percentage | None = Field(default=None, alias="actualPercent")


class DistributionCosts(_FCModel):
    delivery_fee: DistributionCostItem = Field(alias="deliveryFee")
    distributor_credits: DistributionCostItem = Field(alias="distributorCredits")
    annual_ipc_patronage: DistributionCostItem = Field(alias="annualIpcPatronage")
    distribution_costs: DistributionCostItem = Field(alias="distributionCosts")


class WisrInventoryItem(_FCModel):
    name: str
    open: Decimal | None = None
    delivered: Decimal | None = None
    left: Decimal | None = None
    used: Decimal | None = None
    pos_difference: Decimal | None = Field(default=None, alias="posDifference")
    recorded_waste: Decimal | None = Field(default=None, alias="recordedWaste")
    cost: Decimal | None = None
    value_used: Decimal | None = Field(default=None, alias="valueUsed")
    value_difference: Decimal | None = Field(default=None, alias="valueDifference")
    actual_percentage: Percentage | None = Field(default=None, alias="actualPercentage")
    expected_percentage: Percentage | None = Field(default=None, alias="expectedPercentage")
    diff_percentage: Percentage | None = Field(default=None, alias="diffPercentage")


class CashBreadOverShortTotals(_FCModel):
    cash_daily_figures: DaysOfWeekLong = Field(alias="cashDailyFigures")
    bread_daily_figures: DaysOfWeekLong = Field(alias="breadDailyFigures")


class WisrRow(_FCModel):
    restaurant_number: str = Field(validation_alias=_RESTAURANT_NUMBER_ALIASES)
    total_inventory_value: Money = Field(alias="totalInventoryValue")
    adjusted_cost_of_goods: AdjustedCostOfGoods = Field(alias="adjustedCostOfGoods")
    inventory_categories_summary: InventoryCategoriesSummary = Field(
        alias="inventoryCategoriesSummary"
    )
    sales_summary_items: SalesSummaryItems = Field(alias="salesSummaryItems")
    units_summary_items: UnitsSummaryItems = Field(alias="unitsSummaryItems")
    catering_summary_items: CateringSummaryItems = Field(alias="cateringSummaryItems")
    distribution_costs: DistributionCosts = Field(alias="distributionCosts")
    customer_count: Decimal = Field(alias="customerCount")
    units_per_customer: Decimal = Field(alias="unitsPerCustomer")
    factor: Decimal
    average_ticket: Decimal = Field(alias="averageTicket")
    inventory_items: list[WisrInventoryItem] = Field(alias="inventoryItems")
    cash_bread_over_short_totals: CashBreadOverShortTotals = Field(
        alias="cashBreadOverShortTotals"
    )


class WisrResponse(_FCModel):
    week_end_date: datetime = Field(alias="weekEndDate")
    data: list[WisrRow]


# ---------------------------------------------------------------------------
# ControlSheet
# ---------------------------------------------------------------------------


class ControlSheetSummary(_FCModel):
    week_end_date: datetime = Field(alias="weekEndDate")
    store_number: str = Field(alias="storeNumber")
    cost_of_good_percentage: Percentage = Field(alias="costOfGoodPercentage")
    cost_of_units_percentage: Percentage = Field(alias="costOfUnitsPercentage")
    drink_cost_percentage: Percentage = Field(alias="drinkCostPercentage")
    adjusted_cost_of_goods_percentage: Percentage = Field(
        alias="adjustedCostOfGoodsPercentage"
    )
    adjusted_cost_of_units_percentage: Percentage = Field(
        alias="adjustedCostOfUnitsPercentage"
    )
    misc_cost_percentage: Percentage = Field(alias="miscCostPercentage")
    productivity: Decimal
    factor: Decimal
    customer_count: int = Field(alias="customerCount")
    net_sales: Money = Field(alias="netSales")


class CashControl(_FCModel):
    closing_grand_total: DaysOfWeek = Field(alias="closingGrandTotal")
    opening_grand_total: DaysOfWeek = Field(alias="openingGrandTotal")
    adjustments: DaysOfWeek
    adjusted_proceeds: DaysOfWeek = Field(alias="adjustedProceeds")
    opening_cash: DaysOfWeek = Field(alias="openingCash")
    paidouts: DaysOfWeek
    credit_sales: DaysOfWeek = Field(alias="creditSales")
    required_cash: DaysOfWeek = Field(alias="requiredCash")
    actual_cash: DaysOfWeek = Field(alias="actualCash")
    over_short: DaysOfWeek = Field(alias="overShort")
    closing_keep: DaysOfWeek = Field(alias="closingKeep")
    deposit_in_bank: DaysOfWeek = Field(alias="depositInBank")
    cashcards: DaysOfWeek
    debit: DaysOfWeek
    visa_and_mastercard: DaysOfWeek = Field(alias="visaAndMastercard")
    discover: DaysOfWeek
    american_express: DaysOfWeek = Field(alias="americanExpress")
    catering_call_center: DaysOfWeek = Field(alias="cateringCallCenter")
    other: DaysOfWeek
    pay_pal: DaysOfWeek = Field(alias="payPal")
    cash_rounding_adjustment: DaysOfWeek = Field(alias="cashRoundingAdjustment")


class BreadSection(_FCModel):
    opening: DaysOfWeek
    delivered: DaysOfWeek
    credits: DaysOfWeek
    left: DaysOfWeek
    used: DaysOfWeek
    sold: DaysOfWeek
    over_short: DaysOfWeek = Field(alias="overShort")
    bread_left: DaysOfWeek = Field(alias="breadLeft")
    bread_over_short: DaysOfWeek = Field(alias="breadOverShort")
    flatbread_left: DaysOfWeek = Field(alias="flatbreadLeft")
    flatbread_over_short: DaysOfWeek = Field(alias="flatbreadOverShort")
    salad_left: DaysOfWeek = Field(alias="saladLeft")
    salad_over_short: DaysOfWeek = Field(alias="saladOverShort")
    muffin_left: DaysOfWeek = Field(alias="muffinLeft")
    muffin_over_short: DaysOfWeek = Field(alias="muffinOverShort")
    pizza_left: DaysOfWeek = Field(alias="pizzaLeft")
    pizza_over_short: DaysOfWeek = Field(alias="pizzaOverShort")
    other_left: DaysOfWeek = Field(alias="otherLeft")
    other_over_short: DaysOfWeek = Field(alias="otherOverShort")


class LaborSection(_FCModel):
    hours_open: DaysOfWeek = Field(alias="hoursOpen")
    hours_worked: DaysOfWeek = Field(alias="hoursWorked")
    productivity: DaysOfWeek
    sales_per_labor_hour: DaysOfWeek = Field(alias="salesPerLaborHour")


class MetricsSection(_FCModel):
    factor: DaysOfWeek
    customer_count: DaysOfWeek = Field(alias="customerCount")
    average_ticket: DaysOfWeek = Field(alias="averageTicket")


class SalesItemization(_FCModel):
    total_subway_sales: DaysOfWeek = Field(alias="totalSubwaySales")
    footlong: DaysOfWeek
    six_inch: DaysOfWeek = Field(alias="sixInch")
    three_inch: DaysOfWeek = Field(alias="threeInch")
    muffin_melt: DaysOfWeek = Field(alias="muffinMelt")
    salad: DaysOfWeek
    pizza: DaysOfWeek
    other_carrier: DaysOfWeek = Field(alias="otherCarrier")
    add_on: DaysOfWeek = Field(alias="addOn")
    catering: DaysOfWeek
    unit_coupons_discounts: DaysOfWeek = Field(alias="unitCouponsDiscounts")
    unit_refunds: DaysOfWeek = Field(alias="unitRefunds")
    unit_voids: DaysOfWeek = Field(alias="unitVoids")
    total_units_sales: DaysOfWeek = Field(alias="totalUnitsSales")
    fountain: DaysOfWeek
    bottled_beverage: DaysOfWeek = Field(alias="bottledBeverage")
    hot_beverage: DaysOfWeek = Field(alias="hotBeverage")
    other_beverage: DaysOfWeek = Field(alias="otherBeverage")
    drinks_coupons_discounts: DaysOfWeek = Field(alias="drinksCouponsDiscounts")
    drinks_refunds: DaysOfWeek = Field(alias="drinksRefunds")
    drinks_voids: DaysOfWeek = Field(alias="drinksVoids")
    total_drinks_sales: DaysOfWeek = Field(alias="totalDrinksSales")
    chips: DaysOfWeek
    cookies: DaysOfWeek
    soups: DaysOfWeek
    other_misc: DaysOfWeek = Field(alias="otherMisc")
    misc_coupons_discounts: DaysOfWeek = Field(alias="miscCouponsDiscounts")
    misc_refunds: DaysOfWeek = Field(alias="miscRefunds")
    misc_voids: DaysOfWeek = Field(alias="miscVoids")
    total_misc_sales: DaysOfWeek = Field(alias="totalMiscSales")
    cash_card_sales: DaysOfWeek = Field(alias="cashCardSales")
    adj_sales_tax_and_fees: DaysOfWeek = Field(alias="adjSalesTaxAndFees")
    tax_and_fee_adjustments: DaysOfWeek = Field(alias="taxAndFeeAdjustments")
    adj_other_receipts: DaysOfWeek = Field(alias="adjOtherReceipts")
    adj_co_brand_sales: DaysOfWeek = Field(alias="adjCoBrandSales")
    other_adjustments: DaysOfWeek = Field(alias="otherAdjustments")


class UnitItemization(_FCModel):
    footlong: DaysOfWeek
    six_inch: DaysOfWeek = Field(alias="sixInch")
    three_inch: DaysOfWeek = Field(alias="threeInch")
    muffin_melt: DaysOfWeek = Field(alias="muffinMelt")
    salad: DaysOfWeek
    pizza: DaysOfWeek
    other_carrier: DaysOfWeek = Field(alias="otherCarrier")
    catering: DaysOfWeek
    employee_and_free_units: DaysOfWeek = Field(alias="employeeAndFreeUnits")
    total_units: DaysOfWeek = Field(alias="totalUnits")
    all_units_sold: DaysOfWeek = Field(alias="allUnitsSold")
    drink: DaysOfWeek
    drink_percentage: DaysOfWeek = Field(alias="drinkPercentage")


class ControlSheetRow(_FCModel):
    summary: ControlSheetSummary
    cash_control: CashControl = Field(alias="cashControl")
    bread: BreadSection
    labor: LaborSection
    metrics: MetricsSection
    sales_itemization: SalesItemization = Field(alias="salesItemization")
    unit_itemization: UnitItemization = Field(alias="unitItemization")


class ControlSheetResponse(_FCModel):
    week_end_date: datetime = Field(alias="weekEndDate")
    data: list[ControlSheetRow]
