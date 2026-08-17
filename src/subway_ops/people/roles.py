"""Role ordering and effective-role resolution — SPEC-PPL-001 AC-029, AC-030.

Pure. No database, no I/O.

codex 06 "Roles" is the governing sentence: role is a property of an
**assignment**, not of the person, because someone can be a shift lead at one
store and crew at another. This module holds the ladder and the one operation
that collapses several assignment roles into a single answer — and nothing
else, because collapsing is exactly the operation that must not happen by
accident.
"""

from __future__ import annotations

from collections.abc import Iterable

#: The ladder, ascending. SPEC-PPL-001 REQ-006 states it as
#: ``crew < shift_lead < store_manager < field_manager < office < owner``, and
#: codex 06 "Roles" lists the same six.
#:
#: **The ORDER of this tuple is load-bearing for permissions**, not a display
#: preference. Index position is authority: everything in this module compares
#: by it, so reordering two entries silently changes who outranks whom
#: everywhere at once. That is why ``test_role_order_matches_codex_ladder``
#: pins the exact sequence rather than the membership — a reordering compiles,
#: passes every behavioural test, and escalates crew above office.
#:
#: Note this is the JOB ladder, and it is not the same six as ``ref_users.role``
#: (migration 021), which is an ACCESS vocabulary carrying ``readonly`` and no
#: ``shift_lead``. The two are deliberately distinct; see 021's divergence note.
ROLE_ORDER: tuple[str, ...] = (
    "crew",
    "shift_lead",
    "store_manager",
    "field_manager",
    "office",
    "owner",
)


def effective_role(roles: Iterable[str]) -> str:
    """Return the highest role in ``roles`` by the ladder. AC-029.

    "Highest among their active assignments" — someone who is a shift lead at
    one store and crew at another has an effective role of ``shift_lead``.

    **Use this only where a single role is genuinely required** (AC-030): bonus
    eligibility, a role badge, anything that must name one thing. Store-scoped
    permission checks must use the **per-assignment** role instead, and passing
    them through here would be a privilege escalation with a plausible
    explanation — a shift lead at store A would silently acquire shift-lead
    authority over store B's cash and schedule. This function cannot enforce
    that distinction, which is why it is stated here and again at the call site
    in the roster service.

    Raises ``ValueError`` on an unknown role or an empty iterable, matching
    CON-003's use of ``ValueError`` for an out-of-contract argument.

    Empty raises rather than returning ``"crew"``. A person with no active
    assignment has no role, and the lowest rung is a real answer that would be
    indistinguishable from "we do not know" — the caller would carry on and
    grant crew-level access to someone the system has nothing on. An exception
    at least stops.

    Unknown raises rather than being skipped. A role this module has never heard
    of is either a typo or a ladder change that has not reached ``ROLE_ORDER``;
    silently ignoring it would resolve a person's authority from the roles that
    happened to be spelled correctly.
    """
    ranked = list(roles)
    if not ranked:
        raise ValueError(
            "effective_role() needs at least one role; a person with no active "
            "assignment has no effective role"
        )

    unknown = sorted(set(ranked) - set(ROLE_ORDER))
    if unknown:
        raise ValueError(f"unknown role(s) {unknown!r}; the ladder is {list(ROLE_ORDER)!r}")

    return max(ranked, key=ROLE_ORDER.index)
