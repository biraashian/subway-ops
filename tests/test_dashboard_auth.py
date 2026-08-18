"""Tests for the dashboard auth helpers.

The helpers under test are pure — credentials shaping and visible-store
filtering — so we don't need Streamlit running.
"""

from __future__ import annotations

from subway_ops.dashboard.auth import (
    ALL_STORE_ROLES,
    UserRow,
    _normalise_assigned,
    build_credentials,
    is_owner,
    visible_stores,
)


def _user(
    *,
    email: str = "user@example.com",
    role: str = "field_manager",
    assigned: tuple[str, ...] | None = ("4092", "17967"),
) -> UserRow:
    return UserRow(
        email=email,
        display_name="Test User",
        role=role,
        password_hash="$2b$12$abc...",
        assigned_stores=assigned,
    )


def test_normalise_assigned_accepts_list() -> None:
    assert _normalise_assigned(["4092", "17967"]) == ("4092", "17967")


def test_normalise_assigned_accepts_csv_string() -> None:
    assert _normalise_assigned("4092, 17967 , 26529") == ("4092", "17967", "26529")


def test_normalise_assigned_none_stays_none() -> None:
    assert _normalise_assigned(None) is None


def test_build_credentials_shape() -> None:
    rows = [
        _user(email="alice@x.com"),
        _user(email="bob@x.com", role="owner"),
    ]
    creds = build_credentials(rows)
    assert set(creds.keys()) == {"usernames"}
    assert creds["usernames"]["alice@x.com"]["name"] == "Test User"
    assert creds["usernames"]["alice@x.com"]["password"].startswith("$2b$")
    assert creds["usernames"]["bob@x.com"]["email"] == "bob@x.com"


def test_visible_stores_owner_sees_everything() -> None:
    user = _user(role="owner", assigned=("4092",))
    assert "owner" in ALL_STORE_ROLES
    assert visible_stores(user, ["4092", "17967", "26529"]) == [
        "4092",
        "17967",
        "26529",
    ]


def test_visible_stores_field_manager_filtered_to_assigned() -> None:
    user = _user(role="field_manager", assigned=("4092", "17967"))
    assert visible_stores(user, ["4092", "17967", "26529", "39969"]) == [
        "4092",
        "17967",
    ]


def test_visible_stores_with_null_assigned_sees_everything() -> None:
    """Edge case from the seed: a user row with no assigned_stores list
    falls back to seeing the whole roster (the playbook's spec)."""
    user = _user(role="readonly", assigned=None)
    assert visible_stores(user, ["4092", "17967"]) == ["4092", "17967"]


def test_visible_stores_preserves_input_order() -> None:
    user = _user(role="field_manager", assigned=("17967", "4092"))
    # Input order wins: ref_stores rows are sorted by store_number on read.
    assert visible_stores(user, ["4092", "17967", "26529"]) == ["4092", "17967"]


# ---------------------------------------------------------------------------
# is_owner (Task 7.2)
# ---------------------------------------------------------------------------


def test_is_owner_true_for_owner_role() -> None:
    assert is_owner("owner") is True


def test_is_owner_false_for_other_roles() -> None:
    assert is_owner("field_manager") is False
    assert is_owner("readonly") is False
    assert is_owner(None) is False
    assert is_owner("") is False
