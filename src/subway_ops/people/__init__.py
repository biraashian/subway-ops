"""People — the person as a first-class record. SPEC-PPL-001.

Today the system knows stores and clerk PINs. This package is where it learns
about humans: who they are, where they work, what they are paid, and how two
rows that turn out to be one person get put back together.

T-0005 creates the package with its two pure modules. The rest of PLAN §2's
layout — ``derive``, ``identity``, ``wages``, ``cost``, ``completeness`` —
arrives in T-0006 through T-0009, and each adds its own re-exports here.

Everything exported below is pure: no database, no I/O, no clock.
"""

from __future__ import annotations

from subway_ops.people.names import derive_display_name, normalize_name
from subway_ops.people.roles import ROLE_ORDER, effective_role

__all__ = [
    "ROLE_ORDER",
    "derive_display_name",
    "effective_role",
    "normalize_name",
]
