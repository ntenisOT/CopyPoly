"""Gamma API client — Market discovery and metadata.

Base URL: https://gamma-api.polymarket.com
Auth: None required (fully public)

Used for:
- Market discovery (find markets by category, slug, etc.)
- Market metadata (question, outcomes, token IDs)
- Liquidity checks (filter markets before trading)
"""

from __future__ import annotations

from typing import Any

from copypoly.api.base import BaseAPIClient
from copypoly.logging import get_logger

log = get_logger(__name__)

GAMMA_API_BASE = "https://gamma-api.polymarket.com"


class GammaAPIClient(BaseAPIClient):
    """Client for Polymarket's Gamma API (market data)."""

    def __init__(self) -> None:
        super().__init__(base_url=GAMMA_API_BASE)

    async def get_markets(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        active: bool = True,
        closed: bool = False,
        category: str | None = None,
        order: str = "liquidityNum",
        ascending: bool = False,
    ) -> list[dict[str, Any]]:
        """Fetch markets with optional filters.

        Args:
            limit: Number of markets to return.
            offset: Pagination offset.
            active: Only active markets.
            closed: Include closed markets.
            category: Filter by category (CRYPTO, POLITICS, etc.).
            order: Sort field.
            ascending: Sort direction.

        Returns:
            List of market objects.
        """
        params: dict[str, Any] = {
            "limit": limit,
            "offset": offset,
            "active": str(active).lower(),
            "closed": str(closed).lower(),
            "order": order,
            "ascending": str(ascending).lower(),
        }
        if category:
            params["category"] = category

        return await self.get("/markets", params)

    async def get_market(self, condition_id: str) -> dict[str, Any]:
        """Fetch a single market by condition ID.

        Args:
            condition_id: The market's condition ID.

        Returns:
            Market object.
        """
        return await self.get(f"/markets/{condition_id}")

    async def get_events(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        active: bool = True,
    ) -> list[dict[str, Any]]:
        """Fetch events (each event can have multiple markets).

        Args:
            limit: Number of events to return.
            offset: Pagination offset.
            active: Only active events.

        Returns:
            List of event objects.
        """
        params: dict[str, Any] = {
            "limit": limit,
            "offset": offset,
            "active": str(active).lower(),
        }
        return await self.get("/events", params)

    async def search(self, query: str) -> list[dict[str, Any]]:
        """Search across events, markets, and profiles.

        Args:
            query: Search query string.

        Returns:
            List of search results.
        """
        return await self.get("/public-search", {"query": query})

    async def get_all_active_markets(self, max_pages: int = 50) -> list[dict[str, Any]]:
        """Fetch ALL active markets using pagination.

        Returns:
            Complete list of all active markets.
        """
        return await self.fetch_all_pages(
            "/markets",
            params={"active": "true", "closed": "false", "order": "liquidityNum"},
            page_size=100,
            max_pages=max_pages,
        )
