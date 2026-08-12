"""Seed CSVs are well-formed and internally consistent.

This is the check that would have caught the store 10393 defect: its row in
``seed/stores.csv`` carried 6 fields where the header declares 7, so the
opening date shifted left into the timezone column. Nothing noticed, the row
was seeded to production, and ``ref_stores`` held
``timezone = 'October 18, 2023'`` for three months.

Two invariants:
  1. Every row has exactly as many fields as the header.
  2. Every store number referenced by another seed file exists in stores.csv.
"""

from __future__ import annotations

import csv
from pathlib import Path

from ._base import Result, failed, ok

NAME = "seed files well-formed"

# (file, column holding a comma-separated list of store numbers)
STORE_REF_COLUMNS = [
    ("field_managers.csv", "store_numbers_csv"),
    ("users.csv", "assigned_stores"),
]


def _field_count_violations(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        return [f"{path.name}: empty file"]
    width = len(rows[0])
    out = []
    for lineno, row in enumerate(rows[1:], start=2):
        if not row or (len(row) == 1 and not row[0].strip()):
            continue  # trailing blank line
        if len(row) != width:
            out.append(f"{path.name}:{lineno}: {len(row)} fields, header declares {width} -> {row}")
    return out


def _known_store_numbers(seed_dir: Path) -> set[str]:
    stores = seed_dir / "stores.csv"
    if not stores.exists():
        return set()
    with stores.open(newline="", encoding="utf-8") as fh:
        return {
            row["store_number"].strip() for row in csv.DictReader(fh) if row.get("store_number")
        }


def _reference_violations(seed_dir: Path, known: set[str]) -> list[str]:
    out = []
    for filename, column in STORE_REF_COLUMNS:
        path = seed_dir / filename
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8") as fh:
            for lineno, row in enumerate(csv.DictReader(fh), start=2):
                raw = (row.get(column) or "").strip()
                if not raw:
                    continue
                for number in (n.strip() for n in raw.split(",")):
                    if number and number not in known:
                        out.append(
                            f"{filename}:{lineno}: references store {number!r}, "
                            f"which is not in stores.csv"
                        )
    return out


def check(repo_root: Path) -> Result:
    seed_dir = repo_root / "seed"
    if not seed_dir.is_dir():
        return failed(NAME, "no seed/ directory", [str(seed_dir)])

    csvs = sorted(seed_dir.glob("*.csv"))
    violations: list[str] = []
    for path in csvs:
        violations.extend(_field_count_violations(path))
    violations.extend(_reference_violations(seed_dir, _known_store_numbers(seed_dir)))

    if violations:
        return failed(NAME, f"{len(violations)} problem(s)", violations)
    return ok(NAME, f"{len(csvs)} seed file(s) consistent")
