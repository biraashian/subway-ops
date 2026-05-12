"""HTTP client for the FreshConnect (LiveIQ) franchise reporting API.

Every endpoint goes through `FreshConnectClient`. The client owns:

- Auth headers (`api-client`, `api-key`, `Accept: application/json`).
- Exponential-backoff retry on transient failures (5xx, connect errors,
  read timeouts) via tenacity. 429 is treated as a hard daily-quota stop
  and is NOT retried in-process.
- Documented per-endpoint pre-call limit validation — the most common cause
  of an opaque 400 from this API is exceeding the store-count or date-span
  ceiling, so we catch it locally with a `ValueError` before hitting the
  wire.
- Structured request logging (method, URL, status, duration_ms).

The exact REST paths used here follow the FreshConnect API documentation
(`docs/freshconnect/APIDocumentation.pdf` in the operator's local copy).
Task 1.3 (the discovery script) will hit each endpoint with real credentials
and reconcile any drift.
"""

from __future__ import annotations

import time
from datetime import date
from types import TracebackType
from typing import Any

import httpx
import structlog
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from subway_ops.config import settings

DEFAULT_BASE_URL = "https://liveiqfranchiseeapi.subway.com/api"
DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class FreshConnectError(Exception):
    """Base for every FreshConnect-specific failure."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class AuthError(FreshConnectError):
    """401 — credentials missing, invalid, or expired."""


class ForbiddenError(FreshConnectError):
    """403 — credentials valid but not authorized for this resource."""


class BadRequestError(FreshConnectError):
    """400 — malformed request (often: limits exceeded server-side)."""


class NotFoundError(FreshConnectError):
    """404 — endpoint or resource not found."""


class RateLimitError(FreshConnectError):
    """429 — daily call quota exhausted.

    FreshConnect's quota resets at midnight UTC. We do NOT retry within the
    same job run; the caller (the orchestrator) decides whether to surface
    the failure or reschedule for tomorrow.
    """


class ServerError(FreshConnectError):
    """5xx after all retries are exhausted."""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class FreshConnectClient:
    """Thin, typed wrapper around the FreshConnect REST API."""

    def __init__(
        self,
        *,
        api_client: str | None = None,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
        max_retries: int = 5,
        retry_initial_wait: float = 2.0,
        retry_max_wait: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_client = (
            api_client if api_client is not None else settings.freshconnect_api_client
        )
        self._api_key = api_key if api_key is not None else settings.freshconnect_api_key

        if not self._api_client or not self._api_key:
            raise RuntimeError(
                "FreshConnect credentials missing: set FRESHCONNECT_API_CLIENT "
                "and FRESHCONNECT_API_KEY in .env."
            )

        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self.retry_initial_wait = retry_initial_wait
        self.retry_max_wait = retry_max_wait

        self._http = httpx.Client(
            timeout=timeout,
            headers={
                "api-client": self._api_client,
                "api-key": self._api_key,
                "Accept": "application/json",
            },
            transport=transport,
        )

    # -- lifecycle ----------------------------------------------------------

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> FreshConnectClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # -- low-level request --------------------------------------------------

    def _retry_policy(self) -> Retrying:
        return Retrying(
            retry=retry_if_exception_type(
                (ServerError, httpx.ConnectError, httpx.ReadTimeout)
            ),
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential_jitter(
                initial=self.retry_initial_wait, max=self.retry_max_wait
            ),
            reraise=True,
        )

    def _do_request(
        self, method: str, url: str, params: dict[str, Any] | None
    ) -> dict[str, Any] | list[Any]:
        t0 = time.monotonic()
        resp = self._http.request(method, url, params=params)
        duration_ms = int((time.monotonic() - t0) * 1000)
        log.info(
            "freshconnect_request",
            method=method,
            url=url,
            status=resp.status_code,
            duration_ms=duration_ms,
        )
        self._raise_for_status(resp)
        return resp.json()  # type: ignore[no-any-return]

    @staticmethod
    def _raise_for_status(resp: httpx.Response) -> None:
        if resp.status_code < 400:
            return
        if resp.status_code == 400:
            raise BadRequestError(
                f"FreshConnect 400 Bad Request: {resp.text[:500]}", status_code=400
            )
        if resp.status_code == 401:
            raise AuthError("FreshConnect 401 Unauthorized", status_code=401)
        if resp.status_code == 403:
            raise ForbiddenError("FreshConnect 403 Forbidden", status_code=403)
        if resp.status_code == 404:
            raise NotFoundError(
                f"FreshConnect 404 Not Found: {resp.url}", status_code=404
            )
        if resp.status_code == 429:
            raise RateLimitError(
                "FreshConnect 429 — daily call quota exhausted. "
                "Quota resets at midnight UTC; do not retry in-process.",
                status_code=429,
            )
        if resp.status_code >= 500:
            raise ServerError(
                f"FreshConnect {resp.status_code}: {resp.text[:500]}",
                status_code=resp.status_code,
            )
        raise FreshConnectError(
            f"Unexpected FreshConnect status {resp.status_code}: {resp.text[:500]}",
            status_code=resp.status_code,
        )

    def _request(
        self, method: str, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | list[Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        return self._retry_policy()(self._do_request, method, url, params)

    # -- public: raw -------------------------------------------------------

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        """Raw GET. Used by endpoint-specific methods and by discovery scripts."""
        return self._request("GET", path, params)

    # -- public: endpoints -------------------------------------------------

    def list_restaurants(self) -> list[str]:
        """GET /Restaurants → list of restaurant_number strings.

        Observed live shape (2026-05): a list of ``{"restaurantNumber": "..."}``
        dicts. We accept that shape, a bare list of strings, and a wrapper dict
        with a ``restaurants`` key — whichever the API ends up settling on.
        """
        result = self._request("GET", "/Restaurants")
        if isinstance(result, dict) and "restaurants" in result:
            result = result["restaurants"]

        if not isinstance(result, list):
            raise FreshConnectError(
                f"Unexpected /Restaurants payload shape: {type(result).__name__}"
            )

        out: list[str] = []
        for item in result:
            if isinstance(item, dict):
                num = item.get("restaurantNumber") or item.get("storeNumber")
                if num is None:
                    raise FreshConnectError(
                        f"/Restaurants item missing restaurantNumber: {item!r}"
                    )
                out.append(str(num))
            else:
                out.append(str(item))
        return out

    def get_daily_sales_summary(
        self, store_numbers: list[str], start: date, end: date
    ) -> Any:
        """GET /DailySalesSummary. Max 20 stores, max 50 days (inclusive)."""
        _validate_limits("DailySalesSummary", store_numbers, start, end, 20, 50)
        stores = _join(store_numbers)
        path = (
            f"/DailySalesSummary/{stores}"
            f"/startDate/{_fmt(start)}/endDate/{_fmt(end)}"
        )
        return self._request("GET", path)

    def get_control_sheet(self, store_numbers: list[str], week_end: date) -> Any:
        """GET /controlsheet/{stores}/{weekEndDate}. Max 40 stores; weekly."""
        _validate_stores("ControlSheet", store_numbers, 40)
        stores = _join(store_numbers)
        path = f"/controlsheet/{stores}/{_fmt(week_end)}"
        return self._request("GET", path)

    def get_paidouts_and_no_sales(
        self, store_numbers: list[str], start: date, end: date
    ) -> Any:
        """GET /PaidOutsAndNoSales. Max 20 stores, max 31 days."""
        _validate_limits("PaidOutsAndNoSales", store_numbers, start, end, 20, 31)
        stores = _join(store_numbers)
        path = (
            f"/PaidOutsAndNoSales/{stores}"
            f"/startDate/{_fmt(start)}/endDate/{_fmt(end)}"
        )
        return self._request("GET", path)

    def get_inventory_movement(
        self, store_numbers: list[str], start: date, end: date
    ) -> Any:
        """GET /InventoryMovement. Max 20 stores, max 50 days."""
        _validate_limits("InventoryMovement", store_numbers, start, end, 20, 50)
        stores = _join(store_numbers)
        path = (
            f"/InventoryMovement/{stores}"
            f"/startDate/{_fmt(start)}/endDate/{_fmt(end)}"
        )
        return self._request("GET", path)

    def get_wisr(self, store_numbers: list[str], week_end: date) -> Any:
        """GET /Wisr/{stores}/{weekEndDate}. Max 25 stores; weekly."""
        _validate_stores("Wisr", store_numbers, 25)
        stores = _join(store_numbers)
        path = f"/Wisr/{stores}/{_fmt(week_end)}"
        return self._request("GET", path)

    def get_daily_timeclock(
        self, store_numbers: list[str], start: date, end: date
    ) -> Any:
        """GET /DailyTimeclock. Max 10 stores, max 30 days."""
        _validate_limits("DailyTimeclock", store_numbers, start, end, 10, 30)
        stores = _join(store_numbers)
        path = (
            f"/DailyTimeclock/{stores}"
            f"/startDate/{_fmt(start)}/endDate/{_fmt(end)}"
        )
        return self._request("GET", path)

    def get_third_party_daily(
        self, store_numbers: list[str], start: date, end: date
    ) -> Any:
        """GET /ThirdPartyDailySalesSummary. Max 20 stores, max 30 days."""
        _validate_limits(
            "ThirdPartyDailySalesSummary", store_numbers, start, end, 20, 30
        )
        stores = _join(store_numbers)
        path = (
            f"/ThirdPartyDailySalesSummary/{stores}"
            f"/startDate/{_fmt(start)}/endDate/{_fmt(end)}"
        )
        return self._request("GET", path)

    def get_transaction_details(
        self, store_number: str, start: date, end: date
    ) -> Any:
        """GET /TransactionDetails. Single store, max 14 days. Heaviest endpoint."""
        _validate_single_store("TransactionDetails", store_number)
        _validate_limits(
            "TransactionDetails", [store_number], start, end, 1, 14
        )
        path = (
            f"/TransactionDetails/{store_number}"
            f"/startDate/{_fmt(start)}/endDate/{_fmt(end)}"
        )
        return self._request("GET", path)

    def get_tips_details(
        self, store_number: str, start: date, end: date
    ) -> Any:
        """GET /TipsDetails. Single store, max 14 days."""
        _validate_single_store("TipsDetails", store_number)
        _validate_limits("TipsDetails", [store_number], start, end, 1, 14)
        path = (
            f"/TipsDetails/{store_number}"
            f"/startDate/{_fmt(start)}/endDate/{_fmt(end)}"
        )
        return self._request("GET", path)

    def get_waste_bread_credits(
        self, store_numbers: list[str], start: date, end: date
    ) -> Any:
        """GET /WasteBreadCredits. Max 10 stores, max 20 days."""
        _validate_limits("WasteBreadCredits", store_numbers, start, end, 10, 20)
        stores = _join(store_numbers)
        path = (
            f"/WasteBreadCredits/{stores}"
            f"/startDate/{_fmt(start)}/endDate/{_fmt(end)}"
        )
        return self._request("GET", path)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fmt(d: date) -> str:
    return d.isoformat()


def _join(store_numbers: list[str]) -> str:
    return ",".join(str(s) for s in store_numbers)


def _validate_single_store(endpoint: str, store_number: str) -> None:
    if not store_number or "," in store_number:
        raise ValueError(
            f"{endpoint}: requires exactly one store_number, got {store_number!r}. "
            "This endpoint exceeds the per-store cap when given a comma-joined value."
        )


def _validate_stores(endpoint: str, store_numbers: list[str], max_stores: int) -> None:
    if not store_numbers:
        raise ValueError(f"{endpoint}: store_numbers must be non-empty.")
    if len(store_numbers) > max_stores:
        raise ValueError(
            f"{endpoint}: {len(store_numbers)} stores exceeds documented limit "
            f"of {max_stores}. Split into smaller batches."
        )


def _validate_limits(
    endpoint: str,
    store_numbers: list[str],
    start: date,
    end: date,
    max_stores: int,
    max_days: int,
) -> None:
    _validate_stores(endpoint, store_numbers, max_stores)
    if end < start:
        raise ValueError(f"{endpoint}: end date {end} precedes start date {start}.")
    span = (end - start).days + 1
    if span > max_days:
        raise ValueError(
            f"{endpoint}: requested span of {span} days "
            f"({start}..{end}) exceeds documented limit of {max_days}. "
            "Split into smaller windows."
        )
