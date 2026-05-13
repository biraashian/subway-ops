"""Read-only Gmail API client for the University of Subway pipeline.

Local dev loads OAuth credentials from ``./token.json`` (produced once
by ``scripts/gmail_get_token.py``). CI / production loads them from
``GMAIL_TOKEN_JSON_B64`` (base64 of the same file).

The client refreshes the access token transparently when it expires and
writes the refreshed credentials back to ``./token.json`` locally —
GitHub Actions runs are ephemeral, so the refresh just happens per run
and no write-back is required.

Two operations:

- ``search(query, max_results)`` runs a Gmail search expression
  (``label:uos newer_than:7d`` etc.) and returns lightweight
  ``Message`` records with id + thread id.
- ``get_message(msg_id)`` pulls the full payload — body parts and
  attachment metadata — so the caller can extract the uOS
  attachment in Task 6.2.

The Gmail API is read-only by scope (``gmail.readonly``); even if the
client somehow received write-shaped calls, Google would reject them.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from subway_ops.config import settings

log = structlog.get_logger(__name__)

# Read-only — list / read messages and download attachments. Any future
# need to mark-as-read or label messages would require a fresh OAuth
# consent flow with the broader scope.
SCOPES = ("https://www.googleapis.com/auth/gmail.readonly",)

# Default location for the OAuth token. The path is intentionally the
# current working directory so a developer who runs the get-token
# script gets a file they can see + base64-encode easily.
DEFAULT_TOKEN_PATH = Path("token.json")


@dataclass(frozen=True)
class Attachment:
    """One attachment on a Gmail message — metadata only.

    The actual bytes live behind ``attachment_id`` and the Gmail
    ``users().messages().attachments().get()`` endpoint. Task 6.2's
    parser pulls bytes when it needs them.
    """

    filename: str
    mime_type: str
    attachment_id: str
    size: int


@dataclass(frozen=True)
class Message:
    """A Gmail message we care about — id, thread, headers, body, atts.

    Body parts are flattened to a list of ``(mime_type, text)`` tuples
    so the caller doesn't have to walk a payload tree. ``raw_payload``
    is the original Gmail ``payload`` dict, kept around for archiving
    into ``raw_uos_emails`` (Task 6.2) and for any field the dataclass
    didn't surface.
    """

    id: str
    thread_id: str
    subject: str
    sender: str
    received_at: str | None
    body_parts: tuple[tuple[str, str], ...] = ()
    attachments: tuple[Attachment, ...] = ()
    raw_payload: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Credential loading
# ---------------------------------------------------------------------------


def _decode_token_b64(b64: str) -> dict[str, Any]:
    """Decode a base64'd token.json into the dict the SDK expects."""
    if not b64:
        raise ValueError("GMAIL_TOKEN_JSON_B64 is empty")
    decoded = base64.b64decode(b64.encode("ascii"))
    payload = json.loads(decoded)
    if not isinstance(payload, dict):
        raise ValueError("Decoded token.json is not a JSON object")
    return payload


def load_credentials(
    *,
    token_b64: str | None = None,
    token_path: Path | None = None,
) -> Credentials:
    """Load OAuth credentials, preferring the env variable.

    The env-variable path is the only one used in CI; the file path is
    the local-dev fallback after running ``gmail_get_token.py``. We
    consult one source — never both — so misconfigured local runs
    don't silently pick up stale CI tokens.
    """
    if token_b64 is None:
        token_b64 = settings.gmail_token_json_b64
    if token_b64:
        info = _decode_token_b64(token_b64)
        creds: Credentials = Credentials.from_authorized_user_info(  # type: ignore[no-untyped-call]
            info, list(SCOPES)
        )
        log.info("gmail_credentials_loaded", source="env")
        return creds

    path = token_path or DEFAULT_TOKEN_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"No Gmail credentials available: set GMAIL_TOKEN_JSON_B64 or "
            f"create {path} via scripts/gmail_get_token.py"
        )
    creds = Credentials.from_authorized_user_file(  # type: ignore[no-untyped-call]
        str(path), list(SCOPES)
    )
    log.info("gmail_credentials_loaded", source=str(path))
    return creds


def _refresh_if_needed(
    creds: Credentials, *, token_path: Path | None = None
) -> Credentials:
    """Refresh access token in-place if expired; write back when local."""
    if creds.valid:
        return creds
    if not creds.expired or not creds.refresh_token:
        # Without a refresh token the only recourse is re-running the
        # interactive OAuth flow — fail loudly so the operator sees it.
        raise RuntimeError(
            "Gmail credentials are invalid and cannot be refreshed; "
            "re-run scripts/gmail_get_token.py"
        )
    creds.refresh(Request())  # type: ignore[no-untyped-call]
    if token_path is not None and token_path.exists():
        # Only persist refreshed creds when we read them from disk.
        # GitHub Actions can't write back, so don't try.
        token_path.write_text(creds.to_json())  # type: ignore[no-untyped-call]
        log.info("gmail_credentials_refreshed", written_to=str(token_path))
    else:
        log.info("gmail_credentials_refreshed", written_to=None)
    return creds


# ---------------------------------------------------------------------------
# Payload extraction
# ---------------------------------------------------------------------------


def _walk_parts(payload: dict[str, Any]) -> Iterable[dict[str, Any]]:
    """Yield every leaf part in a Gmail payload tree."""
    if not payload:
        return
    parts = payload.get("parts")
    if not parts:
        yield payload
        return
    for part in parts:
        yield from _walk_parts(part)


def _decode_body(part: dict[str, Any]) -> str:
    """Decode a base64-url body part into a UTF-8 string.

    Gmail uses URL-safe base64 without padding; ``urlsafe_b64decode``
    handles the URL part but expects padding, so we pad here.
    """
    data = part.get("body", {}).get("data")
    if not data:
        return ""
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii")).decode(
        "utf-8", errors="replace"
    )


def _header(headers: list[dict[str, str]], name: str) -> str:
    """Pluck one header out of the Gmail header list, case-insensitive."""
    lower = name.lower()
    for h in headers or []:
        if h.get("name", "").lower() == lower:
            return h.get("value", "")
    return ""


def message_from_payload(payload: dict[str, Any]) -> Message:
    """Flatten a Gmail-API message dict into a ``Message`` dataclass."""
    p = payload.get("payload", {})
    headers = p.get("headers", []) or []
    body_parts: list[tuple[str, str]] = []
    attachments: list[Attachment] = []

    for part in _walk_parts(p):
        filename = part.get("filename") or ""
        mime = part.get("mimeType", "")
        body = part.get("body") or {}
        attachment_id = body.get("attachmentId")
        if filename and attachment_id:
            attachments.append(
                Attachment(
                    filename=filename,
                    mime_type=mime,
                    attachment_id=attachment_id,
                    size=int(body.get("size") or 0),
                )
            )
            continue
        if mime.startswith("text/"):
            text = _decode_body(part)
            if text:
                body_parts.append((mime, text))

    return Message(
        id=str(payload.get("id", "")),
        thread_id=str(payload.get("threadId", "")),
        subject=_header(headers, "Subject"),
        sender=_header(headers, "From"),
        received_at=_header(headers, "Date") or None,
        body_parts=tuple(body_parts),
        attachments=tuple(attachments),
        raw_payload=p,
    )


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class GmailClient:
    """Thin wrapper around the Gmail API ``users().messages()`` resource.

    Built once per process. Lazy-builds the underlying service so unit
    tests can inject a mock service via the ``service`` constructor
    argument and skip the network entirely.
    """

    def __init__(
        self,
        *,
        creds: Credentials | None = None,
        service: Any | None = None,
        token_path: Path | None = None,
        user_id: str = "me",
    ) -> None:
        self._user_id = user_id
        self._token_path = token_path or DEFAULT_TOKEN_PATH
        if service is not None:
            self._service = service
        else:
            self._creds = _refresh_if_needed(
                creds or load_credentials(token_path=token_path),
                token_path=self._token_path,
            )
            self._service = build("gmail", "v1", credentials=self._creds)

    # ---- public API --------------------------------------------------

    def search(self, query: str, max_results: int = 50) -> list[Message]:
        """Return message id / thread id pairs matching ``query``.

        Paginates internally so callers can ask for more than one
        Gmail page (default page = 100). The wrapped ``Message``
        instances have no body / attachments populated — call
        ``get_message`` per id when you need the payload.
        """
        if max_results <= 0:
            return []
        messages: list[Message] = []
        page_token: str | None = None
        while len(messages) < max_results:
            page_size = min(100, max_results - len(messages))
            req = self._service.users().messages().list(
                userId=self._user_id,
                q=query,
                maxResults=page_size,
                pageToken=page_token,
            )
            resp = req.execute()
            for m in resp.get("messages", []) or []:
                messages.append(
                    Message(
                        id=str(m.get("id", "")),
                        thread_id=str(m.get("threadId", "")),
                        subject="",
                        sender="",
                        received_at=None,
                    )
                )
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return messages[:max_results]

    def get_message(self, msg_id: str) -> Message:
        """Pull the full payload for one message, flattened to ``Message``."""
        if not msg_id:
            raise ValueError("msg_id is required")
        payload = (
            self._service.users()
            .messages()
            .get(userId=self._user_id, id=msg_id, format="full")
            .execute()
        )
        return message_from_payload(payload)

    def get_attachment(self, msg_id: str, attachment_id: str) -> bytes:
        """Pull raw attachment bytes for a known attachment id.

        Used by Task 6.2's parser — kept here so the API surface stays
        in one place.
        """
        if not msg_id or not attachment_id:
            raise ValueError("msg_id and attachment_id are required")
        resp = (
            self._service.users()
            .messages()
            .attachments()
            .get(userId=self._user_id, messageId=msg_id, id=attachment_id)
            .execute()
        )
        data = resp.get("data") or ""
        padded = data + "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode(padded.encode("ascii"))
