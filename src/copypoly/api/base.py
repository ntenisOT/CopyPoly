"""Base HTTP client with retry logic, rate limiting, and structured logging.

All Polymarket API clients inherit from this base.
"""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from copypoly.logging import get_logger

log = get_logger(__name__)

# Default timeout (seconds)
DEFAULT_TIMEOUT = 30.0

# Retry on these HTTP status codes
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class APIError(Exception):
    """Raised when an API request fails after retries."""

    def __init__(self, status_code: int, message: str, url: str) -> None:
        self.status_code = status_code
        self.url = url
        super().__init__(f"API error {status_code} from {url}: {message}")


class RetryableAPIError(APIError):
    """API error that can be retried (429, 5xx)."""

    pass


class BaseAPIClient:
    """Async HTTP client with built-in retry, timeout, and logging.

    Features:
        - Automatic retries with exponential backoff for 429/5xx errors
        - Structured request/response logging
        - Configurable timeout
        - Pagination support via `fetch_all_pages()`
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = DEFAULT_TIMEOUT,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout),
            headers=headers or {},
            follow_redirects=True,
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    @retry(
        retry=retry_if_exception_type(RetryableAPIError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        """Execute an HTTP request with retry logic.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API path (appended to base_url)
            params: Query parameters
            json_body: JSON request body

        Returns:
            Parsed JSON response.

        Raises:
            RetryableAPIError: For 429/5xx errors (will be retried).
            APIError: For other HTTP errors (will not be retried).
        """
        url = f"{self.base_url}{path}"

        log.debug(
            "api_request",
            method=method,
            url=url,
            params=params,
        )

        try:
            response = await self._client.request(
                method=method,
                url=path,
                params=params,
                json=json_body,
            )
        except httpx.TimeoutException as e:
            log.warning("api_timeout", url=url, error=str(e))
            raise RetryableAPIError(
                status_code=0, message=f"Timeout: {e}", url=url
            ) from e
        except httpx.ConnectError as e:
            log.warning("api_connection_error", url=url, error=str(e))
            raise RetryableAPIError(
                status_code=0, message=f"Connection error: {e}", url=url
            ) from e

        if response.status_code in RETRYABLE_STATUS_CODES:
            log.warning(
                "api_retryable_error",
                url=url,
                status_code=response.status_code,
                body=response.text[:200],
            )
            raise RetryableAPIError(
                status_code=response.status_code,
                message=response.text[:200],
                url=url,
            )

        if response.status_code >= 400:
            log.error(
                "api_error",
                url=url,
                status_code=response.status_code,
                body=response.text[:500],
            )
            raise APIError(
                status_code=response.status_code,
                message=response.text[:500],
                url=url,
            )

        return response.json()

    async def get(
        self, path: str, params: dict[str, Any] | None = None
    ) -> Any:
        """Execute a GET request."""
        return await self._request("GET", path, params=params)

    async def post(
        self,
        path: str,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Execute a POST request."""
        return await self._request("POST", path, params=params, json_body=json_body)

    async def fetch_all_pages(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        page_size: int = 100,
        max_pages: int = 50,
    ) -> list[Any]:
        """Fetch all pages from a paginated endpoint.

        Args:
            path: API path
            params: Base query parameters
            page_size: Number of results per page
            max_pages: Safety limit to prevent infinite pagination

        Returns:
            All items across all pages.
        """
        all_items: list[Any] = []
        params = dict(params or {})
        params["limit"] = page_size
        offset = 0

        for page in range(max_pages):
            params["offset"] = offset
            data = await self.get(path, params)

            # Handle both list responses and dict responses with data key
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = data.get("data", data.get("results", []))
            else:
                break

            if not items:
                break

            all_items.extend(items)
            offset += len(items)

            log.debug(
                "pagination",
                path=path,
                page=page + 1,
                items_this_page=len(items),
                total_items=len(all_items),
            )

            # Got fewer items than page size — this is the last page
            if len(items) < page_size:
                break

        return all_items
