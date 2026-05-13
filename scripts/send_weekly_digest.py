"""Send the Wednesday weekly digest.

Schedule: GitHub Actions cron fires every Wednesday at 14:00 UTC, which
lands between 06:00 and 07:00 PT depending on DST. The script:

1. Resolves ``week_end`` = the just-closed Tuesday via
   ``previous_business_week()`` (overridable via ``--week-end YYYY-MM-DD``).
2. Refreshes ``mart_store_weekly`` and ``mart_recon_weekly`` for that
   week so the digest body reflects the freshest possible numbers.
3. Idempotency guard: if ``ops_digest_log`` already has a row for that
   ``week_end``, prints a "Already sent" line and exits 0.
4. Builds the digest via ``subway_ops.digest.builder.build_digest``.
5. Looks up recipients from ``ref_users`` where role IN
   ('owner','field_manager') AND ``is_active`` IS TRUE.
6. Sends the email via ``subway_ops.digest.sender.send_email``.
7. Records the send in ``ops_digest_log`` (key = ``week_end``).

The whole thing wraps in ``track_job("send_weekly_digest")`` so a
failure lands in ``ops_job_runs`` and the GitHub Actions step picks it
up via the existing ``notify_failure.py`` plumbing.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import structlog
from sqlalchemy import text

from subway_ops.calendar import previous_business_week
from subway_ops.config import settings
from subway_ops.db.connection import get_engine
from subway_ops.db.job_runs import track_job
from subway_ops.digest.builder import build_digest
from subway_ops.digest.sender import send_email
from subway_ops.transform import mart_recon_weekly, mart_store_weekly

JOB_NAME = "send_weekly_digest"

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class DigestResult:
    """Outcome of one ``run_send_weekly_digest`` invocation.

    ``status`` is one of:

    - ``"sent"``      — email actually went out and ``ops_digest_log``
      received a row.
    - ``"already_sent"`` — idempotency guard hit; nothing changed.
    - ``"no_recipients"`` — no active owner / field_manager rows; the
      send is skipped intentionally rather than failing.
    """

    status: str
    week_end: date
    subject: str
    recipient_count: int
    sent_at: datetime | None


def _existing_log_row(week_end: date) -> tuple[datetime, str] | None:
    """Return ``(sent_at, subject)`` if the digest is already logged."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT sent_at, subject FROM ops_digest_log "
                "WHERE week_end_date = :w"
            ),
            {"w": week_end},
        ).first()
    if row is None:
        return None
    return row[0], str(row[1])


def _active_recipients() -> list[str]:
    """Owners + field managers, deduplicated, sorted for stable output."""
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT DISTINCT email FROM ref_users
                WHERE is_active = TRUE
                  AND role IN ('owner', 'field_manager')
                ORDER BY email
                """
            )
        ).all()
    return [str(r[0]) for r in rows]


def _log_send(week_end: date, *, recipients: int, subject: str) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO ops_digest_log
                    (week_end_date, recipient_count, subject)
                VALUES (:w, :n, :s)
                ON CONFLICT (week_end_date) DO NOTHING
                """
            ),
            {"w": week_end, "n": recipients, "s": subject},
        )


def _plain_text_body(subject: str, dashboard_url: str) -> str:
    """The plain-text alternative — short, just enough for spam-score."""
    url = dashboard_url or "(DASHBOARD_URL not configured)"
    return (
        f"{subject}\n\n"
        f"View in browser: {url}\n\n"
        "This is the Subway weekly digest. If you're seeing this plain-text "
        "version, your email client suppressed the HTML body.\n"
    )


SendFn = Any  # send_email signature; widened so tests can pass mocks.
WeeklyRefreshFn = Any
ReconRefreshFn = Any
RecipientsFn = Any
LogReadFn = Any
LogWriteFn = Any


def run_send_weekly_digest(
    *,
    week_end: date | None = None,
    refresh_weekly: WeeklyRefreshFn | None = None,
    refresh_recon: ReconRefreshFn | None = None,
    fetch_recipients: RecipientsFn | None = None,
    read_log: LogReadFn | None = None,
    write_log: LogWriteFn | None = None,
    send: SendFn | None = None,
    gmail_user: str | None = None,
    gmail_password: str | None = None,
    dashboard_url: str | None = None,
) -> DigestResult:
    """Orchestrate one digest send.

    Every dependency is injectable for testing; defaults wire up the
    real DB / SMTP. The function NEVER raises on "no recipients" or
    "already sent" — those are normal terminal states. SMTP / DB errors
    bubble up so the surrounding ``track_job`` records a failure.
    """
    if week_end is None:
        _, week_end = previous_business_week()
    refresh_weekly = refresh_weekly or mart_store_weekly.refresh
    refresh_recon = refresh_recon or mart_recon_weekly.refresh_for_week
    fetch_recipients = fetch_recipients or _active_recipients
    read_log = read_log or _existing_log_row
    write_log = write_log or _log_send
    send = send or send_email
    gmail_user = gmail_user if gmail_user is not None else settings.gmail_user
    gmail_password = (
        gmail_password if gmail_password is not None else settings.gmail_app_password
    )
    dashboard_url = (
        dashboard_url if dashboard_url is not None else settings.dashboard_url
    )

    log.info("digest_send_start", week_end=str(week_end))

    # Freshness pass first. If a mart refresh fails the whole job
    # aborts — we'd rather skip sending than email stale numbers.
    refresh_weekly(week_end)
    refresh_recon(week_end)

    existing = read_log(week_end)
    if existing is not None:
        sent_at, subject = existing
        log.info(
            "digest_already_sent",
            week_end=str(week_end),
            sent_at=str(sent_at),
        )
        return DigestResult(
            status="already_sent",
            week_end=week_end,
            subject=subject,
            recipient_count=0,
            sent_at=sent_at,
        )

    subject, html_body = build_digest(week_end)
    recipients = list(fetch_recipients())
    if not recipients:
        log.warning("digest_no_recipients", week_end=str(week_end))
        return DigestResult(
            status="no_recipients",
            week_end=week_end,
            subject=subject,
            recipient_count=0,
            sent_at=None,
        )

    text_body = _plain_text_body(subject, dashboard_url or "")
    send(
        to=recipients,
        subject=subject,
        html=html_body,
        text=text_body,
        user=gmail_user,
        password=gmail_password,
    )
    write_log(week_end, recipients=len(recipients), subject=subject)
    sent_at = datetime.now().astimezone()
    log.info(
        "digest_send_done",
        week_end=str(week_end),
        recipients=len(recipients),
        subject=subject,
    )
    return DigestResult(
        status="sent",
        week_end=week_end,
        subject=subject,
        recipient_count=len(recipients),
        sent_at=sent_at,
    )


def _format_summary(result: DigestResult, *, recipients: Iterable[str] = ()) -> str:
    """Human-readable one-liner printed to stdout from ``main``."""
    if result.status == "already_sent":
        return (
            f"Already sent {result.week_end} at "
            f"{result.sent_at.isoformat() if result.sent_at else 'unknown'}"
        )
    if result.status == "no_recipients":
        return f"Skipped {result.week_end}: no active owner / field_manager users"
    rcpts = ", ".join(recipients)
    return (
        f"Sent digest for {result.week_end} to "
        f"{result.recipient_count} recipients ({rcpts}). "
        f"Subject: {result.subject}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--week-end",
        type=date.fromisoformat,
        default=None,
        help=(
            "Tuesday week-end (YYYY-MM-DD). Defaults to the just-closed "
            "business week."
        ),
    )
    args = parser.parse_args(argv)

    structlog.configure(processors=[structlog.dev.ConsoleRenderer()])

    with track_job(JOB_NAME) as meta:
        result = run_send_weekly_digest(week_end=args.week_end)
        meta["week_end"] = result.week_end.isoformat()
        meta["status"] = result.status
        meta["subject"] = result.subject
        meta["recipient_count"] = result.recipient_count
        meta["rows_written"] = (
            result.recipient_count if result.status == "sent" else 0
        )

    print(_format_summary(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
