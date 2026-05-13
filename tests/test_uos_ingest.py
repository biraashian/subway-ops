"""Tests for ``subway_ops.uos.ingest`` dispatch logic.

DB integration (UPSERT into ``stg_uos_compliance`` against a real
Supabase) is out of scope here — that runs as a one-off smoke check
after the Gmail OAuth token is provisioned. These tests cover the
orchestration: skip already-fetched messages, filter rows to known
stores, capture unparsed rows in the result, surface every per-message
note.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from subway_ops.uos import ingest as ingest_mod
from subway_ops.uos.gmail_client import Attachment, Message
from subway_ops.uos.ingest import _parse_received_at, ingest_recent
from subway_ops.uos.parser import (
    STATUS_COMPLETE,
    ComplianceRow,
    ParsedReport,
    UnparsedRow,
)

REPORT_DATE = date(2026, 5, 13)


def _message(msg_id: str, *, attachments: int = 1) -> Message:
    return Message(
        id=msg_id,
        thread_id=f"T-{msg_id}",
        subject="uOS Weekly",
        sender="noreply@uos.example",
        received_at="Wed, 13 May 2026 14:05:00 +0000",
        body_parts=(("text/html", "<p>see attachment</p>"),),
        attachments=tuple(
            Attachment(
                filename=f"r{i}.csv",
                mime_type="text/csv",
                attachment_id=f"ATT-{msg_id}-{i}",
                size=10,
            )
            for i in range(attachments)
        ),
        raw_payload={"id": msg_id},
    )


def _patch_db(
    monkeypatch: pytest.MonkeyPatch,
    *,
    existing: set[str],
    stores: set[str],
) -> dict[str, MagicMock]:
    """Stub out every DB-touching helper inside ``ingest``."""
    insert_raw = MagicMock()
    upsert = MagicMock(return_value=0)
    monkeypatch.setattr(
        ingest_mod, "_existing_message_ids", MagicMock(return_value=existing)
    )
    monkeypatch.setattr(
        ingest_mod, "_known_store_numbers", MagicMock(return_value=stores)
    )
    monkeypatch.setattr(ingest_mod, "_insert_raw_email", insert_raw)
    monkeypatch.setattr(ingest_mod, "upsert_rows", upsert)
    return {"insert_raw": insert_raw, "upsert": upsert}


def _patch_job(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Replace ``track_job`` with a no-op that captures the metadata dict."""
    captured: dict[str, Any] = {}

    class _Ctx:
        def __enter__(self) -> dict[str, Any]:
            return captured

        def __exit__(self, *_: Any) -> bool:
            return False

    monkeypatch.setattr(ingest_mod, "track_job", lambda _name: _Ctx())
    return captured


def _make_client(messages: list[Message], full_messages: dict[str, Message]) -> MagicMock:
    client = MagicMock()
    client.search.return_value = messages
    client.get_message.side_effect = lambda mid: full_messages[mid]
    client.get_attachment.return_value = b"csv,bytes,here"
    return client


def test_ingest_recent_rejects_non_positive_days() -> None:
    with pytest.raises(ValueError):
        ingest_recent(days=0)
    with pytest.raises(ValueError):
        ingest_recent(days=-1)


def test_ingest_recent_short_circuits_when_search_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_db(monkeypatch, existing=set(), stores=set())
    meta = _patch_job(monkeypatch)
    client = _make_client([], {})
    result = ingest_recent(days=7, client=client)
    assert result.messages_seen == 0
    assert result.messages_new == 0
    assert meta["messages_seen"] == 0
    assert meta["rows_written"] == 0


def test_ingest_recent_skips_messages_already_in_raw_log(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = [_message("m1"), _message("m2")]
    full = {m.id: m for m in seen}
    deps = _patch_db(monkeypatch, existing={"m1", "m2"}, stores={"4092"})
    meta = _patch_job(monkeypatch)
    client = _make_client(seen, full)

    result = ingest_recent(days=7, client=client)
    assert result.messages_seen == 2
    assert result.messages_new == 0
    deps["insert_raw"].assert_not_called()
    deps["upsert"].assert_not_called()
    assert meta["messages_new"] == 0


def test_ingest_recent_writes_only_known_stores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    msg = _message("m1")
    seen = [msg]
    full = {msg.id: msg}
    deps = _patch_db(monkeypatch, existing=set(), stores={"4092"})
    meta = _patch_job(monkeypatch)

    parsed = ParsedReport(
        report_date=REPORT_DATE,
        rows=(
            ComplianceRow("4092", "Alice", "Food Safety", STATUS_COMPLETE, None),
            ComplianceRow("9999", "Bob", "Slicer", STATUS_COMPLETE, None),
        ),
        unparsed_rows=(UnparsedRow(reason="missing fields", raw="x"),),
        source_format="csv",
    )
    deps["upsert"].return_value = 1  # mart layer "wrote one row"

    with patch.object(ingest_mod, "parse_email_payload", return_value=parsed):
        client = _make_client(seen, full)
        result = ingest_recent(days=7, client=client)

    deps["insert_raw"].assert_called_once()
    # Only the 4092 row should have been UPSERTed.
    upsert_call = deps["upsert"].call_args
    assert upsert_call.args[0] == "stg_uos_compliance"
    upserted_rows = upsert_call.args[1]
    assert [r["restaurant_number"] for r in upserted_rows] == ["4092"]
    assert result.rows_written == 1
    assert result.rows_skipped_unknown_store == 1
    assert result.unparsed_rows[0].reason == "missing fields"

    # Metadata captures the per-message breakdown for debugging.
    notes = meta["per_message"]
    assert notes[0]["message_id"] == "m1"
    assert notes[0]["source_format"] == "csv"
    assert notes[0]["rows"] == 2
    assert notes[0]["written"] == 1
    assert notes[0]["skipped_unknown_store"] == 1
    assert notes[0]["unparsed"] == 1
    assert meta["unparsed_count"] == 1


def test_ingest_recent_handles_no_recipients_when_no_rows_parsed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    msg = _message("m1")
    seen = [msg]
    full = {msg.id: msg}
    deps = _patch_db(monkeypatch, existing=set(), stores={"4092"})
    _patch_job(monkeypatch)

    parsed = ParsedReport(
        report_date=REPORT_DATE,
        rows=(),
        unparsed_rows=(UnparsedRow(reason="no usable payload", raw=""),),
        source_format="",
    )
    with patch.object(ingest_mod, "parse_email_payload", return_value=parsed):
        client = _make_client(seen, full)
        result = ingest_recent(days=7, client=client)

    deps["insert_raw"].assert_called_once()
    deps["upsert"].assert_not_called()
    assert result.rows_written == 0
    assert result.unparsed_rows[0].reason == "no usable payload"


def test_parse_received_at_handles_rfc2822_and_missing_header() -> None:
    dt = _parse_received_at("Wed, 13 May 2026 14:05:00 +0000")
    assert dt.year == 2026 and dt.month == 5 and dt.day == 13
    assert dt.tzinfo is not None
    # Missing header → falls back to "now" but always tz-aware.
    fallback = _parse_received_at(None)
    assert fallback.tzinfo is not None


def test_ingest_recent_passes_through_query_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_db(monkeypatch, existing=set(), stores=set())
    meta = _patch_job(monkeypatch)
    client = _make_client([], {})
    ingest_recent(days=14, client=client, query="label:UoS-test newer_than:{days}d")
    client.search.assert_called_once()
    args, _ = client.search.call_args
    assert args[0] == "label:UoS-test newer_than:14d"
    assert meta["query"] == "label:UoS-test newer_than:14d"
