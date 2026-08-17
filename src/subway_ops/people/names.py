"""Name normalization and display-name derivation — SPEC-PPL-001 AC-026, AC-027.

Pure functions. No database, no I/O, no imports from ``subway_ops.db`` — the
whole module is unit-testable with nothing running, and T-0005's
FORBIDDEN_ACTIONS make that a hard constraint rather than a preference.

Why these are worth their own module: the POS emits names that were typed by
whoever was standing at the terminal, and the measurements behind B-0014 are
blunt about it. 250 distinct clerk_ids across 399 (clerk_id, store) pairs; 56
clerk_ids carrying more than one name; ``singh, bir`` and ``bir`` being the same
human under the same PIN. Every downstream question about a person — hours,
wages, certificates, bonuses — starts by deciding whether two strings refer to
the same human, and that decision starts here.
"""

from __future__ import annotations

import re

#: Any run of whitespace, including the tabs and doubled spaces that show up in
#: real POS entries.
_WHITESPACE = re.compile(r"\s+")


def normalize_name(raw: str) -> str:
    """Lowercase, strip, and collapse internal whitespace.

    The comparison form, not a display form. It exists so that AC-005's linking
    rule — exact ``clerk_id`` plus exact normalized name (B-0014 → B) — can be
    exact without being brittle about the three differences that are always
    noise: case, surrounding space, and doubled internal space.

    Deliberately conservative. It does **not** strip punctuation, reorder
    tokens, drop middle names, or do anything fuzzy. B-0014 measured what
    happens when linking is loose: PIN ``8`` appears under 5 different names at
    5 stores, and ``samir, samir`` appears at 5 stores under 6 clerk_ids.
    Over-linking silently fuses two people's hours, wages and certificates, and
    nothing downstream ever notices. Under-linking leaves two rows that office
    merges in a few seconds, with the merge recorded in
    ``ops_employee_identity_log``. The asymmetry is the entire argument.

    Idempotent: ``normalize_name(normalize_name(x)) == normalize_name(x)``, so
    it is safe to apply to a value that may already be normalized, which the
    derivation does on every run.
    """
    return _WHITESPACE.sub(" ", raw.strip()).lower()


def _capitalize_token(token: str) -> str:
    """Upper-case the first character, lower-case the rest. ``BIR`` -> ``Bir``.

    Only ever called on tokens from ``str.split()``, which never yields an empty
    string, so there is no empty-input guard to write.
    """
    return token[0].upper() + token[1:].lower()


def derive_display_name(observed: str) -> str:
    """Derive ``First Last`` from ``LAST, FIRST``; otherwise pass through verbatim.

    AC-026 is the parse path, AC-027 the fallback, and B-0018 is the decision
    behind both: derive where the form is recognisable, let office override
    where it is not, and never lose what the POS actually said.

    **What counts as "of the form ``LAST, FIRST``" — exactly one comma.** AC-026
    governs that form; AC-027 governs everything else, and a string with two
    commas (``smith, john, jr``) or none (``maria flores``) is not that form, so
    it returns unchanged. Reading it this way keeps the rule stated rather than
    inferred: there is no guessing about which comma separates the surname, and
    no silently-dropped suffix. The cost is that a genuine ``LAST, FIRST, SUFFIX``
    is not parsed — it lands on office's desk as a display name to correct,
    which is precisely the escape hatch AC-028 guarantees.

    **Verbatim means verbatim.** ``bir`` stays ``bir``, lowercase and all. The
    fallback path does not capitalize, because AC-027 says "use it verbatim" and
    a helpfully-capitalized value would be a derived value wearing the costume
    of an observed one.

    Capitalization on the parse path is deliberately simple: first character up,
    the rest down, per whitespace-separated token. It gets ``singh, bir`` to
    ``Bir Singh`` and ``REDWAN, SHAH`` to ``Shah Redwan``. It gets ``o'brien``
    to ``O'brien``, which is wrong, and ``mcdonald`` to ``Mcdonald``, which is
    also wrong. Both are left wrong on purpose: any rule clever enough to fix
    them is clever enough to mangle a name it has never seen, and B-0018 already
    provides the correct repair — office types the right thing once and AC-028
    guarantees no later derivation run overwrites it. A wrong name that a human
    can fix permanently beats a heuristic nobody can predict.
    """
    if observed.count(",") != 1:
        return observed

    last, _, first = observed.partition(",")
    last_part = last.strip()
    first_part = first.strip()

    # "singh," or ", bir" is not two names. Neither half may be empty, or the
    # result would be a display name with a dangling space and half a person.
    if not last_part or not first_part:
        return observed

    given = " ".join(_capitalize_token(t) for t in first_part.split())
    family = " ".join(_capitalize_token(t) for t in last_part.split())
    return f"{given} {family}"
