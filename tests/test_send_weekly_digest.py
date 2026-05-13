"""Tests for ``scripts/send_weekly_digest.run_send_weekly_digest``.

The orchestrator is shaped like ``run_daily_pull`` from Task 2.7 —
every dependency is injectable so the unit tests never touch the real
DB, SMTP, or builder. The four interesting paths:

1. Happy path: mart refreshes run, idempotency log is empty, builder
   returns a body, recipients found, send_email called, log written.
2. Already-sent: the read_log dependency returns a row → no send.
3. No recipients: empty roster → no send, no log write.
4. Mart refresh failure surfaces so the surrounding ``track_job`` records
   the failure rather than emailing stale numbers.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from scripts.send_weekly_digest import (
    DigestResult,
    _format_summary,
    _plain_text_body,
    run_send_weekly_digest,
)

WEEK_END = date(2026, 5, 5)


def _deps(
    *,
    existing: tuple[datetime, str] | None = None,
    recipients: list[str] | None = None,
    builder_return: tuple[str, str] = ("subj", "<p>body</p>"),
) -> dict[str, Any]:
    """Wire up a spy dependency stack with sensible defaults."""
    deps: dict[str, Any] = {
        "refresh_weekly": MagicMock(return_value=1),
        "refresh_recon": MagicMock(return_value=1),
        "fetch_recipients": MagicMock(return_value=recipients or []),
        "read_log": MagicMock(return_value=existing),
        "write_log": MagicMock(),
        "send": MagicMock(),
        "gmail_user": "ops@example.com",
        "gmail_password": "app-password",
        "dashboard_url": "https://subway-ops.streamlit.app",
    }
    return deps


def _patched_builder(monkeypatch: pytest.MonkeyPatch, ret: tuple[str, str]) -> MagicMock:
    """Replace ``build_digest`` since the orchestrator imports it directly."""
    spy = MagicMock(return_value=ret)
    monkeypatch.setattr(
        "scripts.send_weekly_digest.build_digest",
        spy,
    )
    return spy


def test_happy_path_sends_and_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    deps = _deps(recipients=["owner@example.com", "fm1@example.com"])
    subject = "Subway weekly — week ending 2026-05-05 — 0 flagged, 0 escalated"
    builder = _patched_builder(monkeypatch, (subject, "<p>body</p>"))

    result = run_send_weekly_digest(week_end=WEEK_END, **deps)

    assert result.status == "sent"
    assert result.recipient_count == 2
    deps["refresh_weekly"].assert_called_once_with(WEEK_END)
    deps["refresh_recon"].assert_called_once_with(WEEK_END)
    deps["read_log"].assert_called_once_with(WEEK_END)
    builder.assert_called_once_with(WEEK_END)
    # send_email is called with html + plain-text fallback.
    send_kwargs = deps["send"].call_args.kwargs
    assert send_kwargs["to"] == ["owner@example.com", "fm1@example.com"]
    assert send_kwargs["subject"].startswith("Subway weekly")
    assert send_kwargs["html"] == "<p>body</p>"
    assert "View in browser" in send_kwargs["text"]
    assert send_kwargs["user"] == "ops@example.com"
    assert send_kwargs["password"] == "app-password"
    deps["write_log"].assert_called_once()
    write_kwargs = deps["write_log"].call_args
    assert write_kwargs.args[0] == WEEK_END
    assert write_kwargs.kwargs["recipients"] == 2


def test_already_sent_skips_build_and_send(monkeypatch: pytest.MonkeyPatch) -> None:
    sent_at = datetime(2026, 5, 6, 14, 5)
    deps = _deps(
        existing=(sent_at, "Subway weekly — week ending 2026-05-05 — 1 flagged, 0 escalated"),
        recipients=["should-not-matter@example.com"],
    )
    builder = _patched_builder(monkeypatch, ("ignored", "ignored"))

    result = run_send_weekly_digest(week_end=WEEK_END, **deps)

    assert result.status == "already_sent"
    assert result.sent_at == sent_at
    assert result.subject.startswith("Subway weekly")
    # Mart refresh STILL happens — the playbook says "for freshness" and
    # the operator may want to be able to re-trigger to refresh marts
    # without resending. Build / fetch / send / write must NOT run.
    deps["refresh_weekly"].assert_called_once()
    deps["refresh_recon"].assert_called_once()
    builder.assert_not_called()
    deps["fetch_recipients"].assert_not_called()
    deps["send"].assert_not_called()
    deps["write_log"].assert_not_called()


def test_no_recipients_skips_send_and_log(monkeypatch: pytest.MonkeyPatch) -> None:
    deps = _deps(recipients=[])
    _patched_builder(monkeypatch, ("subj", "<p>body</p>"))

    result = run_send_weekly_digest(week_end=WEEK_END, **deps)

    assert result.status == "no_recipients"
    assert result.recipient_count == 0
    deps["send"].assert_not_called()
    deps["write_log"].assert_not_called()


def test_refresh_failure_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    deps = _deps(recipients=["a@example.com"])
    deps["refresh_weekly"].side_effect = RuntimeError("Supabase exploded")
    _patched_builder(monkeypatch, ("subj", "<p>body</p>"))

    with pytest.raises(RuntimeError, match="Supabase exploded"):
        run_send_weekly_digest(week_end=WEEK_END, **deps)
    deps["send"].assert_not_called()
    deps["write_log"].assert_not_called()


def test_send_failure_does_not_write_log(monkeypatch: pytest.MonkeyPatch) -> None:
    deps = _deps(recipients=["a@example.com"])
    deps["send"].side_effect = RuntimeError("SMTP down")
    _patched_builder(monkeypatch, ("subj", "<p>body</p>"))

    with pytest.raises(RuntimeError, match="SMTP down"):
        run_send_weekly_digest(week_end=WEEK_END, **deps)
    deps["write_log"].assert_not_called()


def test_default_week_end_is_previous_business_week(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "scripts.send_weekly_digest.previous_business_week",
        lambda: (date(2026, 4, 29), date(2026, 5, 5)),
    )
    deps = _deps(existing=(datetime(2026, 5, 6), "already sent subject"))
    _patched_builder(monkeypatch, ("ignored", "ignored"))

    result = run_send_weekly_digest(**deps)
    assert result.week_end == date(2026, 5, 5)


def test_plain_text_body_includes_subject_and_url() -> None:
    body = _plain_text_body(
        "Subway weekly — week ending 2026-05-05 — 0 flagged, 0 escalated",
        "https://subway-ops.streamlit.app",
    )
    assert "Subway weekly" in body
    assert "https://subway-ops.streamlit.app" in body
    assert "View in browser" in body


def test_plain_text_body_handles_missing_dashboard_url() -> None:
    body = _plain_text_body("subj", "")
    assert "DASHBOARD_URL not configured" in body


def test_format_summary_paths() -> None:
    sent_at = datetime(2026, 5, 6, 14, 0)
    already = DigestResult(
        status="already_sent",
        week_end=WEEK_END,
        subject="subj",
        recipient_count=0,
        sent_at=sent_at,
    )
    assert "Already sent" in _format_summary(already)
    assert WEEK_END.isoformat() in _format_summary(already)

    none = DigestResult(
        status="no_recipients",
        week_end=WEEK_END,
        subject="subj",
        recipient_count=0,
        sent_at=None,
    )
    assert "no active owner" in _format_summary(none)

    sent = DigestResult(
        status="sent",
        week_end=WEEK_END,
        subject="subj",
        recipient_count=2,
        sent_at=sent_at,
    )
    line = _format_summary(sent, recipients=["a@example.com", "b@example.com"])
    assert "Sent digest" in line
    assert "a@example.com" in line
    assert "b@example.com" in line
