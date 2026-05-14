"""Backfill audit — spot-check 12 months of history against LiveIQ.

Produces a Markdown audit report at ``docs/audit_<YYYY-MM-DD>.md``
with three sections:

1. **Sampled cross-checks.** Five randomly-sampled
   ``(store, week_end_date)`` pairs with
   ``stg_controlsheet_weekly.net_sales_total`` and a hint string for
   the operator to open the matching LiveIQ ControlSheet report. The
   LiveIQ URL is not deterministically constructable from outside the
   portal, so the script prints navigation instructions instead.
2. **Daily-mart coverage.** Expected cell count = active stores x
   days in window, vs actual cells in ``mart_store_daily``. Any
   deficit lists the specific ``(store, date)`` gaps (capped to the
   first 50 for readability).
3. **Weekly-mart coverage.** Same idea against ``mart_store_weekly``
   (active stores x Tuesdays in window). Plus a "zero-sales days"
   side report so the operator can distinguish data gaps from real
   closures.

The script is **read-only** — it never writes to the marts. Wrap the
run in ``track_job("audit_backfill")`` so each invocation is logged
to ``ops_job_runs`` for the system-status page.

Usage:

    uv run python scripts/audit_backfill.py
    uv run python scripts/audit_backfill.py --window-days 90 \\
        --sample-size 3
"""

from __future__ import annotations

import argparse
import random
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import structlog
from sqlalchemy import text

from subway_ops.calendar import previous_business_week
from subway_ops.db.connection import get_engine
from subway_ops.db.job_runs import track_job
from subway_ops.observability import configure_logging

JOB_NAME = "audit_backfill"
DEFAULT_WINDOW_DAYS = 365
DEFAULT_SAMPLE_SIZE = 5
MAX_GAP_LIST = 50  # cap the per-section gap printout

REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIT_DIR = REPO_ROOT / "docs"

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SampleRow:
    """One sampled (store, week_end) pair for manual cross-check."""

    store_number: str
    store_name: str
    week_end_date: date
    net_sales_total: float | None


@dataclass(frozen=True)
class CoverageReport:
    """Coverage stats for one mart over the audit window."""

    expected_cells: int
    actual_cells: int
    missing_cells: tuple[tuple[str, date], ...]


@dataclass(frozen=True)
class AuditReport:
    """Everything the rendered markdown needs."""

    generated_at: datetime
    window_start: date
    window_end: date
    sample: tuple[SampleRow, ...]
    daily_coverage: CoverageReport
    weekly_coverage: CoverageReport
    zero_sales_days: tuple[tuple[str, date], ...]
    active_stores: int
    stores_with_opening_date: int
    notes: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Pure helpers — testable without a live DB
# ---------------------------------------------------------------------------


def expected_daily_cells(
    stores: list[tuple[str, date | None]],
    window_start: date,
    window_end: date,
) -> dict[str, set[date]]:
    """Build the expected ``store → {business_date}`` set.

    A store contributes a date only if its ``opening_date`` is on or
    before that date (when the field is set). Stores with no
    ``opening_date`` are assumed to have always existed in-window —
    that's the safer assumption for an audit that's trying to surface
    gaps, not hide them.
    """
    days_in_window: list[date] = []
    cursor = window_start
    while cursor <= window_end:
        days_in_window.append(cursor)
        cursor += timedelta(days=1)
    out: dict[str, set[date]] = {}
    for store, opened in stores:
        if opened is None:
            out[store] = set(days_in_window)
            continue
        out[store] = {d for d in days_in_window if d >= opened}
    return out


def expected_weekly_cells(
    stores: list[tuple[str, date | None]],
    window_start: date,
    window_end: date,
) -> dict[str, set[date]]:
    """Same as ``expected_daily_cells`` but for Tuesday week-ends.

    A Tuesday counts as expected for a store only if the *whole* week
    falls inside the audit window AND the store was open on or before
    that Tuesday (when ``opening_date`` is set).
    """
    tuesdays: list[date] = []
    cursor = window_start
    # Walk forward to the first Tuesday on/after window_start, then
    # step by 7 days through window_end.
    delta = (1 - cursor.weekday()) % 7  # weekday(): Mon=0..Sun=6, Tue=1
    cursor = cursor + timedelta(days=delta)
    while cursor <= window_end:
        tuesdays.append(cursor)
        cursor += timedelta(days=7)
    out: dict[str, set[date]] = {}
    for store, opened in stores:
        if opened is None:
            out[store] = set(tuesdays)
            continue
        out[store] = {t for t in tuesdays if t >= opened}
    return out


def compute_coverage(
    expected: dict[str, set[date]], actual: set[tuple[str, date]]
) -> CoverageReport:
    """Diff expected vs actual cells. Missing list is sorted + capped."""
    expected_pairs = {(s, d) for s, days in expected.items() for d in days}
    missing = sorted(expected_pairs - actual)
    return CoverageReport(
        expected_cells=len(expected_pairs),
        actual_cells=len(actual),
        missing_cells=tuple(missing[:MAX_GAP_LIST]),
    )


def sample_pairs(
    pairs: list[tuple[str, date, str, float | None]],
    n: int,
    *,
    rng: random.Random | None = None,
) -> list[tuple[str, date, str, float | None]]:
    """Random sample of ``(store, week_end, store_name, net_sales)`` tuples.

    Pulled out as a pure function so tests can pin the rng seed and
    assert the exact sample picked.
    """
    if n <= 0 or not pairs:
        return []
    r = rng or random.Random()
    return r.sample(pairs, min(n, len(pairs)))


def liveiq_hint(store_number: str, week_end: date) -> str:
    """Operator-facing instruction to open the matching LiveIQ report.

    LiveIQ doesn't expose a deterministic deep-link the audit can
    construct; the playbook's fallback is a plain-English navigation
    hint. The script prints this so the operator can open one tab and
    eyeball the numbers.
    """
    return (
        f"Open LiveIQ → Reporting → ControlSheet for store {store_number}, "
        f"week ending {week_end:%Y-%m-%d}"
    )


# ---------------------------------------------------------------------------
# DB helpers — wrapped thin so the pure code above stays unit-testable
# ---------------------------------------------------------------------------


def _fetch_active_stores() -> list[tuple[str, date | None]]:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT store_number, opening_date FROM ref_stores "
                "WHERE is_active = true ORDER BY store_number"
            )
        ).all()
    return [(str(r[0]), r[1]) for r in rows]


def _fetch_actual_daily(window_start: date, window_end: date) -> set[tuple[str, date]]:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT restaurant_number, business_date FROM mart_store_daily "
                "WHERE business_date BETWEEN :s AND :e"
            ),
            {"s": window_start, "e": window_end},
        ).all()
    return {(str(r[0]), r[1]) for r in rows}


def _fetch_actual_weekly(window_start: date, window_end: date) -> set[tuple[str, date]]:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT restaurant_number, week_end_date FROM mart_store_weekly "
                "WHERE week_end_date BETWEEN :s AND :e"
            ),
            {"s": window_start, "e": window_end},
        ).all()
    return {(str(r[0]), r[1]) for r in rows}


def _fetch_zero_sales_days(
    window_start: date, window_end: date
) -> list[tuple[str, date]]:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT restaurant_number, business_date
                FROM mart_store_daily
                WHERE business_date BETWEEN :s AND :e
                  AND (net_sales IS NULL OR net_sales = 0)
                ORDER BY restaurant_number, business_date
                """
            ),
            {"s": window_start, "e": window_end},
        ).all()
    return [(str(r[0]), r[1]) for r in rows]


def _fetch_controlsheet_pairs(
    window_start: date, window_end: date
) -> list[tuple[str, date, str, float | None]]:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT cs.restaurant_number,
                       cs.week_end_date,
                       s.store_name,
                       cs.net_sales
                FROM stg_controlsheet_weekly cs
                JOIN ref_stores s ON s.store_number = cs.restaurant_number
                WHERE cs.week_end_date BETWEEN :s AND :e
                ORDER BY cs.restaurant_number, cs.week_end_date
                """
            ),
            {"s": window_start, "e": window_end},
        ).all()
    return [
        (str(r[0]), r[1], str(r[2]), float(r[3]) if r[3] is not None else None)
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Top-level driver
# ---------------------------------------------------------------------------


def run_audit(
    *,
    window_days: int = DEFAULT_WINDOW_DAYS,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    today: date | None = None,
    rng: random.Random | None = None,
) -> AuditReport:
    """Compose every piece of the audit into an ``AuditReport``.

    The DB-touching helpers (``_fetch_*``) are import-level so a test
    can monkey-patch them; the body here is pure orchestration.
    """
    today = today or date.today()
    _, last_closed = previous_business_week(today)
    window_end = last_closed
    window_start = window_end - timedelta(days=window_days - 1)

    log.info(
        "audit_backfill_plan",
        window_start=str(window_start),
        window_end=str(window_end),
        sample_size=sample_size,
    )

    stores = _fetch_active_stores()
    stores_with_opening = sum(1 for _, o in stores if o is not None)

    expected_daily = expected_daily_cells(stores, window_start, window_end)
    expected_weekly = expected_weekly_cells(stores, window_start, window_end)
    actual_daily = _fetch_actual_daily(window_start, window_end)
    actual_weekly = _fetch_actual_weekly(window_start, window_end)
    daily_cov = compute_coverage(expected_daily, actual_daily)
    weekly_cov = compute_coverage(expected_weekly, actual_weekly)

    cs_pairs = _fetch_controlsheet_pairs(window_start, window_end)
    chosen = sample_pairs(cs_pairs, sample_size, rng=rng)
    sample = tuple(
        SampleRow(
            store_number=p[0],
            store_name=p[2],
            week_end_date=p[1],
            net_sales_total=p[3],
        )
        for p in chosen
    )

    zero_days_full = _fetch_zero_sales_days(window_start, window_end)
    zero_days = tuple(zero_days_full[:MAX_GAP_LIST])

    notes: list[str] = []
    if not stores:
        notes.append(
            "No active rows in ref_stores; audit is meaningless. "
            "Run scripts/seed_reference.py first."
        )
    if not cs_pairs:
        notes.append(
            "stg_controlsheet_weekly is empty for the audit window — "
            "Phase 2 ingest hasn't loaded the ControlSheet endpoint yet, "
            "or the backfill never ran. Sample section will be empty."
        )

    return AuditReport(
        generated_at=datetime.now().astimezone(),
        window_start=window_start,
        window_end=window_end,
        sample=sample,
        daily_coverage=daily_cov,
        weekly_coverage=weekly_cov,
        zero_sales_days=zero_days,
        active_stores=len(stores),
        stores_with_opening_date=stores_with_opening,
        notes=tuple(notes),
    )


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def _fmt_money(v: float | None) -> str:
    if v is None:
        return "—"
    return f"${v:,.2f}"


def _render_header(report: AuditReport) -> list[str]:
    return [
        f"# Backfill audit — {report.generated_at:%Y-%m-%d}",
        "",
        (
            f"Window: **{report.window_start:%Y-%m-%d}** -> "
            f"**{report.window_end:%Y-%m-%d}** "
            f"({(report.window_end - report.window_start).days + 1} days)."
        ),
        (
            f"Active stores at audit time: **{report.active_stores}** "
            f"({report.stores_with_opening_date} with an `opening_date` set)."
        ),
        "",
    ]


def _render_notes(report: AuditReport) -> list[str]:
    if not report.notes:
        return []
    out = ["## Notes", ""]
    out.extend(f"- {n}" for n in report.notes)
    out.append("")
    return out


def _render_sample_section(report: AuditReport) -> list[str]:
    out = ["## 1. Sampled (store, week) cross-checks", ""]
    if not report.sample:
        out.extend(["_No ControlSheet rows available — sample skipped._", ""])
        return out
    out.extend(
        [
            "Open LiveIQ in one tab and the numbers below in another; "
            "eyeball the matches.",
            "",
            "| # | Store | Name | Week ending | `net_sales` | LiveIQ |",
            "|---|-------|------|-------------|-------------|--------|",
        ]
    )
    for i, s in enumerate(report.sample, start=1):
        hint = liveiq_hint(s.store_number, s.week_end_date)
        out.append(
            f"| {i} | {s.store_number} | {s.store_name} | "
            f"{s.week_end_date:%Y-%m-%d} | "
            f"{_fmt_money(s.net_sales_total)} | {hint} |"
        )
    out.append("")
    return out


def _render_coverage_section(
    *,
    title: str,
    cov: CoverageReport,
    summary_extra: str,
    missing_header: str,
    missing_cols: tuple[str, str],
    empty_message: str,
) -> list[str]:
    out = [f"## {title}", ""]
    out.append(
        f"Expected cells{summary_extra}: **{cov.expected_cells:,}**. "
        f"Actual: **{cov.actual_cells:,}**. "
        f"Missing: **{cov.expected_cells - cov.actual_cells:,}**."
    )
    out.append("")
    if not cov.missing_cells:
        out.extend([empty_message, ""])
        return out
    capped = (
        f" (first {MAX_GAP_LIST} shown)"
        if cov.expected_cells - cov.actual_cells > MAX_GAP_LIST
        else ""
    )
    left, right = missing_cols
    out.extend(
        [
            f"### {missing_header}{capped}",
            "",
            f"| {left} | {right} |",
            f"|{'-' * (len(left) + 2)}|{'-' * (len(right) + 2)}|",
        ]
    )
    for store, d in cov.missing_cells:
        out.append(f"| {store} | {d:%Y-%m-%d} |")
    out.append("")
    return out


def render_markdown(report: AuditReport) -> str:
    """Render the audit dataclass as a self-contained Markdown doc."""
    lines: list[str] = []
    lines.extend(_render_header(report))
    lines.extend(_render_notes(report))
    lines.extend(_render_sample_section(report))
    lines.extend(
        _render_coverage_section(
            title="2. Daily mart coverage",
            cov=report.daily_coverage,
            summary_extra="",
            missing_header="Missing daily cells",
            missing_cols=("Store", "Business date"),
            empty_message="_No missing daily cells in window._",
        )
    )
    lines.extend(
        _render_coverage_section(
            title="3. Weekly mart coverage",
            cov=report.weekly_coverage,
            summary_extra=" (active stores x Tuesdays)",
            missing_header="Missing weekly cells",
            missing_cols=("Store", "Week ending"),
            empty_message="_No missing weekly cells in window._",
        )
    )

    # Section 4 — zero-sales days (auxiliary, not a gap)
    lines.append("## 4. Zero-sales days")
    lines.append("")
    lines.append(
        "These rows _exist_ in `mart_store_daily` but report no sales. "
        "Cross-reference `ref_stores.opening_date` and `is_active` — most "
        "of these are real closures (holidays, brand-new stores still "
        "ramping), but persistent zero-sales for an open store points at "
        "an ingest gap."
    )
    lines.append("")
    if report.zero_sales_days:
        capped = (
            f" (first {MAX_GAP_LIST} shown)"
            if len(report.zero_sales_days) >= MAX_GAP_LIST
            else ""
        )
        lines.append(f"### Zero-sales rows{capped}")
        lines.append("")
        lines.append("| Store | Business date |")
        lines.append("|-------|---------------|")
        for store, d in report.zero_sales_days:
            lines.append(f"| {store} | {d:%Y-%m-%d} |")
        lines.append("")
    else:
        lines.append("_No zero-sales rows in window._")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        f"Generated by `scripts/audit_backfill.py` at "
        f"{report.generated_at.isoformat(timespec='seconds')}."
    )
    return "\n".join(lines)


def write_audit_file(markdown: str, *, today: date) -> Path:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    out = AUDIT_DIR / f"audit_{today.isoformat()}.md"
    out.write_text(markdown)
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--window-days",
        type=int,
        default=DEFAULT_WINDOW_DAYS,
        help=f"Audit lookback window (default: {DEFAULT_WINDOW_DAYS}).",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=DEFAULT_SAMPLE_SIZE,
        help=f"Number of cross-check samples (default: {DEFAULT_SAMPLE_SIZE}).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help=(
            "Override the output Markdown path. Defaults to "
            "docs/audit_<YYYY-MM-DD>.md."
        ),
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Seed the sample RNG so reruns pick identical rows.",
    )
    args = parser.parse_args(argv)

    configure_logging()

    rng = random.Random(args.seed) if args.seed is not None else None
    today = date.today()

    with track_job(JOB_NAME) as meta:
        report = run_audit(
            window_days=args.window_days,
            sample_size=args.sample_size,
            today=today,
            rng=rng,
        )
        meta.update(
            {
                "window_start": report.window_start.isoformat(),
                "window_end": report.window_end.isoformat(),
                "active_stores": report.active_stores,
                "expected_daily_cells": report.daily_coverage.expected_cells,
                "actual_daily_cells": report.daily_coverage.actual_cells,
                "missing_daily_cells": (
                    report.daily_coverage.expected_cells
                    - report.daily_coverage.actual_cells
                ),
                "expected_weekly_cells": report.weekly_coverage.expected_cells,
                "actual_weekly_cells": report.weekly_coverage.actual_cells,
                "missing_weekly_cells": (
                    report.weekly_coverage.expected_cells
                    - report.weekly_coverage.actual_cells
                ),
                "zero_sales_rows": len(report.zero_sales_days),
                "rows_written": 0,
            }
        )
        markdown = render_markdown(report)
        out_path = args.out or AUDIT_DIR / f"audit_{today.isoformat()}.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(markdown)

    summary = (
        f"Audit written to {out_path}. "
        f"Daily coverage {report.daily_coverage.actual_cells:,}/"
        f"{report.daily_coverage.expected_cells:,}; "
        f"weekly coverage {report.weekly_coverage.actual_cells:,}/"
        f"{report.weekly_coverage.expected_cells:,}; "
        f"sample rows {len(report.sample)}."
    )
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
