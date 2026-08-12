"""Mechanical checks for the laws this project used to state only in prose.

Every rule here was written in CLAUDE.md as non-negotiable and enforced by
nothing. Two of them were being broken in production when this package was
written: a malformed seed row had corrupted ``ref_stores``, and a test was
hard-deleting real history on every run.

A rule nobody checks is a suggestion. These make them rules.
"""

from __future__ import annotations

from ._base import Result

__all__ = ["CHECKS", "Result"]

# Import order is display order: cheapest and most-often-broken first.
from . import (
    check_extra_forbid,
    check_ingest_registered,
    check_migrations_append_only,
    check_money_types,
    check_no_print,
    check_seed_wellformed,
    check_track_job,
)

CHECKS = [
    check_seed_wellformed,
    check_migrations_append_only,
    check_money_types,
    check_no_print,
    check_track_job,
    check_ingest_registered,
    check_extra_forbid,
]
