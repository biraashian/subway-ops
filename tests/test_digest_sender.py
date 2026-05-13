"""Tests for the SMTP sender helper.

The real network call is wrapped in ``smtplib.SMTP_SSL`` — we patch that
out and assert message shape (headers, multipart structure, body).
"""

from __future__ import annotations

from email.message import EmailMessage
from unittest.mock import MagicMock, patch

import pytest

from subway_ops.digest import sender


def test_build_email_sets_basic_headers() -> None:
    msg = sender.build_email(
        sender="ops@example.com",
        recipients=["a@example.com", "b@example.com"],
        subject="Weekly digest — 2026-05-05",
        html_body="<p>hi</p>",
        text_body="hi",
    )
    assert isinstance(msg, EmailMessage)
    assert msg["Subject"] == "Weekly digest — 2026-05-05"
    assert msg["From"] == "ops@example.com"
    # Bcc keeps individual addresses out of the visible To: header.
    assert msg["To"] == "ops@example.com"
    assert msg["Bcc"] == "a@example.com, b@example.com"


def test_build_email_multipart_alternative_has_both_parts() -> None:
    msg = sender.build_email(
        sender="ops@example.com",
        recipients=["only@example.com"],
        subject="s",
        html_body="<p>html body</p>",
        text_body="plain body",
    )
    # walk() includes the root + each alternative. Two payload parts:
    # text/plain (set_content) and text/html (add_alternative).
    types = [part.get_content_type() for part in msg.walk() if not part.is_multipart()]
    assert "text/plain" in types
    assert "text/html" in types
    html_part = next(p for p in msg.walk() if p.get_content_type() == "text/html")
    assert "html body" in html_part.get_content()
    plain_part = next(p for p in msg.walk() if p.get_content_type() == "text/plain")
    assert "plain body" in plain_part.get_content()


def test_build_email_rejects_empty_recipients() -> None:
    with pytest.raises(ValueError):
        sender.build_email(
            sender="ops@example.com",
            recipients=[],
            subject="s",
            html_body="<p>h</p>",
            text_body="t",
        )


def test_send_email_logins_and_sends_message() -> None:
    smtp_instance = MagicMock()
    smtp_ctx = MagicMock()
    smtp_ctx.__enter__.return_value = smtp_instance
    smtp_ctx.__exit__.return_value = False

    with patch.object(sender.smtplib, "SMTP_SSL", return_value=smtp_ctx) as cls:
        sender.send_email(
            to=["a@example.com", "b@example.com"],
            subject="s",
            html="<p>h</p>",
            text="t",
            user="ops@example.com",
            password="app-password",
        )

    cls.assert_called_once_with(sender.SMTP_HOST, sender.SMTP_PORT)
    smtp_instance.login.assert_called_once_with("ops@example.com", "app-password")
    sent = smtp_instance.send_message.call_args[0][0]
    assert isinstance(sent, EmailMessage)
    assert sent["From"] == "ops@example.com"
    assert sent["Bcc"] == "a@example.com, b@example.com"


def test_send_email_rejects_missing_credentials() -> None:
    with pytest.raises(ValueError):
        sender.send_email(
            to=["a@example.com"],
            subject="s",
            html="<p>h</p>",
            text="t",
            user="",
            password="app-password",
        )
    with pytest.raises(ValueError):
        sender.send_email(
            to=["a@example.com"],
            subject="s",
            html="<p>h</p>",
            text="t",
            user="ops@example.com",
            password="",
        )
