"""People — the person as a first-class record. SPEC-PPL-001.

Today the system knows stores and clerk PINs. This package is where it learns
about humans: who they are, where they work, what they are paid, and how two
rows that turn out to be one person get put back together.

T-0005 created the package with its two pure modules; T-0007 adds ``wages`` and
``cost``. Still to come from PLAN §2's layout: ``derive``, ``identity`` and
``completeness``, in T-0006 and T-0009.

``names`` and ``roles`` are pure — no database, no I/O, no clock. ``wages`` and
``cost`` are not: they read and write the database. ``cost.allocate_overtime``
and ``cost.cost_hours`` are pure and importable on their own for exactly that
reason, since the overtime boundary is the part most worth testing without one.
"""

from __future__ import annotations

from subway_ops.people.cost import WeekCost, cost_week
from subway_ops.people.names import derive_display_name, normalize_name
from subway_ops.people.roles import ROLE_ORDER, effective_role
from subway_ops.people.wages import rate_in_force, read_wage, record_wage

__all__ = [
    "ROLE_ORDER",
    "WeekCost",
    "cost_week",
    "derive_display_name",
    "effective_role",
    "normalize_name",
    "rate_in_force",
    "read_wage",
    "record_wage",
]
