"""Tests for the FreshConnect HTTP client.

All HTTP traffic is intercepted by `httpx.MockTransport` — no real network
calls are issued.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import httpx
import pytest

from subway_ops.freshconnect.client import (
    AuthError,
    BadRequestError,
    ForbiddenError,
    FreshConnectClient,
    NotFoundError,
    RateLimitError,
    ServerError,
)


def _make_client(handler: Callable[[httpx.Request], httpx.Response]) -> FreshConnectClient:
    """Build a client whose HTTP calls are routed through `handler`.

    Retries are kept on but waits are zeroed so tests don't sleep.
    """
    return FreshConnectClient(
        api_client="test-client",
        api_key="test-key",
        max_retries=5,
        retry_initial_wait=0.0,
        retry_max_wait=0.0,
        transport=httpx.MockTransport(handler),
    )


# ---------------------------------------------------------------------------
# Auth header plumbing
# ---------------------------------------------------------------------------


def test_requests_carry_auth_and_accept_headers() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["req"] = request
        return httpx.Response(200, json={"ok": True})

    with _make_client(handler) as client:
        client.get("/Restaurants")

    req = captured["req"]
    assert req.headers["api-client"] == "test-client"
    assert req.headers["api-key"] == "test-key"
    assert req.headers["accept"] == "application/json"


def test_missing_credentials_raise_runtime_error() -> None:
    with pytest.raises(RuntimeError, match="FreshConnect credentials missing"):
        FreshConnectClient(api_client="", api_key="")


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_get_daily_sales_summary_happy_path() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, json={"stores": [{"storeNumber": "4092"}]})

    with _make_client(handler) as client:
        body = client.get_daily_sales_summary(
            ["4092", "17967"], date(2026, 5, 1), date(2026, 5, 7)
        )

    assert body == {"stores": [{"storeNumber": "4092"}]}
    assert "/DailySalesSummary/4092,17967/startDate/2026-05-01/endDate/2026-05-07" in captured[
        "path"
    ]


def test_list_restaurants_returns_string_list() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["4092", "17967", "26529"])

    with _make_client(handler) as client:
        result = client.list_restaurants()

    assert result == ["4092", "17967", "26529"]


def test_list_restaurants_unwraps_dict_items() -> None:
    """Live API shape (2026-05): list of {"restaurantNumber": "..."} dicts."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {"restaurantNumber": "4092"},
                {"restaurantNumber": "17967"},
            ],
        )

    with _make_client(handler) as client:
        result = client.list_restaurants()

    assert result == ["4092", "17967"]


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


def test_401_raises_auth_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    with _make_client(handler) as client, pytest.raises(AuthError):
        client.list_restaurants()


def test_403_raises_forbidden_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="nope")

    with _make_client(handler) as client, pytest.raises(ForbiddenError):
        client.list_restaurants()


def test_400_raises_bad_request_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="bad input")

    with _make_client(handler) as client, pytest.raises(BadRequestError):
        client.list_restaurants()


def test_404_raises_not_found_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="missing")

    with _make_client(handler) as client, pytest.raises(NotFoundError):
        client.list_restaurants()


def test_429_raises_rate_limit_error_without_retry() -> None:
    calls = {"n": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429, text="quota")

    with _make_client(handler) as client, pytest.raises(RateLimitError):
        client.list_restaurants()

    assert calls["n"] == 1, "429 must not be retried"


# ---------------------------------------------------------------------------
# Retry behavior on 5xx
# ---------------------------------------------------------------------------


def test_500_retries_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 5:
            return httpx.Response(500, text="boom")
        return httpx.Response(200, json=["4092", "17967"])

    with _make_client(handler) as client:
        result = client.list_restaurants()

    assert calls["n"] == 5
    assert result == ["4092", "17967"]


def test_500_exhausts_retries_then_raises_server_error() -> None:
    calls = {"n": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, text="still broken")

    with _make_client(handler) as client, pytest.raises(ServerError):
        client.list_restaurants()

    assert calls["n"] == 5  # stop_after_attempt(5)


def test_connect_error_is_retried() -> None:
    calls = {"n": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.ConnectError("temporary")
        return httpx.Response(200, json=["4092"])

    with _make_client(handler) as client:
        result = client.list_restaurants()

    assert calls["n"] == 3
    assert result == ["4092"]


# ---------------------------------------------------------------------------
# Pre-call limit validation
# ---------------------------------------------------------------------------


def test_transaction_details_rejects_multi_store_before_http() -> None:
    """ValueError must be raised pre-flight; the handler never gets called."""

    def handler(_: httpx.Request) -> httpx.Response:
        raise AssertionError("HTTP must not be hit when limits are exceeded")

    with _make_client(handler) as client, pytest.raises(ValueError, match="exactly one store"):
        client.get_transaction_details(
            "4092,17967", date(2026, 5, 1), date(2026, 5, 7)
        )


def test_transaction_details_rejects_window_over_14_days() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise AssertionError("HTTP must not be hit when limits are exceeded")

    with _make_client(handler) as client, pytest.raises(ValueError, match="exceeds"):
        client.get_transaction_details(
            "4092", date(2026, 5, 1), date(2026, 5, 20)
        )


def test_daily_sales_rejects_too_many_stores() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise AssertionError("HTTP must not be hit when limits are exceeded")

    with _make_client(handler) as client, pytest.raises(ValueError, match="exceeds"):
        client.get_daily_sales_summary(
            [str(i) for i in range(21)], date(2026, 5, 1), date(2026, 5, 7)
        )


def test_daily_sales_rejects_window_over_50_days() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise AssertionError("HTTP must not be hit when limits are exceeded")

    with _make_client(handler) as client, pytest.raises(ValueError, match="exceeds"):
        client.get_daily_sales_summary(
            ["4092"], date(2026, 1, 1), date(2026, 5, 1)
        )


def test_end_before_start_raises_value_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise AssertionError("HTTP must not be hit when range is invalid")

    with _make_client(handler) as client, pytest.raises(ValueError, match="precedes"):
        client.get_daily_sales_summary(
            ["4092"], date(2026, 5, 10), date(2026, 5, 1)
        )


def test_control_sheet_rejects_too_many_stores() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise AssertionError("HTTP must not be hit when limits are exceeded")

    with _make_client(handler) as client, pytest.raises(ValueError, match="exceeds"):
        client.get_control_sheet([str(i) for i in range(41)], date(2026, 5, 5))


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


def test_client_is_usable_as_context_manager() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    with _make_client(handler) as client:
        assert client.list_restaurants() == []
    # No explicit assertion on close — relying on httpx's own tests; this just
    # exercises __enter__/__exit__ to keep them covered.
