"""Tests for the small page-agnostic dashboard helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pandas as pd

from subway_ops.config import (
    VARIANCE_ESCALATED_USD,
    VARIANCE_FLAGGED_USD,
)
from subway_ops.dashboard.components import (
    COMPLIANCE_GREEN_MIN,
    COMPLIANCE_YELLOW_MIN,
    EMOJI_IN_TARGET,
    EMOJI_NEAR_TARGET,
    EMOJI_OFF_TARGET,
    EMOJI_UNKNOWN,
    KEY_FILTER_STATUS,
    KEY_FILTER_STORE,
    KEY_FILTER_WEEK_CHOICE,
    compliance_bucket,
    compliance_emoji,
)
from subway_ops.dashboard.components.helpers import (
    csv_download_button,
    humanize_relative,
)

# ---------------------------------------------------------------------------
# humanize_relative
# ---------------------------------------------------------------------------


def test_humanize_just_now_threshold() -> None:
    now = datetime(2026, 5, 13, 12, 0, 0, tzinfo=UTC)
    assert humanize_relative(now - timedelta(seconds=10), now=now) == "just now"


def test_humanize_seconds_under_one_minute() -> None:
    now = datetime(2026, 5, 13, 12, 0, 0, tzinfo=UTC)
    assert humanize_relative(now - timedelta(seconds=45), now=now) == "45 seconds ago"


def test_humanize_minutes() -> None:
    now = datetime(2026, 5, 13, 12, 0, 0, tzinfo=UTC)
    assert humanize_relative(now - timedelta(minutes=1), now=now) == "1 minute ago"
    assert humanize_relative(now - timedelta(minutes=12), now=now) == "12 minutes ago"


def test_humanize_hours() -> None:
    now = datetime(2026, 5, 13, 12, 0, 0, tzinfo=UTC)
    assert humanize_relative(now - timedelta(hours=1), now=now) == "1 hour ago"
    assert humanize_relative(now - timedelta(hours=5), now=now) == "5 hours ago"


def test_humanize_yesterday_and_days() -> None:
    now = datetime(2026, 5, 13, 12, 0, 0, tzinfo=UTC)
    assert humanize_relative(now - timedelta(days=1), now=now) == "yesterday"
    assert humanize_relative(now - timedelta(days=5), now=now) == "5 days ago"


def test_humanize_accepts_naive_datetime() -> None:
    """Naive datetimes are treated as UTC."""
    now = datetime(2026, 5, 13, 12, 0, 0, tzinfo=UTC)
    naive = datetime(2026, 5, 13, 11, 0, 0)  # 1 hour ago in UTC
    assert humanize_relative(naive, now=now) == "1 hour ago"


def test_humanize_accepts_pandas_timestamp() -> None:
    now = datetime(2026, 5, 13, 12, 0, 0, tzinfo=UTC)
    ts = pd.Timestamp("2026-05-13 11:55:00", tz="UTC")
    assert humanize_relative(ts, now=now) == "5 minutes ago"


def test_humanize_future_renders_as_just_now() -> None:
    """Clock skew shouldn't produce 'negative 2 minutes ago' nonsense."""
    now = datetime(2026, 5, 13, 12, 0, 0, tzinfo=UTC)
    assert humanize_relative(now + timedelta(minutes=2), now=now) == "just now"


# ---------------------------------------------------------------------------
# csv_download_button — only the empty-input branch is observable here.
# ---------------------------------------------------------------------------


def test_csv_download_button_noops_on_empty_df() -> None:
    # The helper must not even attempt to call st.download_button when
    # there's nothing to download — otherwise Streamlit raises about
    # missing runtime context. A plain return is the expected behaviour.
    csv_download_button(pd.DataFrame(), filename="x.csv")
    csv_download_button(None, filename="x.csv")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Filter-key constants exist for cross-page persistence
# ---------------------------------------------------------------------------


def test_filter_keys_exposed() -> None:
    assert KEY_FILTER_WEEK_CHOICE
    assert KEY_FILTER_STORE
    assert KEY_FILTER_STATUS
    # Distinct keys so widgets don't collide.
    keys = {KEY_FILTER_WEEK_CHOICE, KEY_FILTER_STORE, KEY_FILTER_STATUS}
    assert len(keys) == 3


# ---------------------------------------------------------------------------
# Variance threshold constants
# ---------------------------------------------------------------------------


def test_variance_thresholds_are_decimal_and_ordered() -> None:
    assert isinstance(VARIANCE_FLAGGED_USD, Decimal)
    assert isinstance(VARIANCE_ESCALATED_USD, Decimal)
    assert Decimal("5") == VARIANCE_FLAGGED_USD
    assert Decimal("50") == VARIANCE_ESCALATED_USD
    # Escalation must be a stricter (larger) threshold than mere flagging.
    assert VARIANCE_ESCALATED_USD > VARIANCE_FLAGGED_USD


# ---------------------------------------------------------------------------
# Compliance bucketing (Task 6.3)
# ---------------------------------------------------------------------------


def test_compliance_thresholds_are_ordered() -> None:
    # Green threshold sits above yellow — sanity check the constants
    # never accidentally invert.
    assert COMPLIANCE_GREEN_MIN > COMPLIANCE_YELLOW_MIN
    assert Decimal("0.90") == COMPLIANCE_GREEN_MIN
    assert Decimal("0.80") == COMPLIANCE_YELLOW_MIN


def test_compliance_bucket_decimal_and_float() -> None:
    assert compliance_bucket(Decimal("0.95")) == "in_target"
    assert compliance_bucket(Decimal("0.90")) == "in_target"  # boundary
    assert compliance_bucket(Decimal("0.85")) == "near"
    assert compliance_bucket(Decimal("0.80")) == "near"  # boundary
    assert compliance_bucket(Decimal("0.79")) == "off"
    assert compliance_bucket(0.92) == "in_target"
    assert compliance_bucket(None) == "unknown"


def test_compliance_emoji_uses_status_palette() -> None:
    assert compliance_emoji(Decimal("0.92")) == EMOJI_IN_TARGET
    assert compliance_emoji(Decimal("0.85")) == EMOJI_NEAR_TARGET
    assert compliance_emoji(Decimal("0.50")) == EMOJI_OFF_TARGET
    assert compliance_emoji(None) == EMOJI_UNKNOWN
