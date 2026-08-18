"""Tests for role ordering — SPEC-PPL-001 AC-029, AC-030.

Pure, no database.
"""

from __future__ import annotations

from itertools import pairwise

import pytest

from subway_ops.people.roles import ROLE_ORDER, effective_role


class TestRoleOrder:
    def test_role_order_matches_codex_ladder(self) -> None:
        """The exact sequence, not the membership.

        SPEC-PPL-001 REQ-006: ``crew < shift_lead < store_manager <
        field_manager < office < owner``; codex 06 "Roles" lists the same six.

        This asserts equality against the literal tuple on purpose. Index
        position IS authority in this module, so swapping two entries is a
        permission change that compiles, passes every behavioural test below,
        and escalates crew above office. A set comparison would not catch it and
        neither would any test that only checks "the highest one wins".
        """
        assert ROLE_ORDER == (
            "crew",
            "shift_lead",
            "store_manager",
            "field_manager",
            "office",
            "owner",
        )

    def test_role_order_is_strictly_ascending_in_authority(self) -> None:
        """Every role outranks the one before it, pairwise."""
        for lower, higher in pairwise(ROLE_ORDER):
            assert effective_role([lower, higher]) == higher

    def test_role_order_has_no_duplicates(self) -> None:
        assert len(set(ROLE_ORDER)) == len(ROLE_ORDER)


class TestEffectiveRole:
    def test_effective_role_returns_highest(self) -> None:
        """AC-029 — highest among the person's active assignments."""
        assert effective_role(["crew", "shift_lead"]) == "shift_lead"
        assert effective_role(["crew", "office", "store_manager"]) == "office"
        assert effective_role(["owner", "crew"]) == "owner"

    def test_effective_role_single_role(self) -> None:
        for role in ROLE_ORDER:
            assert effective_role([role]) == role

    def test_effective_role_is_order_independent(self) -> None:
        """The answer must not depend on how the query happened to sort rows."""
        assert effective_role(["office", "crew", "shift_lead"]) == "office"
        assert effective_role(["shift_lead", "crew", "office"]) == "office"

    def test_effective_role_ignores_duplicates(self) -> None:
        """Three crew assignments do not add up to a shift lead."""
        assert effective_role(["crew", "crew", "crew"]) == "crew"

    def test_effective_role_accepts_any_iterable(self) -> None:
        """PLAN §3 types the parameter as ``Iterable[str]``; a generator counts.

        The caller will be passing the result of a query, and consuming the
        iterable twice inside the function would silently return the wrong
        answer for a one-shot iterator.
        """
        assert effective_role(r for r in ("crew", "field_manager")) == "field_manager"
        assert effective_role({"crew", "store_manager"}) == "store_manager"

    def test_effective_role_rejects_unknown_role(self) -> None:
        """A role off the ladder is a typo or a ladder change, never a no-op.

        Skipping it would resolve someone's authority from whichever of their
        roles happened to be spelled correctly.
        """
        with pytest.raises(ValueError, match="unknown role"):
            effective_role(["crew", "regional_manager"])
        with pytest.raises(ValueError, match="unknown role"):
            effective_role(["CREW"])

    def test_effective_role_rejects_a_ref_users_only_role(self) -> None:
        """``readonly`` is an access level in ``ref_users``, not a job.

        The two six-role vocabularies are deliberately different (migration
        021). Feeding one to the other must fail loudly rather than resolve to
        something plausible.
        """
        with pytest.raises(ValueError, match="unknown role"):
            effective_role(["crew", "readonly"])

    def test_effective_role_on_empty_raises(self) -> None:
        """No active assignment is not the same as the lowest rung.

        Returning ``crew`` here would be indistinguishable from a real answer,
        and the caller would grant crew-level access to a person the system has
        nothing on.
        """
        with pytest.raises(ValueError, match="at least one role"):
            effective_role([])

    def test_effective_role_does_not_mutate_its_input(self) -> None:
        roles = ["crew", "office"]
        effective_role(roles)
        assert roles == ["crew", "office"]
