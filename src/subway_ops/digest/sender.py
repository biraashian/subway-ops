"""SMTP send helper for the weekly digest.

Extracted from ``scripts/send_weekly_digest.py`` so the actual network
call lives in one tested place. The script wraps this with all the
business logic (mart refresh, idempotency guard, recipient lookup,
digest-log write).

The transport is Gmail's submission service over implicit TLS — the same
endpoint ``scripts/notify_failure.py`` already uses for alert emails.
"""

from __future__ import annotations

import smtplib
from collections.abc import Iterable
from email.message import EmailMessage

import structlog

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465

log = structlog.get_logger(__name__)


def build_email(
    *,
    sender: str,
    recipients: Iterable[str],
    subject: str,
    html_body: str,
    text_body: str,
) -> EmailMessage:
    """Compose a ``multipart/alternative`` message.

    The plain-text alternative is what spam-scoring systems read; Gmail
    and Apple Mail both prefer the HTML when rendering. ``Bcc`` is used
    for the recipient list so individual operators don't see each
    other's addresses in the ``To`` field.
    """
    recipients = list(recipients)
    if not recipients:
        raise ValueError("recipients must be non-empty")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = sender
    msg["Bcc"] = ", ".join(recipients)
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    return msg


def send_email(
    *,
    to: list[str],
    subject: str,
    html: str,
    text: str,
    user: str,
    password: str,
) -> None:
    """Send the digest. Raises on any SMTP error.

    Keyword-only arguments because the call site is rare and the order
    is easy to get wrong (the four content fields look interchangeable
    at a glance).
    """
    if not user or not password:
        raise ValueError("Gmail user/password must be set")
    msg = build_email(
        sender=user,
        recipients=to,
        subject=subject,
        html_body=html,
        text_body=text,
    )
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as srv:
        srv.login(user, password)
        srv.send_message(msg)
    log.info("digest_email_sent", recipients=len(to), subject=subject)
