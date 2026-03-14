"""Data API client — Leaderboard, positions, and trader data.

Base URL: https://data-api.polymarket.com
Auth: Mixed (leaderboard is public, some endpoints may need auth)

THIS IS THE MOST CRITICAL API for CopyPoly:
- Leaderboard scraping → identify top traders
- Position tracking → monitor what top traders currently hold
- Trade history → analyze patterns, win rate, consistency
"""

from __future__ import annotations

from typing import Any

from copypoly.api.base import BaseAPIClient
from copypoly.logging import get_logger

log = get_logger(__name__)

DATA_API_BASE = "https://data-api.polymarket.com"


class DataAPIClient(BaseAPIClient):
    """Client for Polymarket's Data API (leaderboard, positions, trades)."""

    def __init__(self) -> None:
        super().__init__(base_url=DATA_API_BASE)

    # ----------------------------------------------------------------
    # Leaderboard
    # ----------------------------------------------------------------

    # API param value mapping — the API uses lowercase timePeriod values
    _PERIOD_MAP = {
        "ALL": "all",
        "MONTH": "month",
        "WEEK": "week",
        "DAY": "day",
        # Also accept lowercase directly
        "all": "all",
        "month": "month",
        "week": "week",
        "day": "day",
    }

    async def get_leaderboard(
        self,
        *,
        period: str = "all",
        category: str = "overall",
        order_by: str = "PNL",
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Fetch leaderboard rankings.

        Args:
            period: day, week, month, all (case-insensitive)
            category: overall, politics, sports, crypto, etc.
            order_by: PNL or VOL
            limit: Number of results
            offset: Pagination offset

        Returns:
            List of leaderboard entries with rank, wallet, pnl, volume.
        """
        api_period = self._PERIOD_MAP.get(period, period.lower())

        params: dict[str, Any] = {
            "timePeriod": api_period,
            "orderBy": order_by,
            "limit": limit,
            "offset": offset,
        }

        log.info(
            "fetching_leaderboard",
            period=api_period,
            order_by=order_by,
            limit=limit,
        )

        return await self.get("/v1/leaderboard", params)

    async def get_full_leaderboard(
        self,
        *,
        period: str = "all",
        order_by: str = "PNL",
        max_traders: int = 500,
    ) -> list[dict[str, Any]]:
        """Fetch all available leaderboard entries using pagination.

        Args:
            period: day, week, month, all
            order_by: PNL or VOL
            max_traders: Maximum traders to fetch.

        Returns:
            Complete leaderboard (up to max_traders).
        """
        api_period = self._PERIOD_MAP.get(period, period.lower())

        return await self.fetch_all_pages(
            "/v1/leaderboard",
            params={
                "timePeriod": api_period,
                "orderBy": order_by,
            },
            page_size=50,  # API caps at 50 per page regardless of limit
            max_pages=(max_traders // 50) + 1,
        )

    async def get_leaderboard_for_all_periods(
        self,
        *,
        limit: int = 100,
    ) -> dict[str, list[dict[str, Any]]]:
        """Fetch leaderboard for all time periods.

        Returns:
            Dict mapping period → leaderboard entries.
            {"all": [...], "month": [...], "week": [...], "day": [...]}
        """
        periods = ["all", "month", "week", "day"]
        result: dict[str, list[dict[str, Any]]] = {}

        for period in periods:
            result[period] = await self.get_leaderboard(
                period=period,
                limit=limit,
            )
            log.info(
                "leaderboard_period_fetched",
                period=period,
                count=len(result[period]),
            )

        return result

    # ----------------------------------------------------------------
    # Positions & Holdings
    # ----------------------------------------------------------------

    async def get_positions(
        self,
        wallet: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Get current open positions for a wallet.

        Args:
            wallet: Trader's wallet address.
            limit: Number of results.
            offset: Pagination offset.

        Returns:
            List of position objects.
        """
        params: dict[str, Any] = {
            "user": wallet,
            "limit": limit,
            "offset": offset,
        }
        return await self.get("/positions", params)

    async def get_all_positions(self, wallet: str) -> list[dict[str, Any]]:
        """Fetch ALL positions for a wallet using pagination.

        Args:
            wallet: Trader's wallet address.

        Returns:
            Complete list of all positions.
        """
        return await self.fetch_all_pages(
            "/positions",
            params={"user": wallet},
            page_size=100,
        )

    # ----------------------------------------------------------------
    # Trades & Activity
    # ----------------------------------------------------------------

    async def get_trades(
        self,
        wallet: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Get trade history for a wallet.

        Args:
            wallet: Trader's wallet address.
            limit: Number of results.
            offset: Pagination offset.

        Returns:
            List of trade objects.
        """
        return await self.get(
            "/trades",
            params={"user": wallet, "limit": limit, "offset": offset},
        )

    async def get_activity(
        self,
        wallet: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Get on-chain activity for a wallet.

        Args:
            wallet: Trader's wallet address.
            limit: Number of results.
            offset: Pagination offset.

        Returns:
            List of activity objects (liquidity, redemptions, etc.)
        """
        return await self.get(
            "/activity",
            params={"user": wallet, "limit": limit, "offset": offset},
        )

    async def get_closed_positions(
        self,
        wallet: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Get closed/resolved positions for a wallet.

        Args:
            wallet: Trader's wallet address.

        Returns:
            List of closed position objects (with PnL outcome).
        """
        return await self.get(
            "/closed-positions",
            params={"user": wallet, "limit": limit, "offset": offset},
        )

    # ----------------------------------------------------------------
    # Profile
    # ----------------------------------------------------------------

    async def get_profile(self, wallet: str) -> dict[str, Any]:
        """Get a trader's public profile.

        Args:
            wallet: Trader's wallet address.

        Returns:
            Profile object with username, image, stats.
        """
        result = await self.get("/v1/leaderboard", params={"user": wallet})

        # API returns a list; get the first match
        if isinstance(result, list) and result:
            return result[0]

        return {}
