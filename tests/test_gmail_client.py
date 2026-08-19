"""Tests for ``subway_ops.uos.gmail_client``.

The Gmail API client never touches the network in tests — every test
either injects a mock ``service`` (so ``users().messages().list()`` etc.
returns synthetic dicts) or exercises the pure payload parsing helpers.

Credential loading is exercised against a synthetic token file and a
synthetic base64'd env var; the real refresh path is verified by
asserting that ``creds.refresh(...)`` would be invoked with an
expired-but-refreshable Credentials stub.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from subway_ops.uos import gmail_client
from subway_ops.uos.gmail_client import (
    SCOPES,
    Attachment,
    GmailClient,
    Message,
    _decode_body,
    _decode_token_b64,
    _header,
    _refresh_if_needed,
    _walk_parts,
    load_credentials,
    message_from_payload,
)

# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_header_lookup_is_case_insensitive() -> None:
    headers = [
        {"name": "Subject", "value": "uOS weekly"},
        {"name": "FROM", "value": "noreply@uos.example"},
    ]
    assert _header(headers, "subject") == "uOS weekly"
    assert _header(headers, "From") == "noreply@uos.example"
    assert _header(headers, "missing") == ""


def test_decode_body_handles_urlsafe_b64_without_padding() -> None:
    # "Hello, world" → urlsafe b64 has no padding when the source byte
    # count is a multiple of 3. Strip what padding there is so we
    # exercise the function's pad-restoration branch.
    raw = b"Hello, uOS!"
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    out = _decode_body({"body": {"data": encoded}})
    assert out == "Hello, uOS!"


def test_decode_body_returns_empty_on_missing_data() -> None:
    assert _decode_body({}) == ""
    assert _decode_body({"body": {}}) == ""


def test_walk_parts_yields_leaves_only() -> None:
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {"mimeType": "text/plain", "body": {"data": ""}},
            {
                "mimeType": "multipart/alternative",
                "parts": [
                    {"mimeType": "text/html", "body": {"data": ""}},
                ],
            },
        ],
    }
    leaves = list(_walk_parts(payload))
    mimes = [p["mimeType"] for p in leaves]
    assert "text/plain" in mimes
    assert "text/html" in mimes
    assert "multipart/mixed" not in mimes
    assert "multipart/alternative" not in mimes


def test_message_from_payload_extracts_headers_body_and_attachments() -> None:
    body_text = base64.urlsafe_b64encode(b"plain body").decode("ascii")
    html = base64.urlsafe_b64encode(b"<p>html body</p>").decode("ascii")
    payload = {
        "id": "MSG-1",
        "threadId": "THR-1",
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [
                {"name": "Subject", "value": "uOS Weekly Compliance"},
                {"name": "From", "value": "noreply@uos.example"},
                {"name": "Date", "value": "Wed, 13 May 2026 14:05:00 +0000"},
            ],
            "parts": [
                {
                    "mimeType": "multipart/alternative",
                    "parts": [
                        {"mimeType": "text/plain", "body": {"data": body_text}},
                        {"mimeType": "text/html", "body": {"data": html}},
                    ],
                },
                {
                    "filename": "compliance.csv",
                    "mimeType": "text/csv",
                    "body": {"attachmentId": "ATT-1", "size": 1024},
                },
            ],
        },
    }
    msg = message_from_payload(payload)
    assert msg.id == "MSG-1"
    assert msg.thread_id == "THR-1"
    assert msg.subject == "uOS Weekly Compliance"
    assert msg.sender == "noreply@uos.example"
    assert msg.received_at == "Wed, 13 May 2026 14:05:00 +0000"
    assert ("text/plain", "plain body") in msg.body_parts
    assert ("text/html", "<p>html body</p>") in msg.body_parts
    assert msg.attachments == (
        Attachment(
            filename="compliance.csv",
            mime_type="text/csv",
            attachment_id="ATT-1",
            size=1024,
        ),
    )


def test_message_from_payload_handles_single_part_text_email() -> None:
    """Plain-text uOS emails sometimes ship without a parts tree."""
    encoded = base64.urlsafe_b64encode(b"just one part").decode("ascii")
    payload = {
        "id": "MSG-2",
        "threadId": "THR-2",
        "payload": {
            "mimeType": "text/plain",
            "headers": [{"name": "Subject", "value": "tiny"}],
            "body": {"data": encoded},
        },
    }
    msg = message_from_payload(payload)
    assert msg.body_parts == (("text/plain", "just one part"),)
    assert msg.attachments == ()


# ---------------------------------------------------------------------------
# Credential loading
# ---------------------------------------------------------------------------


def _fake_token_json() -> dict[str, Any]:
    return {
        "token": "ya29.fake",
        "refresh_token": "1//fake",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "fake.apps.googleusercontent.com",
        "client_secret": "secret",
        "scopes": list(SCOPES),
    }


def test_decode_token_b64_round_trips() -> None:
    src = _fake_token_json()
    encoded = base64.b64encode(json.dumps(src).encode("ascii")).decode("ascii")
    assert _decode_token_b64(encoded) == src


def test_decode_token_b64_rejects_empty() -> None:
    with pytest.raises(ValueError):
        _decode_token_b64("")


def test_decode_token_b64_rejects_non_object() -> None:
    encoded = base64.b64encode(b'"a string"').decode("ascii")
    with pytest.raises(ValueError):
        _decode_token_b64(encoded)


def test_load_credentials_prefers_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    encoded = base64.b64encode(
        json.dumps(_fake_token_json()).encode("ascii")
    ).decode("ascii")
    # Force the file path to *not* exist so we can confirm the env wins.
    monkeypatch.setattr(gmail_client.settings, "gmail_token_json_b64", encoded)

    creds = load_credentials(token_path=tmp_path / "missing.json")
    assert list(creds.scopes) == list(SCOPES)
    assert creds.refresh_token == "1//fake"


def test_load_credentials_falls_back_to_token_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(gmail_client.settings, "gmail_token_json_b64", "")
    path = tmp_path / "token.json"
    path.write_text(json.dumps(_fake_token_json()))

    creds = load_credentials(token_path=path)
    assert creds.refresh_token == "1//fake"


def test_load_credentials_raises_when_no_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(gmail_client.settings, "gmail_token_json_b64", "")
    with pytest.raises(FileNotFoundError):
        load_credentials(token_path=tmp_path / "absent.json")


def test_refresh_if_needed_noop_when_valid() -> None:
    creds = MagicMock()
    creds.valid = True
    out = _refresh_if_needed(creds)
    assert out is creds
    creds.refresh.assert_not_called()


def test_refresh_if_needed_calls_refresh_and_writes_back(tmp_path: Path) -> None:
    creds = MagicMock()
    creds.valid = False
    creds.expired = True
    creds.refresh_token = "1//fake"
    creds.to_json.return_value = '{"token":"refreshed"}'

    path = tmp_path / "token.json"
    path.write_text("{}")
    out = _refresh_if_needed(creds, token_path=path)
    assert out is creds
    creds.refresh.assert_called_once()
    assert path.read_text() == '{"token":"refreshed"}'


def test_refresh_if_needed_does_not_write_back_when_no_token_path() -> None:
    creds = MagicMock()
    creds.valid = False
    creds.expired = True
    creds.refresh_token = "1//fake"
    _refresh_if_needed(creds, token_path=None)
    creds.refresh.assert_called_once()


def test_refresh_if_needed_raises_without_refresh_token() -> None:
    creds = MagicMock()
    creds.valid = False
    creds.expired = True
    creds.refresh_token = None
    with pytest.raises(RuntimeError, match="re-run"):
        _refresh_if_needed(creds)


# ---------------------------------------------------------------------------
# Client (mock service)
# ---------------------------------------------------------------------------


def _make_mock_service(
    *,
    pages: list[dict[str, Any]] | None = None,
    get_payload: dict[str, Any] | None = None,
    attachment_data: str | None = None,
) -> MagicMock:
    """Build a Mock for ``build('gmail','v1', ...)``.

    The Gmail client builder returns an object whose
    ``users().messages().list/.get/.attachments().get`` paths each
    expose ``.execute()``. We rebuild that nesting with MagicMocks so a
    single fixture covers every call shape we exercise.
    """
    service = MagicMock()
    users = service.users.return_value
    messages = users.messages.return_value

    pages = pages or [{"messages": []}]
    list_req_iter = iter([MagicMock(execute=lambda p=p: p) for p in pages])
    messages.list.side_effect = lambda **_kwargs: next(list_req_iter)

    if get_payload is not None:
        messages.get.return_value.execute.return_value = get_payload

    if attachment_data is not None:
        attachments = messages.attachments.return_value
        attachments.get.return_value.execute.return_value = {
            "data": attachment_data
        }
    return service


def test_search_paginates_until_max_results_reached() -> None:
    pages = [
        {
            "messages": [
                {"id": "m1", "threadId": "t1"},
                {"id": "m2", "threadId": "t2"},
            ],
            "nextPageToken": "TOKEN",
        },
        {"messages": [{"id": "m3", "threadId": "t3"}]},
    ]
    service = _make_mock_service(pages=pages)
    client = GmailClient(service=service)
    results = client.search("label:UoS", max_results=5)
    assert [m.id for m in results] == ["m1", "m2", "m3"]


def test_search_caps_at_max_results() -> None:
    pages = [
        {
            "messages": [
                {"id": f"m{i}", "threadId": f"t{i}"} for i in range(100)
            ],
            "nextPageToken": "TOKEN",
        },
    ]
    service = _make_mock_service(pages=pages)
    client = GmailClient(service=service)
    results = client.search("label:UoS", max_results=3)
    assert len(results) == 3


def test_search_with_max_results_zero_short_circuits() -> None:
    service = _make_mock_service(pages=[{"messages": []}])
    client = GmailClient(service=service)
    assert client.search("anything", max_results=0) == []
    service.users.return_value.messages.return_value.list.assert_not_called()


def test_get_message_round_trips_payload() -> None:
    encoded = base64.urlsafe_b64encode(b"hi").decode("ascii")
    payload = {
        "id": "MSG-99",
        "threadId": "THR-99",
        "payload": {
            "mimeType": "text/plain",
            "headers": [{"name": "Subject", "value": "weekly"}],
            "body": {"data": encoded},
        },
    }
    service = _make_mock_service(get_payload=payload)
    client = GmailClient(service=service)
    msg = client.get_message("MSG-99")
    assert isinstance(msg, Message)
    assert msg.subject == "weekly"
    assert msg.body_parts == (("text/plain", "hi"),)


def test_get_message_requires_id() -> None:
    service = _make_mock_service()
    client = GmailClient(service=service)
    with pytest.raises(ValueError):
        client.get_message("")


def test_get_attachment_decodes_urlsafe_b64() -> None:
    data = base64.urlsafe_b64encode(b"ATTACHMENT-BYTES").decode("ascii").rstrip("=")
    service = _make_mock_service(attachment_data=data)
    client = GmailClient(service=service)
    out = client.get_attachment("MSG-1", "ATT-1")
    assert out == b"ATTACHMENT-BYTES"


def test_get_attachment_requires_both_ids() -> None:
    service = _make_mock_service()
    client = GmailClient(service=service)
    with pytest.raises(ValueError):
        client.get_attachment("", "ATT-1")
    with pytest.raises(ValueError):
        client.get_attachment("MSG-1", "")
