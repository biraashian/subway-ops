"""Send a plain-text failure email via Gmail SMTP.

Called from GitHub Actions when a workflow step fails. Reads the job name
from the first CLI arg, pulls Gmail credentials from settings (the workflow
injects them from secrets), and stitches together a link to the workflow
run using the ``GITHUB_*`` env vars Actions provides for free.

Idempotent in the trivial sense: re-running just sends another email.
"""

from __future__ import annotations

import argparse
import os
import smtplib
import sys
from datetime import UTC, datetime
from email.message import EmailMessage

import structlog

from subway_ops.config import settings

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465

log = structlog.get_logger(__name__)


def _gh_run_url() -> str:
    server = os.environ.get("GITHUB_SERVER_URL", "").rstrip("/")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if server and repo and run_id:
        return f"{server}/{repo}/actions/runs/{run_id}"
    return "(no GitHub Actions run URL available — env vars unset)"


def build_message(
    job_name: str,
    *,
    sender: str,
    recipient: str,
    run_url: str | None = None,
    now: datetime | None = None,
) -> EmailMessage:
    """Compose the failure email. Extracted for testing without sending."""
    now = now or datetime.now(UTC)
    run_url = run_url if run_url is not None else _gh_run_url()
    body = (
        f"Subway operations job '{job_name}' failed at "
        f"{now.isoformat(timespec='seconds')}.\n\n"
        f"GitHub Actions run: {run_url}\n\n"
        "Check ops_job_runs for the latest entry, and the workflow logs "
        "above the notify step for the traceback.\n"
    )
    msg = EmailMessage()
    msg["Subject"] = f"[subway-ops] Job '{job_name}' failed"
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(body)
    return msg


def send(msg: EmailMessage, *, user: str, password: str) -> None:
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as srv:
        srv.login(user, password)
        srv.send_message(msg)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job_name", help="Identifier for the job that failed.")
    args = parser.parse_args(argv)

    user = settings.gmail_user
    password = settings.gmail_app_password
    recipient = settings.alert_email
    missing = [
        name
        for name, val in (
            ("GMAIL_USER", user),
            ("GMAIL_APP_PASSWORD", password),
            ("ALERT_EMAIL", recipient),
        )
        if not val
    ]
    if missing:
        sys.stderr.write(
            "notify_failure: missing required secrets: " + ", ".join(missing) + "\n"
        )
        return 2

    msg = build_message(args.job_name, sender=user, recipient=recipient)
    send(msg, user=user, password=password)
    log.info("notify_failure_sent", job=args.job_name, recipient=recipient)
    return 0


if __name__ == "__main__":
    sys.exit(main())
