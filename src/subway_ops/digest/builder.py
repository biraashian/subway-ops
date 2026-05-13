"""Weekly digest builder — renders a self-contained HTML email body.

The function ``build_digest(week_end)`` queries the marts and returns
``(subject, html_body)`` for the just-closed Subway business week. The
HTML is inline-styled on every critical cell so Gmail / Outlook / Apple
Mail render the traffic-light cells the same way (heavy email clients
strip ``<style>`` blocks). Width is fixed at 600px for compatibility.

For testability the renderer is split in two layers:

- ``_collect_digest_data(week_end)`` fetches everything from Postgres
  and packages it into a ``DigestData`` dataclass.
- ``render_digest(data)`` is a pure function: dataclass in, HTML out.
  Tests build a synthetic ``DigestData`` and snapshot the rendered
  HTML so we never need a live database to assert layout.

Color palette and money/percent formatting live as module-level helpers
so the dashboard and the email keep using the same tokens.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

import structlog
from sqlalchemy import text

from subway_ops.calendar import business_week_of, previous_business_week
from subway_ops.config import (
    TARGET_FOOD_COST_PORTFOLIO,
    TARGET_FOOD_COST_STORE,
    TARGET_LABOR_COST_PORTFOLIO,
    TARGET_LABOR_COST_STORE,
    settings,
)
from subway_ops.dashboard.components import GREEN, NEUTRAL_BG, RED, YELLOW
from subway_ops.db.connection import get_engine

log = structlog.get_logger(__name__)

# Email layout. 600px is the de-facto cap for mass email clients; below
# that the design degrades gracefully on phones too.
EMAIL_WIDTH_PX = 600

# Status-bucket colors specifically for the digest. Re-exported from
# ``components`` so the dashboard can pick them up if it ever wants to
# mirror the digest swatch.
COLOR_GREEN = GREEN
COLOR_YELLOW = YELLOW
COLOR_RED = RED
COLOR_NEUTRAL_BG = NEUTRAL_BG

# Faint amber band above target before a metric flips red. 2 percentage
# points matches the dashboard's NEAR_TARGET_TOLERANCE.
NEAR_TARGET_TOLERANCE_PP = Decimal("0.02")

# Address operators reply to with digest feedback. Defaults to the same
# inbox that gets failure alerts; falls back to a static string if unset.
_DEFAULT_FEEDBACK = "amitojsubway@gmail.com"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PortfolioSnapshot:
    """Aggregate KPIs across every visible store for one week.

    All percentages are fractional (0.22 == 22%). ``prior_*`` fields are
    the same metrics for the immediately-preceding closed week so the
    renderer can draw delta arrows. Any of them may be ``None`` if the
    underlying mart row is missing.
    """

    net_sales: Decimal | None
    transactions: int | None
    food_cost_pct: Decimal | None
    labor_cost_pct: Decimal | None
    prior_net_sales: Decimal | None
    prior_transactions: int | None
    prior_food_cost_pct: Decimal | None
    prior_labor_cost_pct: Decimal | None


@dataclass(frozen=True)
class TargetRow:
    """One row in the targets dashboard table."""

    metric: str
    current: Decimal | None
    target: Decimal
    is_pct: bool = True


@dataclass(frozen=True)
class ReconCase:
    """One escalated reconciliation case surfaced in the digest."""

    store_number: str
    store_name: str
    variance: Decimal
    status: str


@dataclass(frozen=True)
class ReconSummary:
    """Counts by status plus the list of escalated cases."""

    counts_by_status: dict[str, int]
    escalated_cases: tuple[ReconCase, ...]


@dataclass(frozen=True)
class StoreRow:
    """One per-store row in the all-stores table at the bottom."""

    store_number: str
    store_name: str
    field_manager_name: str | None
    net_sales: Decimal | None
    transactions: int | None
    food_cost_pct: Decimal | None
    labor_cost_pct: Decimal | None
    cash_overshort: Decimal | None
    is_food_cost_in_target: bool | None
    is_labor_cost_in_target: bool | None


@dataclass(frozen=True)
class FMRollup:
    """One field manager's portfolio + the stores in their cluster."""

    field_manager_name: str
    store_count: int
    net_sales: Decimal | None
    food_cost_pct: Decimal | None
    labor_cost_pct: Decimal | None
    is_food_cost_in_portfolio_target: bool | None
    is_labor_cost_in_portfolio_target: bool | None
    stores: tuple[StoreRow, ...]


@dataclass(frozen=True)
class DigestData:
    """Everything the renderer needs to produce a digest email."""

    week_end: date
    week_start: date
    portfolio: PortfolioSnapshot
    targets: tuple[TargetRow, ...]
    recon: ReconSummary
    fm_rollups: tuple[FMRollup, ...]
    stores: tuple[StoreRow, ...]
    dashboard_url: str
    feedback_email: str
    flagged_count: int = field(init=False)
    escalated_count: int = field(init=False)

    def __post_init__(self) -> None:
        # ``frozen=True`` blocks normal attribute assignment; use
        # ``object.__setattr__`` to back-fill the derived counts.
        object.__setattr__(
            self, "flagged_count", self.recon.counts_by_status.get("flagged", 0)
        )
        object.__setattr__(
            self, "escalated_count", self.recon.counts_by_status.get("escalated", 0)
        )


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _fmt_money(v: Decimal | None) -> str:
    if v is None:
        return "—"
    return f"${v:,.0f}"


def _fmt_money_signed(v: Decimal | None) -> str:
    if v is None:
        return "—"
    sign = "-" if v < 0 else "+" if v > 0 else ""
    return f"{sign}${abs(v):,.0f}"


def _fmt_int(v: int | None) -> str:
    if v is None:
        return "—"
    return f"{v:,}"


def _fmt_pct(v: Decimal | None) -> str:
    if v is None:
        return "—"
    return f"{v * 100:.1f}%"


def _fmt_pp_delta(curr: Decimal | None, prior: Decimal | None) -> str:
    """Format a percentage-point delta with arrow + sign.

    Returns ``""`` when either side is missing so the renderer can hide
    the delta column entirely instead of showing a noisy ``—``.
    """
    if curr is None or prior is None:
        return ""
    diff_pp = (curr - prior) * 100
    if diff_pp == 0:
        return "→ 0.0pp"
    arrow = "▲" if diff_pp > 0 else "▼"
    return f"{arrow} {abs(diff_pp):.1f}pp"


def _fmt_money_delta(curr: Decimal | None, prior: Decimal | None) -> str:
    if curr is None or prior is None:
        return ""
    diff = curr - prior
    if diff == 0:
        return "→ $0"
    arrow = "▲" if diff > 0 else "▼"
    return f"{arrow} ${abs(diff):,.0f}"


def _fmt_int_delta(curr: int | None, prior: int | None) -> str:
    if curr is None or prior is None:
        return ""
    diff = curr - prior
    if diff == 0:
        return "→ 0"
    arrow = "▲" if diff > 0 else "▼"
    return f"{arrow} {abs(diff):,}"


def _bucket_pct(value: Decimal | None, target: Decimal) -> str:
    """Bucket a fractional percent against ``target``.

    Returns one of ``in_target`` / ``near`` / ``off`` / ``unknown``.
    Matches ``dashboard.components.status_bucket``'s semantics exactly so
    the email and the UI never disagree.
    """
    if value is None:
        return "unknown"
    if value <= target:
        return "in_target"
    if value <= target + NEAR_TARGET_TOLERANCE_PP:
        return "near"
    return "off"


def _bucket_color(bucket: str) -> str:
    return {
        "in_target": COLOR_GREEN,
        "near": COLOR_YELLOW,
        "off": COLOR_RED,
    }.get(bucket, COLOR_NEUTRAL_BG)


def _money_delta_color(curr: Decimal | None, prior: Decimal | None) -> str:
    """Sales-style delta: more is good. Empty string when undelta-able."""
    if curr is None or prior is None:
        return ""
    if curr > prior:
        return COLOR_GREEN
    if curr < prior:
        return COLOR_RED
    return COLOR_NEUTRAL_BG


def _pct_delta_color(
    curr: Decimal | None, prior: Decimal | None, target: Decimal
) -> str:
    """Cost-style delta: lower is better. Color flips when crossing target."""
    if curr is None or prior is None:
        return ""
    # Improvement (curr < prior) is green even if still above target — the
    # operator should see effort rewarded.
    if curr < prior:
        return COLOR_GREEN
    if curr > prior:
        return COLOR_RED
    return COLOR_NEUTRAL_BG


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _td(content: str, *, style: str = "") -> str:
    base = "padding:8px;border-bottom:1px solid #e5e7eb;font-size:14px;"
    return f'<td style="{base}{style}">{content}</td>'


def _th(content: str, *, style: str = "") -> str:
    base = (
        "padding:8px;border-bottom:2px solid #d1d5db;"
        "font-size:13px;text-align:left;color:#374151;font-weight:600;"
        "background:#f9fafb;"
    )
    return f'<th style="{base}{style}">{content}</th>'


def _section_header(title: str) -> str:
    return (
        f'<h2 style="font-size:18px;margin:24px 0 8px 0;'
        f'color:#111827;font-weight:600;">{html.escape(title)}</h2>'
    )


def _color_cell(text_: str, color: str) -> str:
    """A solid-background traffic-light cell."""
    fg = "#ffffff" if color in (COLOR_GREEN, COLOR_RED) else "#1f2937"
    return _td(
        html.escape(text_),
        style=f"background:{color};color:{fg};font-weight:600;text-align:right;",
    )


def _delta_cell(text_: str, color: str) -> str:
    if not text_:
        return _td("")
    if not color:
        return _td(html.escape(text_), style="text-align:right;")
    return _td(
        html.escape(text_),
        style=f"color:{color};text-align:right;font-weight:600;",
    )


def _render_portfolio(data: DigestData) -> str:
    p = data.portfolio
    sales_color = _money_delta_color(p.net_sales, p.prior_net_sales)
    txn_color = _money_delta_color(
        Decimal(p.transactions) if p.transactions is not None else None,
        Decimal(p.prior_transactions) if p.prior_transactions is not None else None,
    )
    food_color = _pct_delta_color(
        p.food_cost_pct, p.prior_food_cost_pct, TARGET_FOOD_COST_PORTFOLIO
    )
    labor_color = _pct_delta_color(
        p.labor_cost_pct, p.prior_labor_cost_pct, TARGET_LABOR_COST_PORTFOLIO
    )
    rows = [
        (
            "Net sales",
            _fmt_money(p.net_sales),
            _fmt_money_delta(p.net_sales, p.prior_net_sales),
            sales_color,
        ),
        (
            "Transactions",
            _fmt_int(p.transactions),
            _fmt_int_delta(p.transactions, p.prior_transactions),
            txn_color,
        ),
        (
            "Food cost % (weighted)",
            _fmt_pct(p.food_cost_pct),
            _fmt_pp_delta(p.food_cost_pct, p.prior_food_cost_pct),
            food_color,
        ),
        (
            "Labor cost % (weighted)",
            _fmt_pct(p.labor_cost_pct),
            _fmt_pp_delta(p.labor_cost_pct, p.prior_labor_cost_pct),
            labor_color,
        ),
    ]
    body = "".join(
        "<tr>"
        + _td(html.escape(metric), style="font-weight:500;")
        + _td(html.escape(value), style="text-align:right;font-variant-numeric:tabular-nums;")
        + _delta_cell(delta, color)
        + "</tr>"
        for metric, value, delta, color in rows
    )
    return (
        _section_header("Portfolio snapshot")
        + f'<table role="presentation" cellpadding="0" cellspacing="0" '
        f'style="border-collapse:collapse;width:100%;max-width:{EMAIL_WIDTH_PX}px;'
        f'background:{COLOR_NEUTRAL_BG};">'
        + "<tr>"
        + _th("Metric")
        + _th("This week", style="text-align:right;")
        + _th("vs prior", style="text-align:right;")
        + "</tr>"
        + body
        + "</table>"
    )


def _render_targets(data: DigestData) -> str:
    rows: list[str] = []
    for row in data.targets:
        bucket = _bucket_pct(row.current, row.target)
        color = _bucket_color(bucket)
        status_text = {
            "in_target": "On target",
            "near": "Near target",
            "off": "Off target",
            "unknown": "No data",
        }[bucket]
        rows.append(
            "<tr>"
            + _td(html.escape(row.metric), style="font-weight:500;")
            + _td(
                html.escape(_fmt_pct(row.current) if row.is_pct else str(row.current)),
                style="text-align:right;font-variant-numeric:tabular-nums;",
            )
            + _td(
                html.escape(_fmt_pct(row.target) if row.is_pct else str(row.target)),
                style="text-align:right;font-variant-numeric:tabular-nums;color:#6b7280;",
            )
            + _color_cell(status_text, color)
            + "</tr>"
        )
    return (
        _section_header("Targets")
        + f'<table role="presentation" cellpadding="0" cellspacing="0" '
        f'style="border-collapse:collapse;width:100%;max-width:{EMAIL_WIDTH_PX}px;">'
        + "<tr>"
        + _th("Metric")
        + _th("Current", style="text-align:right;")
        + _th("Target", style="text-align:right;")
        + _th("Status", style="text-align:right;")
        + "</tr>"
        + "".join(rows)
        + "</table>"
    )


def _render_recon(data: DigestData) -> str:
    counts = data.recon.counts_by_status
    chips = []
    for status in ("clean", "flagged", "escalated", "unverified"):
        n = counts.get(status, 0)
        color = {
            "clean": COLOR_GREEN,
            "flagged": COLOR_YELLOW,
            "escalated": COLOR_RED,
            "unverified": "#9ca3af",
        }[status]
        fg = "#ffffff" if status in ("clean", "escalated") else "#1f2937"
        chips.append(
            f'<span style="display:inline-block;padding:4px 10px;margin-right:6px;'
            f'border-radius:12px;background:{color};color:{fg};'
            f'font-size:13px;font-weight:600;">{status} {n}</span>'
        )
    chip_row = (
        '<div style="margin:8px 0 12px 0;">' + "".join(chips) + "</div>"
    )
    if not data.recon.escalated_cases:
        body = (
            '<p style="color:#374151;font-size:14px;margin:8px 0;">'
            "No escalated cases this week.</p>"
        )
    else:
        rows = "".join(
            "<tr>"
            + _td(html.escape(c.store_number))
            + _td(html.escape(c.store_name))
            + _td(
                html.escape(_fmt_money_signed(c.variance)),
                style="text-align:right;font-variant-numeric:tabular-nums;",
            )
            + _color_cell(c.status, COLOR_RED)
            + "</tr>"
            for c in data.recon.escalated_cases
        )
        body = (
            f'<table role="presentation" cellpadding="0" cellspacing="0" '
            f'style="border-collapse:collapse;width:100%;max-width:{EMAIL_WIDTH_PX}px;">'
            + "<tr>"
            + _th("Store #")
            + _th("Name")
            + _th("Variance", style="text-align:right;")
            + _th("Status", style="text-align:right;")
            + "</tr>"
            + rows
            + "</table>"
        )
    return _section_header("Reconciliation") + chip_row + body


def _render_store_row(s: StoreRow) -> str:
    food_color = _bucket_color(_bucket_pct(s.food_cost_pct, TARGET_FOOD_COST_STORE))
    labor_color = _bucket_color(_bucket_pct(s.labor_cost_pct, TARGET_LABOR_COST_STORE))
    cash_color = COLOR_NEUTRAL_BG
    if s.cash_overshort is not None:
        cash_color = (
            COLOR_GREEN
            if abs(s.cash_overshort) < Decimal("5")
            else COLOR_RED
            if abs(s.cash_overshort) >= Decimal("50")
            else COLOR_YELLOW
        )
    return (
        "<tr>"
        + _td(html.escape(s.store_number))
        + _td(html.escape(s.store_name))
        + _td(
            html.escape(_fmt_money(s.net_sales)),
            style="text-align:right;font-variant-numeric:tabular-nums;",
        )
        + _td(
            html.escape(_fmt_int(s.transactions)),
            style="text-align:right;font-variant-numeric:tabular-nums;",
        )
        + _color_cell(_fmt_pct(s.food_cost_pct), food_color)
        + _color_cell(_fmt_pct(s.labor_cost_pct), labor_color)
        + _color_cell(_fmt_money_signed(s.cash_overshort), cash_color)
        + "</tr>"
    )


def _render_store_table(stores: tuple[StoreRow, ...]) -> str:
    if not stores:
        return (
            '<p style="color:#6b7280;font-size:14px;margin:8px 0;">'
            "No store data for this week.</p>"
        )
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" '
        f'style="border-collapse:collapse;width:100%;max-width:{EMAIL_WIDTH_PX}px;">'
        + "<tr>"
        + _th("Store #")
        + _th("Name")
        + _th("Net sales", style="text-align:right;")
        + _th("Txns", style="text-align:right;")
        + _th("Food %", style="text-align:right;")
        + _th("Labor %", style="text-align:right;")
        + _th("Cash O/S", style="text-align:right;")
        + "</tr>"
        + "".join(_render_store_row(s) for s in stores)
        + "</table>"
    )


def _render_fm_rollups(data: DigestData) -> str:
    if not data.fm_rollups:
        return ""
    parts: list[str] = [_section_header("Field manager rollups")]
    for fm in data.fm_rollups:
        food_color = _bucket_color(
            _bucket_pct(fm.food_cost_pct, TARGET_FOOD_COST_PORTFOLIO)
        )
        labor_color = _bucket_color(
            _bucket_pct(fm.labor_cost_pct, TARGET_LABOR_COST_PORTFOLIO)
        )
        parts.append(
            f'<h3 style="font-size:16px;margin:16px 0 4px 0;color:#111827;">'
            f"{html.escape(fm.field_manager_name)} "
            f'<span style="font-weight:400;color:#6b7280;font-size:13px;">'
            f"({fm.store_count} stores)</span></h3>"
        )
        parts.append(
            f'<table role="presentation" cellpadding="0" cellspacing="0" '
            f'style="border-collapse:collapse;width:100%;max-width:{EMAIL_WIDTH_PX}px;'
            f'background:{COLOR_NEUTRAL_BG};margin-bottom:6px;">'
            + "<tr>"
            + _td("Net sales", style="font-weight:500;")
            + _td(
                html.escape(_fmt_money(fm.net_sales)),
                style="text-align:right;font-variant-numeric:tabular-nums;",
            )
            + _td("Food %", style="font-weight:500;")
            + _color_cell(_fmt_pct(fm.food_cost_pct), food_color)
            + _td("Labor %", style="font-weight:500;")
            + _color_cell(_fmt_pct(fm.labor_cost_pct), labor_color)
            + "</tr>"
            + "</table>"
        )
        parts.append(_render_store_table(fm.stores))
    return "".join(parts)


def _render_header(data: DigestData) -> str:
    return (
        f'<h1 style="font-size:22px;margin:0 0 4px 0;color:#111827;">'
        f"Subway weekly digest</h1>"
        f'<p style="font-size:14px;color:#6b7280;margin:0 0 16px 0;">'
        f"Week of {data.week_start:%a %Y-%m-%d} → {data.week_end:%a %Y-%m-%d}"
        f"</p>"
    )


def _render_footer(data: DigestData) -> str:
    url_html = (
        f'<a href="{html.escape(data.dashboard_url)}" '
        f'style="color:#2563eb;">{html.escape(data.dashboard_url)}</a>'
        if data.dashboard_url
        else '<span style="color:#9ca3af;">(dashboard URL not configured)</span>'
    )
    return (
        '<hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;">'
        f'<p style="font-size:13px;color:#6b7280;margin:4px 0;">'
        f"Open dashboard: {url_html}</p>"
        f'<p style="font-size:13px;color:#6b7280;margin:4px 0;">'
        f"Feedback: reply to "
        f'<a href="mailto:{html.escape(data.feedback_email)}" '
        f'style="color:#2563eb;">{html.escape(data.feedback_email)}</a>'
        f"</p>"
    )


def render_digest(data: DigestData) -> tuple[str, str]:
    """Render a ``DigestData`` instance into ``(subject, html_body)``.

    Pure function: no DB access, no time-of-day reasoning. The renderer
    is the unit-test surface; ``_collect_digest_data`` owns DB access.
    """
    subject = (
        f"Subway weekly — week ending {data.week_end:%Y-%m-%d} — "
        f"{data.flagged_count} flagged, {data.escalated_count} escalated"
    )
    head_style = (
        "<style>"
        "body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,"
        "Helvetica,Arial,sans-serif;color:#111827;background:#ffffff;}"
        "table{font-family:inherit;}"
        "</style>"
    )
    body = (
        "<!doctype html><html><head>"
        '<meta charset="utf-8">'
        f"<title>{html.escape(subject)}</title>"
        + head_style
        + "</head><body>"
        f'<div style="max-width:{EMAIL_WIDTH_PX}px;margin:0 auto;padding:16px;">'
        + _render_header(data)
        + _render_portfolio(data)
        + _render_targets(data)
        + _render_recon(data)
        + _render_fm_rollups(data)
        + _section_header("Per-store summary")
        + _render_store_table(data.stores)
        + _render_footer(data)
        + "</div></body></html>"
    )
    return subject, body


# ---------------------------------------------------------------------------
# DB data collection
# ---------------------------------------------------------------------------


def _default_targets(
    portfolio_food: Decimal | None, portfolio_labor: Decimal | None
) -> tuple[TargetRow, ...]:
    return (
        TargetRow("Food cost % (portfolio)", portfolio_food, TARGET_FOOD_COST_PORTFOLIO),
        TargetRow("Labor cost % (portfolio)", portfolio_labor, TARGET_LABOR_COST_PORTFOLIO),
        TargetRow("Food cost % (store-level cap)", None, TARGET_FOOD_COST_STORE),
        TargetRow("Labor cost % (store-level cap)", None, TARGET_LABOR_COST_STORE),
    )


def _collect_digest_data(week_end: date) -> DigestData:
    """Load every row the renderer needs for ``week_end``.

    Splits the read into one round-trip per logical block so the SQL
    stays simple. A digest send happens once a week against the free-tier
    Supabase instance — query count beats query complexity.
    """
    prior_week_end = week_end - timedelta(days=7)
    week_start, _ = business_week_of(week_end)

    engine = get_engine()
    with engine.connect() as conn:
        portfolio_now = conn.execute(
            text(
                """
                SELECT
                    SUM(net_sales_total) AS net_sales,
                    SUM(transactions_total) AS transactions,
                    CASE
                        WHEN SUM(net_sales_total)
                             FILTER (WHERE food_cost_actual_pct IS NOT NULL) > 0
                        THEN SUM(food_cost_actual_pct * net_sales_total)
                             / SUM(net_sales_total)
                               FILTER (WHERE food_cost_actual_pct IS NOT NULL)
                        ELSE NULL
                    END AS food_cost_pct,
                    CASE
                        WHEN SUM(net_sales_total)
                             FILTER (WHERE labor_cost_pct IS NOT NULL) > 0
                        THEN SUM(labor_cost_pct * net_sales_total)
                             / SUM(net_sales_total)
                               FILTER (WHERE labor_cost_pct IS NOT NULL)
                        ELSE NULL
                    END AS labor_cost_pct
                FROM mart_store_weekly
                WHERE week_end_date = :w
                """
            ),
            {"w": week_end},
        ).first()
        portfolio_prior = conn.execute(
            text(
                """
                SELECT
                    SUM(net_sales_total) AS net_sales,
                    SUM(transactions_total) AS transactions,
                    CASE
                        WHEN SUM(net_sales_total)
                             FILTER (WHERE food_cost_actual_pct IS NOT NULL) > 0
                        THEN SUM(food_cost_actual_pct * net_sales_total)
                             / SUM(net_sales_total)
                               FILTER (WHERE food_cost_actual_pct IS NOT NULL)
                        ELSE NULL
                    END AS food_cost_pct,
                    CASE
                        WHEN SUM(net_sales_total)
                             FILTER (WHERE labor_cost_pct IS NOT NULL) > 0
                        THEN SUM(labor_cost_pct * net_sales_total)
                             / SUM(net_sales_total)
                               FILTER (WHERE labor_cost_pct IS NOT NULL)
                        ELSE NULL
                    END AS labor_cost_pct
                FROM mart_store_weekly
                WHERE week_end_date = :w
                """
            ),
            {"w": prior_week_end},
        ).first()

        store_rows_raw = conn.execute(
            text(
                """
                SELECT
                    w.restaurant_number,
                    s.store_name,
                    s.field_manager_name,
                    w.net_sales_total,
                    w.transactions_total,
                    w.food_cost_actual_pct,
                    w.labor_cost_pct,
                    w.cash_overshort_total,
                    w.is_food_cost_in_target,
                    w.is_labor_cost_in_target
                FROM mart_store_weekly w
                JOIN ref_stores s ON s.store_number = w.restaurant_number
                WHERE w.week_end_date = :w
                ORDER BY w.restaurant_number
                """
            ),
            {"w": week_end},
        ).all()

        recon_rows = conn.execute(
            text(
                """
                SELECT
                    r.restaurant_number,
                    s.store_name,
                    r.variance,
                    r.status
                FROM mart_recon_weekly r
                JOIN ref_stores s ON s.store_number = r.restaurant_number
                WHERE r.week_end_date = :w
                """
            ),
            {"w": week_end},
        ).all()

        fm_rows = conn.execute(
            text(
                """
                SELECT
                    field_manager_name,
                    store_count,
                    total_net_sales_weighted,
                    portfolio_food_cost_pct,
                    portfolio_labor_cost_pct,
                    is_food_cost_in_portfolio_target,
                    is_labor_cost_in_portfolio_target
                FROM mart_field_manager_portfolio
                WHERE week_end_date = :w
                ORDER BY field_manager_name
                """
            ),
            {"w": week_end},
        ).all()

    stores = tuple(
        StoreRow(
            store_number=str(r.restaurant_number),
            store_name=str(r.store_name),
            field_manager_name=(
                str(r.field_manager_name) if r.field_manager_name is not None else None
            ),
            net_sales=r.net_sales_total,
            transactions=r.transactions_total,
            food_cost_pct=r.food_cost_actual_pct,
            labor_cost_pct=r.labor_cost_pct,
            cash_overshort=r.cash_overshort_total,
            is_food_cost_in_target=r.is_food_cost_in_target,
            is_labor_cost_in_target=r.is_labor_cost_in_target,
        )
        for r in store_rows_raw
    )

    counts: dict[str, int] = {}
    escalated: list[ReconCase] = []
    for r in recon_rows:
        status = str(r.status)
        counts[status] = counts.get(status, 0) + 1
        if status == "escalated" and r.variance is not None:
            escalated.append(
                ReconCase(
                    store_number=str(r.restaurant_number),
                    store_name=str(r.store_name),
                    variance=r.variance,
                    status=status,
                )
            )

    # Sort escalated by absolute variance descending (worst first).
    escalated.sort(key=lambda c: abs(c.variance), reverse=True)

    fm_rollups: list[FMRollup] = []
    for r in fm_rows:
        fm_name = str(r.field_manager_name)
        fm_rollups.append(
            FMRollup(
                field_manager_name=fm_name,
                store_count=int(r.store_count),
                net_sales=r.total_net_sales_weighted,
                food_cost_pct=r.portfolio_food_cost_pct,
                labor_cost_pct=r.portfolio_labor_cost_pct,
                is_food_cost_in_portfolio_target=r.is_food_cost_in_portfolio_target,
                is_labor_cost_in_portfolio_target=r.is_labor_cost_in_portfolio_target,
                stores=tuple(
                    s for s in stores if s.field_manager_name == fm_name
                ),
            )
        )

    portfolio = PortfolioSnapshot(
        net_sales=portfolio_now.net_sales if portfolio_now is not None else None,
        transactions=(
            int(portfolio_now.transactions)
            if portfolio_now is not None and portfolio_now.transactions is not None
            else None
        ),
        food_cost_pct=portfolio_now.food_cost_pct if portfolio_now is not None else None,
        labor_cost_pct=portfolio_now.labor_cost_pct if portfolio_now is not None else None,
        prior_net_sales=portfolio_prior.net_sales if portfolio_prior is not None else None,
        prior_transactions=(
            int(portfolio_prior.transactions)
            if portfolio_prior is not None and portfolio_prior.transactions is not None
            else None
        ),
        prior_food_cost_pct=(
            portfolio_prior.food_cost_pct if portfolio_prior is not None else None
        ),
        prior_labor_cost_pct=(
            portfolio_prior.labor_cost_pct if portfolio_prior is not None else None
        ),
    )

    feedback = settings.alert_email or _DEFAULT_FEEDBACK
    return DigestData(
        week_end=week_end,
        week_start=week_start,
        portfolio=portfolio,
        targets=_default_targets(portfolio.food_cost_pct, portfolio.labor_cost_pct),
        recon=ReconSummary(
            counts_by_status=counts,
            escalated_cases=tuple(escalated),
        ),
        fm_rollups=tuple(fm_rollups),
        stores=stores,
        dashboard_url=settings.dashboard_url,
        feedback_email=feedback,
    )


def build_digest(week_end: date | None = None) -> tuple[str, str]:
    """Build the weekly digest for ``week_end`` (defaults to the just-closed
    Tuesday).

    Returns ``(subject, html_body)``. Side-effect free: reads from the
    marts but writes nothing. Failure modes bubble up so the sender in
    Task 5.4 can wrap the whole call in ``track_job(...)``.
    """
    if week_end is None:
        _, week_end = previous_business_week()
    log.info("build_digest_start", week_end=str(week_end))
    data = _collect_digest_data(week_end)
    subject, body = render_digest(data)
    log.info(
        "build_digest_done",
        week_end=str(week_end),
        flagged=data.flagged_count,
        escalated=data.escalated_count,
        bytes=len(body),
    )
    return subject, body
