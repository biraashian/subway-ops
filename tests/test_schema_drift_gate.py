"""Tests for the declared-drift gate — D-024 (was B-0022).

All pure: the comparison operates on drift-line lists and snapshot JSON, so
none of this needs a database. That is deliberate — a gate whose own tests
need the thing it guards is a gate you stop running.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.schema_snapshot import compare_declaration, main, parse_declaration

# ---------------------------------------------------------------------------
# parse_declaration
# ---------------------------------------------------------------------------


def test_parse_ignores_blanks_and_comments() -> None:
    text = """
    # T-0003 — the worklist spine
    + table ops_worklist_items (11 columns)

    + ref_stores.nickname text   # added for the crew page
    """
    assert parse_declaration(text) == [
        "+ table ops_worklist_items (11 columns)",
        "+ ref_stores.nickname text",
    ]


def test_parse_empty_declaration_is_empty_list() -> None:
    assert parse_declaration("# nothing intended here\n\n") == []


# ---------------------------------------------------------------------------
# compare_declaration
# ---------------------------------------------------------------------------


def test_no_drift_and_no_declaration_matches() -> None:
    assert compare_declaration([], []) == ([], [])


def test_drift_with_matching_declaration_matches() -> None:
    lines = ["+ table a (2 columns)", "+ b.c text"]
    assert compare_declaration(lines, lines) == ([], [])


def test_declaration_is_order_insensitive() -> None:
    """A declaration is a set of facts, not a transcript."""
    observed = ["+ table a (2 columns)", "+ b.c text", "- d.e REMOVED"]
    declared = ["- d.e REMOVED", "+ table a (2 columns)", "+ b.c text"]
    assert compare_declaration(observed, declared) == ([], [])


def test_undeclared_drift_is_reported() -> None:
    undeclared, stale = compare_declaration(
        ["+ table a (2 columns)", "+ b.c text"], ["+ table a (2 columns)"]
    )
    assert undeclared == ["+ b.c text"]
    assert stale == []


def test_stale_declaration_is_reported() -> None:
    """Declared but not observed — worse than no declaration."""
    undeclared, stale = compare_declaration(
        ["+ table a (2 columns)"], ["+ table a (2 columns)", "+ b.c text"]
    )
    assert undeclared == []
    assert stale == ["+ b.c text"]


def test_both_directions_reported_together() -> None:
    undeclared, stale = compare_declaration(["+ x.y text"], ["+ p.q text"])
    assert undeclared == ["+ x.y text"]
    assert stale == ["+ p.q text"]


# ---------------------------------------------------------------------------
# main() — end to end over snapshot files
# ---------------------------------------------------------------------------


def _snapshot(tables: dict[str, list[str]]) -> dict[str, Any]:
    return {
        name: {
            "columns": {
                col: {"type": "text", "nullable": True} for col in cols
            },
            "primary_key": [],
        }
        for name, cols in tables.items()
    }


def _write(path: Path, payload: dict[str, Any]) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.fixture
def before(tmp_path: Path) -> Path:
    return _write(tmp_path / "before.json", _snapshot({"ref_stores": ["id"]}))


@pytest.fixture
def after_added(tmp_path: Path) -> Path:
    return _write(
        tmp_path / "after.json",
        _snapshot({"ref_stores": ["id"], "ops_worklist_items": ["id", "kind"]}),
    )


def _argv(before: Path, after: Path, expected: Path | None = None) -> list[str]:
    argv = ["--diff", "--before", str(before), "--after", str(after)]
    if expected is not None:
        argv += ["--expected", str(expected)]
    return argv


def test_no_drift_no_declaration_passes(before: Path, tmp_path: Path) -> None:
    same = _write(tmp_path / "same.json", _snapshot({"ref_stores": ["id"]}))
    assert main(_argv(before, same)) == 0


def test_drift_with_no_declaration_fails(before: Path, after_added: Path) -> None:
    """The original protection, preserved exactly."""
    assert main(_argv(before, after_added)) == 1


def test_drift_with_matching_declaration_passes(
    before: Path, after_added: Path, tmp_path: Path
) -> None:
    decl = tmp_path / "T-0003.txt"
    decl.write_text(
        "# intended: the worklist spine\n+ table ops_worklist_items (2 columns)\n",
        encoding="utf-8",
    )
    assert main(_argv(before, after_added, decl)) == 0


def test_drift_not_covered_by_declaration_fails(
    before: Path, after_added: Path, tmp_path: Path
) -> None:
    decl = tmp_path / "T-0003.txt"
    decl.write_text("+ table something_else (1 columns)\n", encoding="utf-8")
    assert main(_argv(before, after_added, decl)) == 1


def test_declaration_covering_absent_drift_fails(
    before: Path, tmp_path: Path
) -> None:
    """A stale declaration reds the gate even though nothing changed."""
    same = _write(tmp_path / "same.json", _snapshot({"ref_stores": ["id"]}))
    decl = tmp_path / "T-0003.txt"
    decl.write_text("+ table ops_worklist_items (2 columns)\n", encoding="utf-8")
    assert main(_argv(before, same, decl)) == 1


def test_missing_declaration_file_fails(
    before: Path, after_added: Path, tmp_path: Path
) -> None:
    """Named but absent is a failure, never a silent skip."""
    assert main(_argv(before, after_added, tmp_path / "nope.txt")) == 1


def test_failure_output_names_the_undeclared_lines(
    before: Path, after_added: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    decl = tmp_path / "T-0003.txt"
    decl.write_text("+ table wrong_table (1 columns)\n", encoding="utf-8")
    main(_argv(before, after_added, decl))
    out = capsys.readouterr().out
    assert "UNDECLARED" in out
    assert "ops_worklist_items" in out, "the undeclared line must be named"
    assert "STALE" in out
    assert "wrong_table" in out, "the stale line must be named"
