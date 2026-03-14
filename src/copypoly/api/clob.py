"""CLOB API client — Order book reading and trade execution.

Base URL: https://clob.polymarket.com
Auth: Required for trading; read-only endpoints are public.

Wraps the official `py-clob-client` SDK for authenticated operations,
and provides direct HTTP access for read-only endpoints.
"""

from __future__ import annotations

from typing import Any

from copypoly.api.base import BaseAPIClient
from copypoly.config import settings
from copypoly.logging import get_logger

log = get_logger(__name__)

CLOB_API_BASE = "https://clob.polymarket.com"


class ClobAPIClient(BaseAPIClient):
    """Client for Polymarket's CLOB API.

    Read-only operations (midpoint, price, order book) don't require auth.
    Trading operations require a wallet private key and use the SDK.
    """

    def __init__(self) -> None:
        super().__init__(base_url=CLOB_API_BASE)
        self._sdk_client: Any | None = None

    # ----------------------------------------------------------------
    # Read-Only Endpoints (No Auth)
    # ----------------------------------------------------------------

    async def get_midpoint(self, token_id: str) -> float:
        """Get the midpoint price for a token.

        Args:
            token_id: The token ID to query.

        Returns:
            Current midpoint price as a float.
        """
        result = await self.get("/midpoint", params={"token_id": token_id})
        return float(result.get("mid", 0))

    async def get_price(
        self, token_id: str, *, side: str = "BUY"
    ) -> float:
        """Get the current price for a token (buy or sell side).

        Args:
            token_id: The token ID to query.
            side: BUY or SELL.

        Returns:
            Current price as a float.
        """
        result = await self.get(
            "/price", params={"token_id": token_id, "side": side}
        )
        return float(result.get("price", 0))

    async def get_order_book(self, token_id: str) -> dict[str, Any]:
        """Get the full order book for a token.

        Args:
            token_id: The token ID to query.

        Returns:
            Order book with bids, asks, best_bid, best_ask.
        """
        return await self.get("/order-book", params={"token_id": token_id})

    async def get_order_books_batch(
        self, token_ids: list[str]
    ) -> list[dict[str, Any]]:
        """Get order books for multiple tokens in one request.

        Args:
            token_ids: List of token IDs.

        Returns:
            List of order book objects.
        """
        return await self.get(
            "/order-books",
            params={"token_ids": ",".join(token_ids)},
        )

    async def get_spread(self, token_id: str) -> dict[str, float]:
        """Get the bid-ask spread for a token.

        Args:
            token_id: The token ID to query.

        Returns:
            Dict with best_bid, best_ask, spread, midpoint.
        """
        book = await self.get_order_book(token_id)

        bids = book.get("bids", [])
        asks = book.get("asks", [])

        best_bid = float(bids[0]["price"]) if bids else 0.0
        best_ask = float(asks[0]["price"]) if asks else 1.0
        spread = best_ask - best_bid
        midpoint = (best_bid + best_ask) / 2 if (best_bid and best_ask) else 0.0

        return {
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread": spread,
            "midpoint": midpoint,
        }

    # ----------------------------------------------------------------
    # SDK-based Trading (Auth Required)
    # ----------------------------------------------------------------

    def _get_sdk_client(self) -> Any:
        """Initialize the py-clob-client SDK (lazy, synchronous).

        The SDK handles wallet signing and order building.
        Only initialized when trading is actually needed.
        """
        if self._sdk_client is not None:
            return self._sdk_client

        private_key = settings.polymarket_private_key.get_secret_value()
        if not private_key:
            raise RuntimeError(
                "POLYMARKET_PRIVATE_KEY not set — cannot initialize trading client. "
                "Set it in .env or environment variables."
            )

        from py_clob_client.client import ClobClient

        self._sdk_client = ClobClient(
            CLOB_API_BASE,
            key=private_key,
            chain_id=settings.polymarket_chain_id,
            signature_type=settings.polymarket_signature_type,
            funder=settings.polymarket_funder_address or None,
        )
        self._sdk_client.set_api_creds(
            self._sdk_client.create_or_derive_api_creds()
        )

        log.info("clob_sdk_initialized", chain_id=settings.polymarket_chain_id)
        return self._sdk_client

    def create_market_order(
        self,
        token_id: str,
        amount: float,
        side: str = "BUY",
    ) -> dict[str, Any]:
        """Create a signed market order using the SDK.

        Args:
            token_id: Token to trade.
            amount: USDC amount.
            side: BUY or SELL.

        Returns:
            Signed order ready for submission.
        """
        from py_clob_client.clob_types import MarketOrderArgs, OrderType

        sdk = self._get_sdk_client()

        order_args = MarketOrderArgs(
            token_id=token_id,
            amount=amount,
        )

        signed_order = sdk.create_market_order(order_args)

        log.info(
            "market_order_created",
            token_id=token_id[:16] + "...",
            amount=amount,
            side=side,
        )

        return signed_order

    def submit_order(self, signed_order: Any) -> dict[str, Any]:
        """Submit a signed order to Polymarket.

        Args:
            signed_order: The signed order from create_market_order().

        Returns:
            Order submission response with order ID and status.
        """
        from py_clob_client.clob_types import OrderType

        sdk = self._get_sdk_client()
        result = sdk.post_order(signed_order, OrderType.FOK)

        log.info("order_submitted", result=str(result)[:200])
        return result

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        """Cancel an open order.

        Args:
            order_id: The order ID to cancel.

        Returns:
            Cancellation response.
        """
        sdk = self._get_sdk_client()
        result = sdk.cancel(order_id)

        log.info("order_cancelled", order_id=order_id)
        return result

    def cancel_all_orders(self) -> dict[str, Any]:
        """Cancel all open orders.

        Returns:
            Cancellation response.
        """
        sdk = self._get_sdk_client()
        result = sdk.cancel_all()

        log.warning("all_orders_cancelled")
        return result
