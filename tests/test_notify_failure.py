"""Tests for the failure notification helper."""

from __future__ import annotations

from datetime import UTC, datetime
from email.message import EmailMessage
from unittest.mock import MagicMock, patch

import pytest

from scripts import notify_failure


def test_build_message_subject_and_body_contain_job_name() -> None:
    fixed_now = datetime(2026, 5, 12, 15, 0, 0, tzinfo=UTC)
    msg = notify_failure.build_message(
        "daily_pull",
        sender="ops@example.com",
        recipient="alerts@example.com",
        run_url="https://github.com/owner/repo/actions/runs/123",
        now=fixed_now,
    )
    assert isinstance(msg, EmailMessage)
    assert msg["Subject"] == "[subway-ops] Job 'daily_pull' failed"
    assert msg["From"] == "ops@example.com"
    assert msg["To"] == "alerts@example.com"
    body = msg.get_content()
    assert "daily_pull" in body
    assert "2026-05-12T15:00:00+00:00" in body
    assert "https://github.com/owner/repo/actions/runs/123" in body


def test_build_message_falls_back_when_run_url_missing() -> None:
    with patch.dict("os.environ", {}, clear=False):
        for k in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID"):
            __import__("os").environ.pop(k, None)
        msg = notify_failure.build_message(
            "weekly_digest",
            sender="ops@example.com",
            recipient="alerts@example.com",
        )
    assert "no GitHub Actions run URL" in msg.get_content()


def test_main_exits_2_when_secrets_missing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(notify_failure.settings, "gmail_user", "")
    monkeypatch.setattr(notify_failure.settings, "gmail_app_password", "")
    monkeypatch.setattr(notify_failure.settings, "alert_email", "")
    rc = notify_failure.main(["daily_pull"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "GMAIL_USER" in err and "ALERT_EMAIL" in err


def test_main_sends_message_when_secrets_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(notify_failure.settings, "gmail_user", "ops@example.com")
    monkeypatch.setattr(notify_failure.settings, "gmail_app_password", "app-password")
    monkeypatch.setattr(notify_failure.settings, "alert_email", "alerts@example.com")
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.com")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_RUN_ID", "99")

    smtp_instance = MagicMock()
    smtp_ctx = MagicMock()
    smtp_ctx.__enter__.return_value = smtp_instance
    smtp_ctx.__exit__.return_value = False

    with patch.object(notify_failure.smtplib, "SMTP_SSL", return_value=smtp_ctx) as smtp_cls:
        rc = notify_failure.main(["daily_pull"])

    assert rc == 0
    smtp_cls.assert_called_once_with(notify_failure.SMTP_HOST, notify_failure.SMTP_PORT)
    smtp_instance.login.assert_called_once_with("ops@example.com", "app-password")
    sent = smtp_instance.send_message.call_args[0][0]
    assert isinstance(sent, EmailMessage)
    assert "daily_pull" in sent["Subject"]
    assert "owner/repo/actions/runs/99" in sent.get_content()
