"""Tests for ``subway_ops.uos.parser``.

CSV and HTML use byte-real fixtures under ``tests/fixtures/uos/`` so the
parser is exercised end-to-end against shapes we've actually seen
(synthetic until a real uOS email lands — see the task notes).

PDF parsing is unit-tested by monkey-patching ``pypdf.PdfReader`` to
return synthetic page objects: writing real PDF bytes without a
``reportlab``-class dependency is out of proportion to the value, and
the parsing logic that lives in our module is the ``_split_pdf_row``
heuristic + the same header-mapping path the CSV/HTML cases exercise.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from subway_ops.uos import parser
from subway_ops.uos.parser import (
    STATUS_COMPLETE,
    STATUS_OVERDUE,
    STATUS_PENDING,
    ComplianceRow,
    ParsedReport,
    UnparsedRow,
    _map_headers,
    _split_pdf_row,
    detect_format,
    extract_store_number,
    normalise_status,
    parse_csv,
    parse_date,
    parse_email_payload,
    parse_html,
    parse_pdf,
)

FIXTURES = Path(__file__).parent / "fixtures" / "uos"
REPORT_DATE = date(2026, 5, 13)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_normalise_status_priority_complete_wins() -> None:
    assert normalise_status("Complete") == STATUS_COMPLETE
    assert normalise_status("completed (was pending)") == STATUS_COMPLETE
    assert normalise_status("✓") == STATUS_COMPLETE
    assert normalise_status("Done") == STATUS_COMPLETE


def test_normalise_status_overdue_variants() -> None:
    assert normalise_status("Overdue") == STATUS_OVERDUE
    assert normalise_status("Past Due") == STATUS_OVERDUE
    assert normalise_status("Expired") == STATUS_OVERDUE
    assert normalise_status("LATE") == STATUS_OVERDUE


def test_normalise_status_pending_variants() -> None:
    assert normalise_status("Pending") == STATUS_PENDING
    assert normalise_status("Not Started") == STATUS_PENDING
    assert normalise_status("In Progress") == STATUS_PENDING
    assert normalise_status("Incomplete") == STATUS_PENDING


def test_normalise_status_returns_none_for_garbage() -> None:
    assert normalise_status("") is None
    assert normalise_status("   ") is None
    assert normalise_status("???") is None


def test_parse_date_accepts_common_formats() -> None:
    assert parse_date("2026-05-13") == date(2026, 5, 13)
    assert parse_date("05/13/2026") == date(2026, 5, 13)
    assert parse_date("5/13/26") == date(2026, 5, 13)
    assert parse_date("May 13, 2026") == date(2026, 5, 13)


def test_parse_date_rejects_blank_and_unparseable() -> None:
    assert parse_date(None) is None
    assert parse_date("") is None
    assert parse_date("   ") is None
    assert parse_date("N/A") is None
    assert parse_date("not a date") is None


def test_extract_store_number_finds_digit_runs() -> None:
    assert extract_store_number("Store 4092") == "4092"
    assert extract_store_number("4092 — Bellevue") == "4092"
    assert extract_store_number("12345") == "12345"
    assert extract_store_number("no digits") is None
    assert extract_store_number("") is None


def test_map_headers_first_match_wins() -> None:
    headers = ["Store #", "Employee Name", "Course", "Status", "Completed Date"]
    out = _map_headers(headers)
    assert out["restaurant_number"] == 0
    assert out["employee_name"] == 1
    assert out["course_name"] == 2
    assert out["status"] == 3
    assert out["completed_at"] == 4


def test_map_headers_skips_unknown_columns() -> None:
    headers = ["Garbage", "Employee", "Garbage 2", "Status", "Course"]
    out = _map_headers(headers)
    assert out == {"employee_name": 1, "status": 3, "course_name": 4}


def test_detect_format() -> None:
    assert detect_format(filename="r.csv", mime_type="text/csv") == "csv"
    assert detect_format(filename="r.pdf", mime_type="application/pdf") == "pdf"
    assert detect_format(filename="r.htm", mime_type="text/html") == "html"
    # Filename alone is enough.
    assert detect_format(filename="r.CSV", mime_type="application/octet-stream") == "csv"
    assert detect_format(filename="anything", mime_type="text/plain") == ""


def test_split_pdf_row_handles_multi_space_columns() -> None:
    line = "4092   Alice Johnson    Food Safety Basics   Complete   05/06/2026"
    cells = _split_pdf_row(line)
    assert cells == ["4092", "Alice Johnson", "Food Safety Basics", "Complete", "05/06/2026"]


def test_split_pdf_row_single_token_fallback() -> None:
    assert _split_pdf_row("Single line of text") == ["Single line of text"]
    assert _split_pdf_row("") == []
    assert _split_pdf_row("   ") == []


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------


def _csv_bytes() -> bytes:
    return (FIXTURES / "sample_report.csv").read_bytes()


def test_parse_csv_extracts_canonical_rows() -> None:
    report = parse_csv(_csv_bytes(), report_date=REPORT_DATE)
    assert report.report_date == REPORT_DATE
    assert report.source_format == "csv"

    by_employee = {
        (r.restaurant_number, r.employee_name, r.course_name): r for r in report.rows
    }
    alice_food = by_employee[("4092", "Alice Johnson", "Food Safety Basics")]
    assert alice_food.completion_status == STATUS_COMPLETE
    assert alice_food.completed_at == date(2026, 5, 6)

    alice_slicer = by_employee[("4092", "Alice Johnson", "Slicer Safety")]
    assert alice_slicer.completion_status == STATUS_PENDING
    assert alice_slicer.completed_at is None

    bob_food = by_employee[("4092", "Bob Patel", "Food Safety Basics")]
    assert bob_food.completion_status == STATUS_OVERDUE

    carol_food = by_employee[("4093", "Carol Singh", "Food Safety Basics")]
    assert carol_food.completion_status == STATUS_OVERDUE  # "Past Due"


def test_parse_csv_classifies_bad_rows_as_unparsed() -> None:
    report = parse_csv(_csv_bytes(), report_date=REPORT_DATE)
    # The fixture has a row with a blank store cell — that lands in unparsed.
    assert any(
        "restaurant_number" in u.reason for u in report.unparsed_rows
    ), report.unparsed_rows
    # The "99999" row with an unrecognised store is a valid ComplianceRow at
    # the parser layer — it's the ingest layer's job to filter to ref_stores.
    assert any(r.restaurant_number == "99999" for r in report.rows)


def test_parse_csv_handles_no_recognisable_header() -> None:
    raw = b"foo,bar,baz\n1,2,3\n4,5,6\n"
    report = parse_csv(raw, report_date=REPORT_DATE)
    assert report.rows == ()
    assert len(report.unparsed_rows) == 1
    assert "no recognisable header row" in report.unparsed_rows[0].reason


def test_parse_csv_strips_utf8_bom() -> None:
    # "﻿" (U+FEFF) prefixed banner row — Windows exports sometimes ship this.
    text = (
        "﻿Header banner\n"
        "Store,Employee,Course,Status,Date\n"
        "4092,Test,Course,Complete,05/01/2026\n"
    )
    report = parse_csv(text.encode(), report_date=REPORT_DATE)
    assert len(report.rows) == 1


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------


def _html_text() -> str:
    return (FIXTURES / "sample_report.html").read_text()


def test_parse_html_picks_largest_table() -> None:
    report = parse_html(_html_text(), report_date=REPORT_DATE)
    assert report.source_format == "html"
    # Three data rows in the second (larger) table; one blank row is silently
    # skipped.
    stores = sorted({r.restaurant_number for r in report.rows})
    assert stores == ["4092", "4093"]
    statuses = {r.completion_status for r in report.rows}
    assert statuses == {STATUS_COMPLETE, STATUS_PENDING, STATUS_OVERDUE}


def test_parse_html_no_table_returns_unparsed() -> None:
    report = parse_html("<html><body>no tables here</body></html>", report_date=REPORT_DATE)
    assert report.rows == ()
    assert any("no <table>" in u.reason for u in report.unparsed_rows)


def test_parse_html_empty_input() -> None:
    report = parse_html("", report_date=REPORT_DATE)
    assert report.rows == ()
    assert report.source_format == "html"


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------


class _FakePage:
    def __init__(self, text: str) -> None:
        self._text = text

    def extract_text(self) -> str:
        return self._text


def _fake_reader(text: str) -> Any:
    reader = MagicMock()
    reader.pages = [_FakePage(text)]
    return reader


def test_parse_pdf_extracts_rows_from_aligned_text() -> None:
    pdf_text = (
        "University of Subway — Weekly Compliance\n"
        "\n"
        "Store    Employee Name        Course               Status     Completed\n"
        "4092     Alice Johnson        Food Safety Basics   Complete   05/06/2026\n"
        "4092     Alice Johnson        Slicer Safety        Pending\n"
        "4093     Carol Singh          Food Safety Basics   Past Due\n"
    )
    with patch.object(parser, "PdfReader", return_value=_fake_reader(pdf_text)):
        report = parse_pdf(b"not used - mocked reader", report_date=REPORT_DATE)
    assert report.source_format == "pdf"
    assert len(report.rows) == 3
    statuses = {r.completion_status for r in report.rows}
    assert statuses == {STATUS_COMPLETE, STATUS_PENDING, STATUS_OVERDUE}


def test_parse_pdf_no_header_returns_unparsed() -> None:
    with patch.object(parser, "PdfReader", return_value=_fake_reader("garbage line\nanother\n")):
        report = parse_pdf(b"x", report_date=REPORT_DATE)
    assert report.rows == ()
    assert report.unparsed_rows


def test_parse_pdf_empty_bytes_short_circuits() -> None:
    report = parse_pdf(b"", report_date=REPORT_DATE)
    assert report.rows == ()
    assert report.source_format == "pdf"


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def test_parse_email_payload_prefers_csv_over_html() -> None:
    csv_bytes = _csv_bytes()
    html_str = _html_text()
    report = parse_email_payload(
        html_body=html_str,
        attachments=[("report.csv", "text/csv", csv_bytes)],
        report_date=REPORT_DATE,
    )
    assert report.source_format == "csv"
    assert any(r.restaurant_number == "4093" for r in report.rows)


def test_parse_email_payload_falls_back_to_html_when_csv_yields_zero_rows() -> None:
    empty_csv = b"foo,bar,baz\n1,2,3\n"
    html_str = _html_text()
    report = parse_email_payload(
        html_body=html_str,
        attachments=[("report.csv", "text/csv", empty_csv)],
        report_date=REPORT_DATE,
    )
    # parser fell through because CSV had no rows; HTML supplied the data.
    assert report.source_format == "html"
    assert report.rows


def test_parse_email_payload_no_payload_returns_empty_report() -> None:
    report = parse_email_payload(
        html_body=None, attachments=[], report_date=REPORT_DATE
    )
    assert report.rows == ()
    assert report.unparsed_rows
    assert "no usable payload" in report.unparsed_rows[0].reason


def test_compliance_row_is_immutable() -> None:
    row = ComplianceRow("4092", "A", "B", STATUS_COMPLETE, None)
    try:
        row.employee_name = "X"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("ComplianceRow should be frozen")


def test_parsed_report_defaults_are_empty_tuples() -> None:
    report = ParsedReport(report_date=REPORT_DATE)
    assert report.rows == ()
    assert report.unparsed_rows == ()
    assert report.source_format == ""


def test_unparsed_row_carries_reason_and_raw() -> None:
    u = UnparsedRow(reason="x", raw={"k": "v"})
    assert u.reason == "x"
    assert u.raw == {"k": "v"}
