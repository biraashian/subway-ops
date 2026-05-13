"""Pull recent uOS emails from Gmail and stage them.

Flow:

1. ``GmailClient.search("label:UoS newer_than:Nd")`` returns lightweight
   message ids.
2. For each id we look up ``raw_uos_emails`` — if the row exists, skip.
3. Otherwise pull the full message + each attachment, persist the
   envelope to ``raw_uos_emails``, hand the bytes to
   ``parser.parse_email_payload`` to extract compliance rows, then
   UPSERT into ``stg_uos_compliance`` (limited to stores in
   ``ref_stores``).
4. Anything the parser couldn't classify is dropped into the
   surrounding ``track_job`` row's metadata so the operator can debug.

The whole thing wraps in ``track_job("ingest_uos")``. Failures bubble
up so the workflow can fire ``notify_failure.py``.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import structlog
from sqlalchemy import text

from subway_ops.db.connection import get_engine
from subway_ops.db.job_runs import track_job
from subway_ops.db.upsert import upsert_rows
from subway_ops.uos.gmail_client import GmailClient, Message
from subway_ops.uos.parser import (
    ComplianceRow,
    ParsedReport,
    UnparsedRow,
    parse_email_payload,
)

JOB_NAME = "ingest_uos"
DEFAULT_DAYS = 7
DEFAULT_QUERY = "label:UoS newer_than:{days}d"

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class IngestResult:
    """Summary of one ``ingest_recent`` run."""

    messages_seen: int
    messages_new: int
    rows_written: int
    rows_skipped_unknown_store: int
    unparsed_rows: tuple[UnparsedRow, ...]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_received_at(raw: str | None) -> datetime:
    """Parse an RFC-2822 Date header into a tz-aware datetime.

    Falls back to ``datetime.now(UTC)`` only when the header is
    completely missing — uOS emails always set Date, so this is
    really defensive coverage for hand-crafted test fixtures.
    """
    if not raw:
        return datetime.now(UTC)
    dt = parsedate_to_datetime(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _existing_message_ids(message_ids: Iterable[str]) -> set[str]:
    """Look up which of ``message_ids`` are already in raw_uos_emails."""
    ids = list(message_ids)
    if not ids:
        return set()
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT gmail_message_id FROM raw_uos_emails "
                "WHERE gmail_message_id = ANY(:ids)"
            ),
            {"ids": ids},
        ).all()
    return {str(r[0]) for r in rows}


def _known_store_numbers() -> set[str]:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT store_number FROM ref_stores")).all()
    return {str(r[0]) for r in rows}


def _insert_raw_email(
    *,
    msg: Message,
    received_at: datetime,
    payload: dict[str, Any],
) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO raw_uos_emails
                    (gmail_message_id, received_at, subject,
                     attachment_count, payload)
                VALUES (:id, :received, :subject, :n, CAST(:payload AS JSONB))
                ON CONFLICT (gmail_message_id) DO NOTHING
                """
            ),
            {
                "id": msg.id,
                "received": received_at,
                "subject": msg.subject,
                "n": len(msg.attachments),
                "payload": json.dumps(payload),
            },
        )


def _upsert_compliance(
    rows: Iterable[ComplianceRow],
    *,
    report_date: date,
    known_stores: set[str],
) -> tuple[int, int]:
    """Filter to known stores and UPSERT into stg_uos_compliance.

    Returns ``(written, skipped_unknown_store)``. Empty input is a
    no-op.
    """
    written = 0
    skipped = 0
    payload: list[dict[str, Any]] = []
    for r in rows:
        if r.restaurant_number not in known_stores:
            skipped += 1
            continue
        payload.append(
            {
                "restaurant_number": r.restaurant_number,
                "report_date": report_date,
                "employee_name": r.employee_name,
                "course_name": r.course_name,
                "completion_status": r.completion_status,
                "completed_at": r.completed_at,
            }
        )
    if payload:
        written = upsert_rows(
            "stg_uos_compliance",
            payload,
            key_cols=[
                "restaurant_number",
                "report_date",
                "employee_name",
                "course_name",
            ],
        )
    return written, skipped


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _fetch_attachments(
    client: GmailClient, msg: Message
) -> list[tuple[str, str, bytes]]:
    """Pull bytes for every attachment on the message."""
    out: list[tuple[str, str, bytes]] = []
    for att in msg.attachments:
        data = client.get_attachment(msg.id, att.attachment_id)
        out.append((att.filename, att.mime_type, data))
    return out


def _largest_html_body(msg: Message) -> str:
    """Return the HTML body if present, else the plain-text body."""
    html_parts = [b for mime, b in msg.body_parts if mime == "text/html"]
    if html_parts:
        return max(html_parts, key=len)
    plain_parts = [b for mime, b in msg.body_parts if mime.startswith("text/")]
    return max(plain_parts, key=len) if plain_parts else ""


def _process_message(
    client: GmailClient,
    msg: Message,
    *,
    known_stores: set[str],
) -> tuple[int, int, ParsedReport]:
    """Fetch attachments, parse, persist. Returns (written, skipped, report)."""
    full = client.get_message(msg.id)
    received_at = _parse_received_at(full.received_at)
    attachments = _fetch_attachments(client, full)
    raw_payload = {
        "id": full.id,
        "subject": full.subject,
        "sender": full.sender,
        "received_at": full.received_at,
        "attachment_count": len(attachments),
        "payload": full.raw_payload,
    }
    _insert_raw_email(msg=full, received_at=received_at, payload=raw_payload)

    report = parse_email_payload(
        html_body=_largest_html_body(full),
        attachments=attachments,
        report_date=received_at.date(),
    )
    written, skipped = _upsert_compliance(
        report.rows,
        report_date=report.report_date,
        known_stores=known_stores,
    )
    return written, skipped, report


def ingest_recent(
    days: int = DEFAULT_DAYS,
    *,
    client: GmailClient | None = None,
    query: str | None = None,
) -> IngestResult:
    """Pull new uOS emails from Gmail and parse into stg_uos_compliance.

    Wraps the whole run in ``track_job("ingest_uos")`` and writes
    ``rows_written`` plus per-message counts into metadata. Idempotent:
    messages already in ``raw_uos_emails`` are skipped without
    re-parsing.

    ``client`` and ``query`` are injectable for tests; production
    builds a real ``GmailClient`` and uses the default
    ``label:UoS newer_than:Nd`` query.
    """
    if days <= 0:
        raise ValueError(f"days must be positive, got {days}")

    with track_job(JOB_NAME) as meta:
        meta["days"] = days
        gc = client or GmailClient()
        q = (query or DEFAULT_QUERY).format(days=days)
        meta["query"] = q
        seen = gc.search(q, max_results=200)
        meta["messages_seen"] = len(seen)

        if not seen:
            meta["messages_new"] = 0
            meta["rows_written"] = 0
            return IngestResult(0, 0, 0, 0, ())

        existing = _existing_message_ids(m.id for m in seen)
        new_messages = [m for m in seen if m.id not in existing]
        meta["messages_new"] = len(new_messages)

        if not new_messages:
            meta["rows_written"] = 0
            return IngestResult(len(seen), 0, 0, 0, ())

        known_stores = _known_store_numbers()
        meta["known_store_count"] = len(known_stores)

        total_written = 0
        total_skipped = 0
        all_unparsed: list[UnparsedRow] = []
        notes: list[dict[str, Any]] = []
        for m in new_messages:
            written, skipped, report = _process_message(
                gc, m, known_stores=known_stores
            )
            total_written += written
            total_skipped += skipped
            all_unparsed.extend(report.unparsed_rows)
            notes.append(
                {
                    "message_id": m.id,
                    "source_format": report.source_format,
                    "rows": len(report.rows),
                    "written": written,
                    "skipped_unknown_store": skipped,
                    "unparsed": len(report.unparsed_rows),
                }
            )

        meta["rows_written"] = total_written
        meta["rows_skipped_unknown_store"] = total_skipped
        meta["per_message"] = notes
        if all_unparsed:
            # Capture at most 50 unparsed rows so a runaway parser
            # doesn't bloat ops_job_runs.metadata beyond a useful
            # debugging level.
            meta["unparsed_sample"] = [
                {"reason": r.reason, "raw": r.raw}
                for r in all_unparsed[:50]
            ]
            meta["unparsed_count"] = len(all_unparsed)

        return IngestResult(
            messages_seen=len(seen),
            messages_new=len(new_messages),
            rows_written=total_written,
            rows_skipped_unknown_store=total_skipped,
            unparsed_rows=tuple(all_unparsed),
        )
