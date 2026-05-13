"""Tests for ``subway_ops.digest.builder``.

The renderer is a pure function: dataclass in, ``(subject, html_body)``
out. We build a synthetic ``DigestData`` covering every status bucket
(green/yellow/red/unknown) and exercise the renderer; assertions stay
focused on substrings the digest CONTRACT promises rather than on the
exact byte layout so non-load-bearing markup tweaks don't churn the
suite.

A separate snapshot test guards rendering stability: render the same
fixture twice and confirm byte-equality. The snapshot file lives next
to the test so changes are reviewed in PR.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

import pytest

from subway_ops.digest.builder import (
    COLOR_GREEN,
    COLOR_RED,
    COLOR_YELLOW,
    DigestData,
    FMRollup,
    PortfolioSnapshot,
    ReconCase,
    ReconSummary,
    StoreRow,
    TargetRow,
    _bucket_color,
    _bucket_pct,
    _default_targets,
    _fmt_money,
    _fmt_money_signed,
    _fmt_pct,
    _fmt_pp_delta,
    _money_delta_color,
    _pct_delta_color,
    render_digest,
)

# ---------------------------------------------------------------------------
# Pure-helper tests
# ---------------------------------------------------------------------------


def test_fmt_money_handles_none() -> None:
    assert _fmt_money(None) == "—"
    assert _fmt_money(Decimal("1234.56")) == "$1,235"


def test_fmt_money_signed() -> None:
    assert _fmt_money_signed(Decimal("0")) == "$0"
    # Python's f-string formatter does banker's rounding — pick values
    # away from the .5 boundary so the test isn't an exam in IEEE-754.
    assert _fmt_money_signed(Decimal("12.4")) == "+$12"
    assert _fmt_money_signed(Decimal("12.6")) == "+$13"
    assert _fmt_money_signed(Decimal("-45")) == "-$45"
    assert _fmt_money_signed(None) == "—"


def test_fmt_pct() -> None:
    assert _fmt_pct(None) == "—"
    assert _fmt_pct(Decimal("0.225")) == "22.5%"


def test_fmt_pp_delta_signs() -> None:
    # Improvement = curr lower than prior. We render the raw absolute
    # change with an arrow; sign-coloring is the renderer's job.
    assert _fmt_pp_delta(Decimal("0.20"), Decimal("0.22")) == "▼ 2.0pp"
    assert _fmt_pp_delta(Decimal("0.24"), Decimal("0.22")) == "▲ 2.0pp"
    assert _fmt_pp_delta(Decimal("0.22"), Decimal("0.22")) == "→ 0.0pp"
    assert _fmt_pp_delta(None, Decimal("0.22")) == ""
    assert _fmt_pp_delta(Decimal("0.22"), None) == ""


def test_bucket_pct_thresholds() -> None:
    target = Decimal("0.20")
    assert _bucket_pct(None, target) == "unknown"
    assert _bucket_pct(Decimal("0.19"), target) == "in_target"
    assert _bucket_pct(Decimal("0.20"), target) == "in_target"
    assert _bucket_pct(Decimal("0.21"), target) == "near"
    assert _bucket_pct(Decimal("0.22"), target) == "near"
    assert _bucket_pct(Decimal("0.23"), target) == "off"


def test_bucket_color_round_trip() -> None:
    assert _bucket_color("in_target") == COLOR_GREEN
    assert _bucket_color("near") == COLOR_YELLOW
    assert _bucket_color("off") == COLOR_RED
    # Unknown buckets degrade to neutral so the cell renders without
    # screaming color.
    assert _bucket_color("unknown") not in (COLOR_GREEN, COLOR_YELLOW, COLOR_RED)


def test_money_delta_color() -> None:
    assert _money_delta_color(Decimal("100"), Decimal("90")) == COLOR_GREEN
    assert _money_delta_color(Decimal("90"), Decimal("100")) == COLOR_RED
    assert _money_delta_color(Decimal("100"), Decimal("100")) not in (COLOR_GREEN, COLOR_RED)
    assert _money_delta_color(None, Decimal("100")) == ""


def test_pct_delta_color_improvement_is_green_even_above_target() -> None:
    # Curr is 23% (still above 20% target) but improved from 25% — the
    # operator should see the trend reward, not punishment.
    color = _pct_delta_color(Decimal("0.23"), Decimal("0.25"), Decimal("0.20"))
    assert color == COLOR_GREEN
    # Worsening is red.
    assert _pct_delta_color(Decimal("0.25"), Decimal("0.23"), Decimal("0.20")) == COLOR_RED


def test_default_targets_emits_four_rows_with_portfolio_currents() -> None:
    targets = _default_targets(Decimal("0.18"), Decimal("0.24"))
    assert len(targets) == 4
    assert targets[0].current == Decimal("0.18")
    assert targets[1].current == Decimal("0.24")
    # Store-level rows expose the cap as the target only — no portfolio
    # current to compare against.
    assert targets[2].current is None
    assert targets[3].current is None


# ---------------------------------------------------------------------------
# Synthetic fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def fixture_data() -> DigestData:
    """A digest covering every status bucket so visual regressions
    surface in one rendered HTML body.

    Two field managers, four stores. Maria's cluster is in-target on
    food (19%) but near-target on labor (29%). James's cluster is
    off-target on food (24%). Two recon cases: one flagged, one
    escalated."""
    stores = (
        StoreRow(
            store_number="4001",
            store_name="Bellevue Main",
            field_manager_name="Maria",
            net_sales=Decimal("8500.00"),
            transactions=600,
            food_cost_pct=Decimal("0.190"),
            labor_cost_pct=Decimal("0.290"),
            cash_overshort=Decimal("-2.50"),
            is_food_cost_in_target=True,
            is_labor_cost_in_target=False,
        ),
        StoreRow(
            store_number="4002",
            store_name="Bellevue North",
            field_manager_name="Maria",
            net_sales=Decimal("7200.00"),
            transactions=520,
            food_cost_pct=Decimal("0.205"),
            labor_cost_pct=Decimal("0.275"),
            cash_overshort=Decimal("0.00"),
            is_food_cost_in_target=True,
            is_labor_cost_in_target=True,
        ),
        StoreRow(
            store_number="4101",
            store_name="Seattle Downtown",
            field_manager_name="James",
            net_sales=Decimal("9100.00"),
            transactions=720,
            food_cost_pct=Decimal("0.240"),
            labor_cost_pct=Decimal("0.310"),
            cash_overshort=Decimal("-75.00"),
            is_food_cost_in_target=False,
            is_labor_cost_in_target=False,
        ),
        StoreRow(
            store_number="4102",
            store_name="Seattle Capitol Hill",
            field_manager_name="James",
            net_sales=Decimal("6300.00"),
            transactions=480,
            food_cost_pct=None,
            labor_cost_pct=None,
            cash_overshort=None,
            is_food_cost_in_target=None,
            is_labor_cost_in_target=None,
        ),
    )
    fms = (
        FMRollup(
            field_manager_name="Maria",
            store_count=2,
            net_sales=Decimal("15700.00"),
            food_cost_pct=Decimal("0.197"),
            labor_cost_pct=Decimal("0.283"),
            is_food_cost_in_portfolio_target=True,
            is_labor_cost_in_portfolio_target=False,
            stores=tuple(s for s in stores if s.field_manager_name == "Maria"),
        ),
        FMRollup(
            field_manager_name="James",
            store_count=2,
            net_sales=Decimal("15400.00"),
            food_cost_pct=Decimal("0.240"),
            labor_cost_pct=Decimal("0.310"),
            is_food_cost_in_portfolio_target=False,
            is_labor_cost_in_portfolio_target=False,
            stores=tuple(s for s in stores if s.field_manager_name == "James"),
        ),
    )
    portfolio = PortfolioSnapshot(
        net_sales=Decimal("31100.00"),
        transactions=2320,
        food_cost_pct=Decimal("0.218"),
        labor_cost_pct=Decimal("0.296"),
        prior_net_sales=Decimal("30200.00"),
        prior_transactions=2280,
        prior_food_cost_pct=Decimal("0.225"),
        prior_labor_cost_pct=Decimal("0.290"),
    )
    recon = ReconSummary(
        counts_by_status={
            "clean": 2,
            "flagged": 1,
            "escalated": 1,
            "unverified": 0,
        },
        escalated_cases=(
            ReconCase(
                store_number="4101",
                store_name="Seattle Downtown",
                variance=Decimal("-75.00"),
                status="escalated",
            ),
        ),
    )
    return DigestData(
        week_end=date(2026, 5, 5),
        week_start=date(2026, 4, 29),
        portfolio=portfolio,
        targets=_default_targets(portfolio.food_cost_pct, portfolio.labor_cost_pct),
        recon=recon,
        fm_rollups=fms,
        stores=stores,
        dashboard_url="https://subway-ops.streamlit.app",
        feedback_email="amitojsubway@gmail.com",
    )


# ---------------------------------------------------------------------------
# Renderer contract tests
# ---------------------------------------------------------------------------


def test_subject_includes_week_end_and_counts(fixture_data: DigestData) -> None:
    subject, _ = render_digest(fixture_data)
    assert subject == "Subway weekly — week ending 2026-05-05 — 1 flagged, 1 escalated"


def test_body_is_valid_doctype_html(fixture_data: DigestData) -> None:
    _, body = render_digest(fixture_data)
    assert body.startswith("<!doctype html>")
    assert "</html>" in body


def test_body_includes_every_store_name(fixture_data: DigestData) -> None:
    _, body = render_digest(fixture_data)
    for store in fixture_data.stores:
        assert store.store_name in body, store.store_name


def test_body_includes_every_field_manager(fixture_data: DigestData) -> None:
    _, body = render_digest(fixture_data)
    for fm in fixture_data.fm_rollups:
        assert fm.field_manager_name in body


def test_body_includes_status_chips_for_each_status(fixture_data: DigestData) -> None:
    _, body = render_digest(fixture_data)
    # Each status chip uses the literal status label followed by the count.
    assert "clean 2" in body
    assert "flagged 1" in body
    assert "escalated 1" in body
    assert "unverified 0" in body


def test_body_renders_target_percentages_as_pretty_pct(fixture_data: DigestData) -> None:
    _, body = render_digest(fixture_data)
    # 20% / 22% / 25% / 28% — the canonical four targets.
    for label in ("20.0%", "22.0%", "25.0%", "28.0%"):
        assert label in body, label


def test_body_has_no_script_tags(fixture_data: DigestData) -> None:
    _, body = render_digest(fixture_data)
    # Email clients tend to reject scripts outright; we promise none.
    assert "<script" not in body.lower()
    assert "javascript:" not in body.lower()


def test_body_has_no_external_images(fixture_data: DigestData) -> None:
    """No external image hosts — the playbook explicitly bans them.

    Embedded base64 ``data:image/...`` strings would still be fine but
    we don't ship any in v1, so any ``<img`` is a regression.
    """
    _, body = render_digest(fixture_data)
    assert "<img" not in body.lower()


def test_color_coded_cells_carry_inline_background(fixture_data: DigestData) -> None:
    """Critical cells must inline ``background:`` so Outlook / Gmail
    render the traffic-light state when they drop the ``<style>`` block."""
    _, body = render_digest(fixture_data)
    # Each of the three palette colors should appear inline at least once
    # somewhere in the document (target table + recon chip strip + store
    # table all rely on them).
    for color in (COLOR_GREEN, COLOR_YELLOW, COLOR_RED):
        assert f"background:{color}" in body, color


def test_escalated_case_appears_with_variance(fixture_data: DigestData) -> None:
    _, body = render_digest(fixture_data)
    case = fixture_data.recon.escalated_cases[0]
    assert case.store_name in body
    # _fmt_money_signed renders -75.00 as "-$75".
    assert "-$75" in body


def test_dashboard_url_in_footer(fixture_data: DigestData) -> None:
    _, body = render_digest(fixture_data)
    assert fixture_data.dashboard_url in body
    assert "Open dashboard" in body


def test_feedback_email_mailto_present(fixture_data: DigestData) -> None:
    _, body = render_digest(fixture_data)
    assert f"mailto:{fixture_data.feedback_email}" in body


def test_unknown_food_cost_cell_renders_em_dash(fixture_data: DigestData) -> None:
    """Store 4102 has NULL food/labor pct — the cells must still render
    (showing the em-dash placeholder) without raising."""
    _, body = render_digest(fixture_data)
    # The em-dash placeholder must show up; counts aren't worth pinning.
    assert "—" in body


def test_rendering_is_deterministic(fixture_data: DigestData) -> None:
    """Two renders of the same data MUST be byte-identical. The digest
    is sent once a week; deterministic output is what makes Task 5.4's
    'don't send the same digest twice' check trivial."""
    first = render_digest(fixture_data)
    second = render_digest(fixture_data)
    assert first == second


def test_inline_style_attribute_count_is_substantial(fixture_data: DigestData) -> None:
    """A sanity floor: critical cells live in inline styles, not the
    ``<style>`` block. A digest with fewer than a dozen ``style=`` attrs
    has almost certainly regressed the inline-CSS contract."""
    _, body = render_digest(fixture_data)
    inline_styles = re.findall(r'style="', body)
    assert len(inline_styles) >= 20


def test_subject_matches_playbook_format(fixture_data: DigestData) -> None:
    subject, _ = render_digest(fixture_data)
    pattern = (
        r"^Subway weekly — week ending \d{4}-\d{2}-\d{2} — "
        r"\d+ flagged, \d+ escalated$"
    )
    assert re.match(pattern, subject), subject


def test_targets_table_shows_status_label_per_bucket(fixture_data: DigestData) -> None:
    _, body = render_digest(fixture_data)
    # At least one of each label must appear (food cost 21.8% is "near",
    # labor cost 29.6% is "off" against the 25% portfolio target).
    assert "Near target" in body
    assert "Off target" in body


def test_no_jinja_or_unrendered_placeholders(fixture_data: DigestData) -> None:
    """We render with plain string concat; an accidental f-string typo
    would leave ``{...}`` in the output. Guard against that."""
    _, body = render_digest(fixture_data)
    # No double-braces and no obvious unfilled template tokens.
    assert "{{" not in body
    assert "}}" not in body


def test_target_row_dataclass_is_immutable() -> None:
    row = TargetRow("Food", Decimal("0.20"), Decimal("0.22"))
    with pytest.raises(Exception):  # noqa: B017 — dataclass freezes raise FrozenInstanceError
        row.metric = "Labor"  # type: ignore[misc]


def test_digest_data_post_init_back_fills_counts() -> None:
    data = DigestData(
        week_end=date(2026, 5, 5),
        week_start=date(2026, 4, 29),
        portfolio=PortfolioSnapshot(
            net_sales=None, transactions=None,
            food_cost_pct=None, labor_cost_pct=None,
            prior_net_sales=None, prior_transactions=None,
            prior_food_cost_pct=None, prior_labor_cost_pct=None,
        ),
        targets=(),
        recon=ReconSummary(
            counts_by_status={"flagged": 3, "escalated": 7, "clean": 2},
            escalated_cases=(),
        ),
        fm_rollups=(),
        stores=(),
        dashboard_url="",
        feedback_email="x@example.com",
    )
    assert data.flagged_count == 3
    assert data.escalated_count == 7
