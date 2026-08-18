"""Parse a University of Subway training-compliance email.

The uOS report ships as one of three payload shapes:

- A **CSV attachment** (preferred — easy to tabulate).
- An **HTML body** with one or more tables.
- A **PDF attachment** whose first page holds a table.

Each yields the same shape of output: ``ParsedReport(report_date,
rows, unparsed_rows)``. ``rows`` are validated ``ComplianceRow``
records ready to UPSERT into ``stg_uos_compliance``; ``unparsed_rows``
carry the raw text + reason for any line the parser couldn't classify
so the surrounding ``track_job`` can land them in metadata.

Status string normalisation is intentionally loose: uOS swaps wording
("Past Due" vs "Overdue") between quarterly releases, so the mapping
is a substring check against several known synonyms. Anything that
falls through is logged but does not crash the ingest.

This module is intentionally **pure**: input = bytes / strings,
output = dataclasses. No DB / no Gmail / no clock — those live in
``subway_ops.uos.ingest``.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import structlog
from bs4 import BeautifulSoup, Tag
from pypdf import PdfReader

log = structlog.get_logger(__name__)

# Canonical status strings persisted in stg_uos_compliance.
STATUS_COMPLETE = "complete"
STATUS_OVERDUE = "overdue"
STATUS_PENDING = "pending"

# Lowercase synonym lookups. Order matters: "overdue" should win over
# "due" because the substring "due" appears in both, and "past due"
# means overdue. We resolve in priority order: complete → overdue →
# pending.
_COMPLETE_SYNONYMS = ("complete", "completed", "✓", "passed", "done", "finished")
_OVERDUE_SYNONYMS = ("overdue", "past due", "expired", "late")
_PENDING_SYNONYMS = (
    "pending",
    "not started",
    "in progress",
    "incomplete",
    "due",
    "scheduled",
    "n/a",
)

# Tokens we accept as column headers when mapping to our canonical row
# fields. Lowercase. A header containing any of these tokens (substring
# match) wins the field. Order inside a tuple is don't-care; outer
# order picks the first matching field if a header contains multiple
# tokens (e.g. "Employee Name").
_HEADER_TOKENS: dict[str, tuple[str, ...]] = {
    "restaurant_number": ("restaurant", "store #", "store number", "store"),
    "employee_name": ("employee", "name", "associate", "team member"),
    "course_name": ("course", "training", "module", "topic"),
    "status": ("status", "completion", "state"),
    "completed_at": ("completed", "completion date", "date"),
}

# Pattern for a store number (3-5 digits — Subway franchise numbers
# fit in 4 digits today but the dataset has 5-digit acquired stores).
_STORE_NUMBER_RE = re.compile(r"\b(\d{3,5})\b")


@dataclass(frozen=True)
class ComplianceRow:
    """One row destined for ``stg_uos_compliance``."""

    restaurant_number: str
    employee_name: str
    course_name: str
    completion_status: str
    completed_at: date | None


@dataclass(frozen=True)
class UnparsedRow:
    """A row the parser saw but couldn't classify."""

    reason: str
    raw: dict[str, Any] | str


@dataclass(frozen=True)
class ParsedReport:
    """The whole digest of one uOS email."""

    report_date: date
    rows: tuple[ComplianceRow, ...] = ()
    unparsed_rows: tuple[UnparsedRow, ...] = ()
    source_format: str = ""  # 'csv' | 'html' | 'pdf'
    notes: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Status + date normalisation
# ---------------------------------------------------------------------------


def normalise_status(raw: str) -> str | None:
    """Return one of the three canonical statuses or ``None`` if unrecognised.

    Word-boundary regex matching so quarterly wording tweaks ("Past
    Due" → "Overdue") don't require a code change, but ``Incomplete``
    isn't accidentally classified as ``Complete`` because the
    substring ``complete`` appears inside it. Resolution order:
    pending (most specific — handles ``Incomplete``) → overdue →
    complete. Each tier only matches when its token appears as a
    standalone word.
    """
    if not raw:
        return None
    s = raw.strip().lower()
    if not s:
        return None
    # Order matters. Overdue first: "Past Due" contains "due" which is a
    # pending synonym; overdue is more specific. Complete next: word-
    # boundary matching means "complete" does NOT match inside
    # "incomplete", so checking it before pending is safe. Pending is the
    # last-resort tier.
    for tier, status in (
        (_OVERDUE_SYNONYMS, STATUS_OVERDUE),
        (_COMPLETE_SYNONYMS, STATUS_COMPLETE),
        (_PENDING_SYNONYMS, STATUS_PENDING),
    ):
        for token in tier:
            # Use word-boundary regex when the token is alphanumeric;
            # symbol-only tokens like "✓" don't have word boundaries
            # so we substring-match those directly.
            if token.isalnum() or " " in token:
                pattern = r"\b" + re.escape(token) + r"\b"
                if re.search(pattern, s):
                    return status
            elif token in s:
                return status
    return None


_DATE_FORMATS = (
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%m/%d/%y",
    "%d-%b-%Y",
    "%b %d, %Y",
    "%B %d, %Y",
)


def parse_date(raw: str | None) -> date | None:
    """Best-effort date parser for the messy ``completed_at`` cell.

    Returns ``None`` for blank / unparseable values. uOS dates are
    almost always US-style ``MM/DD/YYYY`` but historical CSV exports
    leak ISO and abbreviated forms too.
    """
    if not raw:
        return None
    s = raw.strip()
    if not s or s.lower() in {"n/a", "-", "none", "null"}:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def extract_store_number(text: str) -> str | None:
    """Pull a 3-5 digit store number out of a label string.

    "Store 4092" → "4092"; "12345 Main St" → "12345". Returns
    ``None`` when there's no number-like token at all. Callers must
    still verify the result is a known store before persisting.
    """
    if not text:
        return None
    m = _STORE_NUMBER_RE.search(text)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Header mapping
# ---------------------------------------------------------------------------


def _map_headers(headers: list[str]) -> dict[str, int]:
    """Map normalised field names → column index based on header text."""
    out: dict[str, int] = {}
    for idx, header in enumerate(headers):
        if header is None:
            continue
        h = header.strip().lower()
        if not h:
            continue
        for field_name, tokens in _HEADER_TOKENS.items():
            if field_name in out:
                continue
            if any(tok in h for tok in tokens):
                out[field_name] = idx
                break
    return out


def _row_from_cells(
    cells: list[str],
    header_map: dict[str, int],
    *,
    default_store: str | None,
) -> tuple[ComplianceRow | None, UnparsedRow | None]:
    """Turn one row of cell strings into a ``ComplianceRow`` or
    classify it as unparsed."""

    def cell(field_name: str) -> str:
        idx = header_map.get(field_name)
        if idx is None or idx >= len(cells):
            return ""
        return (cells[idx] or "").strip()

    store_raw = cell("restaurant_number") or default_store or ""
    store = extract_store_number(store_raw) if store_raw else None
    employee = cell("employee_name")
    course = cell("course_name")
    status_raw = cell("status")
    status = normalise_status(status_raw)
    completed_at = parse_date(cell("completed_at"))

    missing: list[str] = []
    if not store:
        missing.append("restaurant_number")
    if not employee:
        missing.append("employee_name")
    if not course:
        missing.append("course_name")
    if status is None:
        missing.append("completion_status")

    if missing:
        return None, UnparsedRow(
            reason=f"missing/unrecognised fields: {','.join(missing)}",
            raw={
                "cells": cells,
                "store_raw": store_raw,
                "status_raw": status_raw,
            },
        )

    # mypy: at this point store/employee/course/status are all truthy
    # strings, so the assert is documentation, not a runtime cost worth
    # worrying about (the function is called per-row in batches).
    assert store is not None and status is not None
    return (
        ComplianceRow(
            restaurant_number=store,
            employee_name=employee,
            course_name=course,
            completion_status=status,
            completed_at=completed_at,
        ),
        None,
    )


# ---------------------------------------------------------------------------
# CSV parsing
# ---------------------------------------------------------------------------


def parse_csv(data: bytes | str, *, report_date: date) -> ParsedReport:
    """Parse a uOS CSV attachment.

    The CSV may have a banner row before the real header (uOS exports
    sometimes leak the report title into row 0). We try the first
    non-empty row as the header; if it doesn't map any of our fields,
    we drop it and try the next one.
    """
    text = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else data
    # Strip a UTF-8 BOM if present — uOS Windows-line exports include one.
    text = text.lstrip("﻿")
    reader = list(csv.reader(io.StringIO(text)))
    if not reader:
        return ParsedReport(report_date=report_date, source_format="csv")

    header_row_idx, header_map = _find_header_row(reader)
    if header_row_idx is None or not header_map:
        return ParsedReport(
            report_date=report_date,
            source_format="csv",
            unparsed_rows=(
                UnparsedRow(
                    reason="no recognisable header row",
                    raw={"first_rows": reader[:5]},
                ),
            ),
        )

    rows: list[ComplianceRow] = []
    unparsed: list[UnparsedRow] = []
    for raw_row in reader[header_row_idx + 1 :]:
        if not any((c or "").strip() for c in raw_row):
            continue  # silently skip blank rows
        row, bad = _row_from_cells(raw_row, header_map, default_store=None)
        if row is not None:
            rows.append(row)
        elif bad is not None:
            unparsed.append(bad)
    return ParsedReport(
        report_date=report_date,
        rows=tuple(rows),
        unparsed_rows=tuple(unparsed),
        source_format="csv",
    )


def _find_header_row(
    rows: list[list[str]],
) -> tuple[int | None, dict[str, int]]:
    """Scan the first few rows for one that yields a usable header map."""
    for idx, row in enumerate(rows[:5]):
        hm = _map_headers(row)
        # Require at least three of the five field types to be mapped
        # so a single stray "Status" column header in a banner row
        # doesn't trigger.
        if len(hm) >= 3:
            return idx, hm
    return None, {}


# ---------------------------------------------------------------------------
# HTML parsing
# ---------------------------------------------------------------------------


def parse_html(html: str, *, report_date: date) -> ParsedReport:
    """Parse the largest ``<table>`` in an HTML body.

    "Largest" = the table with the most ``<tr>`` rows. Subway's HTML
    emails tend to embed multiple framing tables for layout; the
    actual data table is invariably the biggest one. If the largest
    table doesn't yield any recognisable headers we fall through to
    classifying every row as unparsed.
    """
    if not html:
        return ParsedReport(report_date=report_date, source_format="html")
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        return ParsedReport(
            report_date=report_date,
            source_format="html",
            unparsed_rows=(UnparsedRow(reason="no <table> in body", raw=html[:200]),),
        )
    biggest = max(tables, key=lambda t: len(t.find_all("tr")))
    return _parse_html_table(biggest, report_date=report_date)


def _parse_html_table(table: Tag, *, report_date: date) -> ParsedReport:
    trs = table.find_all("tr")
    text_rows: list[list[str]] = []
    for tr in trs:
        if not isinstance(tr, Tag):
            continue
        cells = [c.get_text(strip=True) for c in tr.find_all(["th", "td"]) if isinstance(c, Tag)]
        text_rows.append(cells)

    header_idx, header_map = _find_header_row(text_rows)
    if header_idx is None or not header_map:
        return ParsedReport(
            report_date=report_date,
            source_format="html",
            unparsed_rows=(
                UnparsedRow(
                    reason="no recognisable header row",
                    raw={"first_rows": text_rows[:5]},
                ),
            ),
        )
    rows: list[ComplianceRow] = []
    unparsed: list[UnparsedRow] = []
    for raw_row in text_rows[header_idx + 1 :]:
        if not any((c or "").strip() for c in raw_row):
            continue
        row, bad = _row_from_cells(raw_row, header_map, default_store=None)
        if row is not None:
            rows.append(row)
        elif bad is not None:
            unparsed.append(bad)
    return ParsedReport(
        report_date=report_date,
        rows=tuple(rows),
        unparsed_rows=tuple(unparsed),
        source_format="html",
    )


# ---------------------------------------------------------------------------
# PDF parsing
# ---------------------------------------------------------------------------


def parse_pdf(data: bytes, *, report_date: date) -> ParsedReport:
    """Parse a uOS PDF attachment by extracting whitespace-aligned text.

    PDFs don't have semantic rows the way CSVs / HTML do — we read the
    text per page and split on newlines, then try to interpret each
    line as a whitespace-separated row. A real uOS PDF (when one
    lands) may need a more structured extractor; this implementation
    treats anything past the first recognisable header line as data.
    """
    if not data:
        return ParsedReport(report_date=report_date, source_format="pdf")
    reader = PdfReader(io.BytesIO(data))
    full_text_lines: list[list[str]] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        for line in text.splitlines():
            cells = _split_pdf_row(line)
            if cells:
                full_text_lines.append(cells)
    if not full_text_lines:
        return ParsedReport(
            report_date=report_date,
            source_format="pdf",
            unparsed_rows=(UnparsedRow(reason="empty pdf text extraction", raw=""),),
        )
    header_idx, header_map = _find_header_row(full_text_lines)
    if header_idx is None or not header_map:
        return ParsedReport(
            report_date=report_date,
            source_format="pdf",
            unparsed_rows=tuple(
                UnparsedRow(reason="no recognisable header row", raw=" ".join(r))
                for r in full_text_lines[:5]
            ),
        )

    rows: list[ComplianceRow] = []
    unparsed: list[UnparsedRow] = []
    for cells in full_text_lines[header_idx + 1 :]:
        row, bad = _row_from_cells(cells, header_map, default_store=None)
        if row is not None:
            rows.append(row)
        elif bad is not None:
            unparsed.append(bad)
    return ParsedReport(
        report_date=report_date,
        rows=tuple(rows),
        unparsed_rows=tuple(unparsed),
        source_format="pdf",
    )


def _split_pdf_row(line: str) -> list[str]:
    """Tokenise a single PDF text line into cells.

    Heuristic: split on runs of two-or-more spaces (typical table
    columns); fall back to single-space split when the line has no
    multi-space runs. Skip empty results.
    """
    s = line.rstrip()
    if not s.strip():
        return []
    multi = re.split(r"\s{2,}", s.strip())
    if len(multi) >= 2:
        return [c.strip() for c in multi if c.strip()]
    return [s.strip()]


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def detect_format(*, filename: str, mime_type: str) -> str:
    """Pick the parser format from MIME + filename.

    Order: CSV first (cheapest), then PDF, then HTML. Anything else
    falls through as empty string and the caller treats the email as
    having no usable payload.
    """
    name = (filename or "").lower()
    mime = (mime_type or "").lower()
    if mime == "text/csv" or name.endswith(".csv"):
        return "csv"
    if mime == "application/pdf" or name.endswith(".pdf"):
        return "pdf"
    if mime.startswith("text/html") or name.endswith((".html", ".htm")):
        return "html"
    return ""


def parse_attachment(
    *,
    data: bytes,
    filename: str,
    mime_type: str,
    report_date: date,
) -> ParsedReport:
    """Dispatch on detected format. Used by the ingest layer."""
    fmt = detect_format(filename=filename, mime_type=mime_type)
    if fmt == "csv":
        return parse_csv(data, report_date=report_date)
    if fmt == "pdf":
        return parse_pdf(data, report_date=report_date)
    if fmt == "html":
        return parse_html(data.decode("utf-8", errors="replace"), report_date=report_date)
    log.warning("uos_parser_unknown_format", filename=filename, mime=mime_type)
    return ParsedReport(
        report_date=report_date,
        source_format="",
        unparsed_rows=(
            UnparsedRow(
                reason=f"unknown attachment format: {mime_type} {filename}",
                raw="",
            ),
        ),
    )


def parse_email_payload(
    *,
    html_body: str | None,
    attachments: Iterable[tuple[str, str, bytes]],
    report_date: date,
) -> ParsedReport:
    """Choose the best payload available: CSV attachment > PDF attachment >
    HTML body. Returns the first non-empty parse.

    ``attachments`` is an iterable of ``(filename, mime_type, bytes)``
    triples — what ``GmailClient.get_attachment`` produces alongside
    the ``Message.attachments`` metadata.
    """
    csvs: list[tuple[str, str, bytes]] = []
    pdfs: list[tuple[str, str, bytes]] = []
    for fname, mime, data in attachments:
        fmt = detect_format(filename=fname, mime_type=mime)
        if fmt == "csv":
            csvs.append((fname, mime, data))
        elif fmt == "pdf":
            pdfs.append((fname, mime, data))
    for fname, mime, data in csvs + pdfs:
        report = parse_attachment(
            data=data, filename=fname, mime_type=mime, report_date=report_date
        )
        if report.rows:
            return report
    if html_body:
        return parse_html(html_body, report_date=report_date)
    return ParsedReport(
        report_date=report_date,
        source_format="",
        unparsed_rows=(UnparsedRow(reason="no usable payload (no CSV/PDF/HTML)", raw=""),),
    )
