"""Tests for ``scripts/audit_backfill``.

The DB-touching helpers (``_fetch_*``) are stubbed via monkey-patch so
the test never opens a Postgres connection. The pure helpers
(``expected_daily_cells`` / ``expected_weekly_cells`` /
``compute_coverage`` / ``sample_pairs`` / ``render_markdown``) are
exercised directly.
"""

from __future__ import annotations

import random
from datetime import date, datetime
from pathlib import Path

import pytest

from scripts import audit_backfill as ab
from scripts.audit_backfill import (
    AuditReport,
    CoverageReport,
    SampleRow,
    compute_coverage,
    expected_daily_cells,
    expected_weekly_cells,
    liveiq_hint,
    render_markdown,
    run_audit,
    sample_pairs,
)

# ---------------------------------------------------------------------------
# expected_daily_cells / expected_weekly_cells
# ---------------------------------------------------------------------------


def test_expected_daily_cells_no_opening_date_means_full_window() -> None:
    """A store without an ``opening_date`` is assumed to have always
    existed in-window — the safer assumption for gap discovery."""
    out = expected_daily_cells(
        [("4092", None)],
        window_start=date(2026, 5, 1),
        window_end=date(2026, 5, 7),
    )
    assert len(out["4092"]) == 7
    assert date(2026, 5, 1) in out["4092"]
    assert date(2026, 5, 7) in out["4092"]


def test_expected_daily_cells_clips_at_opening_date() -> None:
    """A store with a later opening_date contributes only days from
    that date forward."""
    out = expected_daily_cells(
        [("4092", date(2026, 5, 4))],
        window_start=date(2026, 5, 1),
        window_end=date(2026, 5, 7),
    )
    assert out["4092"] == {date(2026, 5, d) for d in range(4, 8)}


def test_expected_weekly_cells_only_picks_tuesdays() -> None:
    out = expected_weekly_cells(
        [("4092", None)],
        window_start=date(2026, 4, 27),  # Monday
        window_end=date(2026, 5, 12),    # Tuesday
    )
    tuesdays = sorted(out["4092"])
    # 2026-04-28, 2026-05-05, 2026-05-12 are Tuesdays in window.
    assert tuesdays == [date(2026, 4, 28), date(2026, 5, 5), date(2026, 5, 12)]


def test_expected_weekly_cells_clips_at_opening_date() -> None:
    out = expected_weekly_cells(
        [("4092", date(2026, 5, 5))],
        window_start=date(2026, 4, 27),
        window_end=date(2026, 5, 12),
    )
    assert out["4092"] == {date(2026, 5, 5), date(2026, 5, 12)}


# ---------------------------------------------------------------------------
# compute_coverage
# ---------------------------------------------------------------------------


def test_compute_coverage_full_match() -> None:
    expected = {"4092": {date(2026, 5, 1), date(2026, 5, 2)}}
    actual = {("4092", date(2026, 5, 1)), ("4092", date(2026, 5, 2))}
    cov = compute_coverage(expected, actual)
    assert cov.expected_cells == 2
    assert cov.actual_cells == 2
    assert cov.missing_cells == ()


def test_compute_coverage_lists_missing_in_sorted_order() -> None:
    expected = {
        "4092": {date(2026, 5, 1), date(2026, 5, 2)},
        "17967": {date(2026, 5, 1)},
    }
    actual: set[tuple[str, date]] = set()  # nothing landed
    cov = compute_coverage(expected, actual)
    assert cov.expected_cells == 3
    assert cov.actual_cells == 0
    # Sorted: ("17967", 2026-05-01), ("4092", 2026-05-01), ("4092", 2026-05-02)
    assert cov.missing_cells == (
        ("17967", date(2026, 5, 1)),
        ("4092", date(2026, 5, 1)),
        ("4092", date(2026, 5, 2)),
    )


def test_compute_coverage_caps_missing_list() -> None:
    """``MAX_GAP_LIST`` keeps the audit doc readable."""
    expected = {
        "X": {date(2026, 1, 1) + __import__("datetime").timedelta(days=i) for i in range(200)},
    }
    cov = compute_coverage(expected, set())
    assert cov.expected_cells == 200
    assert len(cov.missing_cells) == ab.MAX_GAP_LIST


# ---------------------------------------------------------------------------
# sample_pairs
# ---------------------------------------------------------------------------


def test_sample_pairs_respects_n_and_seed() -> None:
    rows = [
        ("4092", date(2026, 5, 5), "Bothell", 6500.0),
        ("17967", date(2026, 5, 5), "Kirkland", 7100.0),
        ("26529", date(2026, 5, 5), "Issaquah", 5800.0),
    ]
    chosen_a = sample_pairs(rows, 2, rng=random.Random(42))
    chosen_b = sample_pairs(rows, 2, rng=random.Random(42))
    # Same seed → same picks.
    assert chosen_a == chosen_b
    assert len(chosen_a) == 2


def test_sample_pairs_zero_or_negative_returns_empty() -> None:
    rows = [("4092", date(2026, 5, 5), "Bothell", 6500.0)]
    assert sample_pairs(rows, 0) == []
    assert sample_pairs(rows, -3) == []


def test_sample_pairs_caps_at_population_size() -> None:
    rows = [("4092", date(2026, 5, 5), "Bothell", 6500.0)]
    chosen = sample_pairs(rows, 99, rng=random.Random(1))
    assert len(chosen) == 1


def test_sample_pairs_empty_population() -> None:
    assert sample_pairs([], 5) == []


def test_liveiq_hint_includes_store_and_week() -> None:
    h = liveiq_hint("4092", date(2026, 5, 5))
    assert "4092" in h
    assert "2026-05-05" in h
    assert "LiveIQ" in h


# ---------------------------------------------------------------------------
# render_markdown
# ---------------------------------------------------------------------------


def _build_report(**overrides: object) -> AuditReport:
    defaults: dict[str, object] = {
        "generated_at": datetime(2026, 5, 13, 10, 0, 0),
        "window_start": date(2025, 5, 13),
        "window_end": date(2026, 5, 5),
        "sample": (
            SampleRow("4092", "Bothell", date(2026, 5, 5), 6500.0),
            SampleRow("17967", "Kirkland", date(2026, 4, 28), None),
        ),
        "daily_coverage": CoverageReport(
            expected_cells=14 * 365,
            actual_cells=14 * 365,
            missing_cells=(),
        ),
        "weekly_coverage": CoverageReport(
            expected_cells=14 * 52,
            actual_cells=14 * 52 - 3,
            missing_cells=(
                ("4092", date(2025, 6, 3)),
                ("17967", date(2025, 6, 3)),
                ("26529", date(2025, 6, 3)),
            ),
        ),
        "zero_sales_days": (("4092", date(2026, 1, 1)),),
        "active_stores": 14,
        "stores_with_opening_date": 14,
        "notes": (),
    }
    defaults.update(overrides)
    return AuditReport(**defaults)  # type: ignore[arg-type]


def test_render_markdown_contains_section_headers() -> None:
    md = render_markdown(_build_report())
    assert "# Backfill audit" in md
    assert "## 1. Sampled (store, week) cross-checks" in md
    assert "## 2. Daily mart coverage" in md
    assert "## 3. Weekly mart coverage" in md
    assert "## 4. Zero-sales days" in md


def test_render_markdown_includes_each_sample_row() -> None:
    md = render_markdown(_build_report())
    assert "Bothell" in md
    assert "Kirkland" in md
    # Money is rendered with $; the None row falls back to the em-dash.
    assert "$6,500.00" in md
    assert "| — |" in md
    # The LiveIQ hint shows up alongside each row.
    assert "Open LiveIQ" in md


def test_render_markdown_flags_missing_weekly_cells() -> None:
    md = render_markdown(_build_report())
    # Missing-cells table renders the gap rows.
    assert "| 4092 | 2025-06-03 |" in md
    assert "| 17967 | 2025-06-03 |" in md
    # And the section banner shows the count.
    assert "Missing: **3**" in md


def test_render_markdown_handles_empty_sample() -> None:
    md = render_markdown(_build_report(sample=()))
    assert "_No ControlSheet rows available — sample skipped._" in md


def test_render_markdown_renders_notes() -> None:
    md = render_markdown(
        _build_report(
            notes=("ControlSheet table is empty for the audit window.",)
        )
    )
    assert "## Notes" in md
    assert "ControlSheet table is empty" in md


def test_render_markdown_clean_state_messages() -> None:
    """Clean coverage → 'no missing cells' banners replace the tables."""
    report = _build_report(
        daily_coverage=CoverageReport(
            expected_cells=10, actual_cells=10, missing_cells=()
        ),
        weekly_coverage=CoverageReport(
            expected_cells=5, actual_cells=5, missing_cells=()
        ),
        zero_sales_days=(),
    )
    md = render_markdown(report)
    assert "_No missing daily cells in window._" in md
    assert "_No missing weekly cells in window._" in md
    assert "_No zero-sales rows in window._" in md


# ---------------------------------------------------------------------------
# run_audit — orchestrator with mocked DB helpers
# ---------------------------------------------------------------------------


def _patch_db(
    monkeypatch: pytest.MonkeyPatch,
    *,
    stores: list[tuple[str, date | None]] | None = None,
    actual_daily: set[tuple[str, date]] | None = None,
    actual_weekly: set[tuple[str, date]] | None = None,
    zero_sales: list[tuple[str, date]] | None = None,
    controlsheet: list[tuple[str, date, str, float | None]] | None = None,
) -> None:
    monkeypatch.setattr(
        ab, "_fetch_active_stores", lambda: stores or []
    )
    monkeypatch.setattr(
        ab, "_fetch_actual_daily", lambda *_a, **_k: actual_daily or set()
    )
    monkeypatch.setattr(
        ab, "_fetch_actual_weekly", lambda *_a, **_k: actual_weekly or set()
    )
    monkeypatch.setattr(
        ab, "_fetch_zero_sales_days", lambda *_a, **_k: zero_sales or []
    )
    monkeypatch.setattr(
        ab, "_fetch_controlsheet_pairs", lambda *_a, **_k: controlsheet or []
    )


def test_run_audit_assembles_a_full_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    today = date(2026, 5, 13)  # Wednesday
    # previous_business_week(2026-05-13) → week ending 2026-05-12 (Tue).
    _patch_db(
        monkeypatch,
        stores=[("4092", None), ("17967", date(2026, 1, 1))],
        actual_daily=set(),
        actual_weekly=set(),
        zero_sales=[("4092", date(2026, 5, 1))],
        controlsheet=[
            ("4092", date(2026, 5, 5), "Bothell", 6500.0),
            ("17967", date(2026, 5, 5), "Kirkland", 7100.0),
        ],
    )
    report = run_audit(
        window_days=7,
        sample_size=2,
        today=today,
        rng=random.Random(0),
    )
    assert report.active_stores == 2
    assert report.stores_with_opening_date == 1
    assert len(report.sample) == 2
    assert report.daily_coverage.expected_cells > 0
    assert report.daily_coverage.actual_cells == 0
    assert "Bothell" in {s.store_name for s in report.sample}


def test_run_audit_emits_note_when_no_active_stores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_db(monkeypatch, stores=[])
    report = run_audit(window_days=7, sample_size=2, today=date(2026, 5, 13))
    assert any("No active rows in ref_stores" in n for n in report.notes)
    assert report.active_stores == 0


def test_run_audit_emits_note_when_no_controlsheet_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_db(
        monkeypatch,
        stores=[("4092", None)],
        controlsheet=[],
    )
    report = run_audit(window_days=7, sample_size=2, today=date(2026, 5, 13))
    assert any("stg_controlsheet_weekly is empty" in n for n in report.notes)
    assert report.sample == ()


def test_run_audit_window_anchors_on_previous_business_week(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_db(monkeypatch, stores=[("4092", None)])
    # Friday 2026-05-15 → previous business week ends Tuesday 2026-05-12.
    report = run_audit(
        window_days=7,
        sample_size=0,
        today=date(2026, 5, 15),
    )
    assert report.window_end == date(2026, 5, 12)
    # 7-day window inclusive of end → start is 6 days earlier.
    assert report.window_start == date(2026, 5, 6)


# ---------------------------------------------------------------------------
# write_audit_file — sanity check the path naming
# ---------------------------------------------------------------------------


def test_write_audit_file_uses_iso_today(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ab, "AUDIT_DIR", tmp_path)
    out = ab.write_audit_file("# hi", today=date(2026, 5, 13))
    assert out == tmp_path / "audit_2026-05-13.md"
    assert out.read_text() == "# hi"
