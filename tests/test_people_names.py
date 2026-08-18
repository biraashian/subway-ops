"""Tests for name helpers — SPEC-PPL-001 AC-026, AC-027.

No database, no fixtures, no network. If any of these ever needs a connection,
the module has stopped being pure and T-0005's first FORBIDDEN_ACTION has been
crossed.

The test data is real. T-0005's NOTES point at the observed names because they
are messier than anything invented: ``singh, bir`` and ``bir`` are the same
human under PIN 1998, and ``samir, samir`` appears at 5 stores under 6 clerk_ids.
"""

from __future__ import annotations

import pytest

from subway_ops.people.names import derive_display_name, normalize_name


class TestNormalizeName:
    def test_normalize_name_lowercases_trims_and_collapses_whitespace(self) -> None:
        assert normalize_name("  SINGH,   BIR  ") == "singh, bir"
        assert normalize_name("Maria   Flores") == "maria flores"
        assert normalize_name("\tredwan,\tshah\n") == "redwan, shah"

    def test_normalize_name_is_idempotent(self) -> None:
        """Applied to an already-normalized value it must change nothing.

        The derivation re-normalizes on every nightly run, so a function that
        drifted on a second application would slowly walk names away from the
        values already stored and quietly break AC-005's exact-match linking.
        """
        for raw in ("  SINGH,   BIR  ", "bir", "samir, samir", "", "   "):
            once = normalize_name(raw)
            assert normalize_name(once) == once

    def test_normalize_name_does_not_fuse_two_different_people(self) -> None:
        """B-0014's whole point: exact means exact.

        ``singh, bir`` and ``bir`` are in fact the same human, and normalization
        still keeps them apart. That is the accepted cost of choosing option B —
        office merges them, and the merge is recorded. The alternative fuses
        people who merely share a first name, which nothing downstream detects.
        """
        assert normalize_name("singh, bir") != normalize_name("bir")

    def test_normalize_name_preserves_punctuation(self) -> None:
        """Not a cleanup function. Stripping punctuation would be fuzzy matching."""
        assert normalize_name("O'BRIEN, PAT") == "o'brien, pat"


class TestDeriveDisplayName:
    def test_derive_display_name_from_last_comma_first(self) -> None:
        """AC-026 — ``LAST, FIRST`` becomes ``First Last``."""
        assert derive_display_name("singh, bir") == "Bir Singh"
        assert derive_display_name("redwan, shah") == "Shah Redwan"
        assert derive_display_name("samir, samir") == "Samir Samir"

    def test_derive_display_name_normalizes_case_on_the_parse_path(self) -> None:
        assert derive_display_name("SINGH, BIR") == "Bir Singh"
        assert derive_display_name("  singh ,  bir  ") == "Bir Singh"

    def test_derive_display_name_passes_through_unparseable(self) -> None:
        """AC-027 — verbatim, and verbatim includes the original case.

        ``bir`` stays ``bir``. Capitalizing it here would dress a value the POS
        supplied up as one this system derived.
        """
        assert derive_display_name("bir") == "bir"
        assert derive_display_name("maria flores") == "maria flores"
        assert derive_display_name("SAMIR") == "SAMIR"

    def test_derive_display_name_handles_extra_commas(self) -> None:
        """Two commas is not ``LAST, FIRST``, so AC-027 governs it.

        Nothing is dropped and no guess is made about which comma separates the
        surname. Office corrects it once and AC-028 keeps the correction.
        """
        assert derive_display_name("smith, john, jr") == "smith, john, jr"
        assert derive_display_name("a, b, c, d") == "a, b, c, d"

    def test_derive_display_name_on_empty_string(self) -> None:
        assert derive_display_name("") == ""
        assert derive_display_name("   ") == "   "

    def test_derive_display_name_on_a_dangling_comma(self) -> None:
        """One comma but only one name is not two names either."""
        assert derive_display_name("singh,") == "singh,"
        assert derive_display_name(", bir") == ", bir"
        assert derive_display_name(",") == ","

    def test_derive_display_name_keeps_multi_token_halves_together(self) -> None:
        """A two-word given name or surname survives intact."""
        assert derive_display_name("de la cruz, maria elena") == "Maria Elena De La Cruz"

    @pytest.mark.parametrize(
        ("observed", "expected"),
        [("o'brien, pat", "Pat O'brien"), ("mcdonald, sean", "Sean Mcdonald")],
    )
    def test_derive_display_name_capitalization_is_simple_and_known_imperfect(
        self, observed: str, expected: str
    ) -> None:
        """Pinning the known-wrong cases so they are a decision, not a surprise.

        ``O'brien`` and ``Mcdonald`` are both incorrect renderings. They are
        accepted because B-0018 pairs derivation with an office override that
        AC-028 protects, and because a cleverer rule mangles names it has never
        seen. If this test ever changes, it should change because someone chose
        a better rule — not because one slipped in.
        """
        assert derive_display_name(observed) == expected

    def test_derive_display_name_output_is_stable_under_re_derivation(self) -> None:
        """A derived name fed back in must not be re-parsed into something else.

        The nightly run sees stored values as well as fresh ones. ``Bir Singh``
        has no comma, so AC-027 returns it unchanged — the name does not
        oscillate between two forms on alternate nights.
        """
        once = derive_display_name("singh, bir")
        assert derive_display_name(once) == once
