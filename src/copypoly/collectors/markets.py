"""Market Data Syncer — Refreshes market metadata from Gamma API.

Runs on a schedule (default: every 15 minutes).
Keeps the markets table current with prices, liquidity, volume,
and settlement status.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert

from copypoly.api.gamma import GammaAPIClient
from copypoly.db.models import Market
from copypoly.db.session import async_session_factory
from copypoly.logging import get_logger

log = get_logger(__name__)


async def sync_markets() -> dict[str, int]:
    """Fetch all active markets and upsert into the database.

    Returns:
        Dict with stats: fetched, inserted, updated.
    """
    client = GammaAPIClient()

    try:
        markets = await client.get_all_active_markets()
    except Exception as e:
        log.error("market_sync_failed", error=str(e))
        return {"fetched": 0, "inserted": 0, "updated": 0}
    finally:
        await client.close()

    if not markets:
        log.warning("no_markets_returned")
        return {"fetched": 0, "inserted": 0, "updated": 0}

    inserted = 0
    updated = 0
    now = datetime.now(timezone.utc)

    async with async_session_factory() as session:
        for market in markets:
            result = await _upsert_market(session, market, now)
            if result == "inserted":
                inserted += 1
            elif result == "updated":
                updated += 1

        await session.commit()

    stats = {"fetched": len(markets), "inserted": inserted, "updated": updated}
    log.info("market_sync_complete", **stats)
    return stats


async def _upsert_market(
    session,
    market: dict,
    now: datetime,
) -> str:
    """Insert or update a single market.

    Returns:
        "inserted" or "updated".
    """
    condition_id = market.get("conditionId", market.get("condition_id", ""))
    if not condition_id:
        return "skipped"

    # Parse tokens
    tokens = market.get("tokens", [])
    outcomes = [t.get("outcome", "") for t in tokens] if tokens else market.get("outcomes", [])
    token_ids = [t.get("token_id", "") for t in tokens] if tokens else []

    # Parse prices
    outcome_prices = market.get("outcomePrices", [])
    if isinstance(outcome_prices, str):
        import json
        try:
            outcome_prices = json.loads(outcome_prices)
        except (json.JSONDecodeError, TypeError):
            outcome_prices = []

    current_prices = {}
    for i, price in enumerate(outcome_prices):
        key = outcomes[i] if i < len(outcomes) else f"outcome_{i}"
        current_prices[key] = float(price) if price else 0.0

    stmt = pg_insert(Market).values(
        condition_id=condition_id,
        question=market.get("question", "Unknown"),
        slug=market.get("slug"),
        category=market.get("category"),
        outcomes=outcomes,
        token_ids=token_ids,
        current_prices=current_prices,
        volume=float(market.get("volume", 0) or 0),
        liquidity=float(market.get("liquidity", 0) or 0),
        active=market.get("active", True),
        settled=market.get("closed", False),
        winning_outcome=market.get("winningOutcome"),
        start_date=_parse_date(market.get("startDate")),
        end_date=_parse_date(market.get("endDate")),
        updated_at=now,
    )

    stmt = stmt.on_conflict_do_update(
        index_elements=["condition_id"],
        set_={
            "question": stmt.excluded.question,
            "slug": stmt.excluded.slug,
            "category": stmt.excluded.category,
            "outcomes": stmt.excluded.outcomes,
            "token_ids": stmt.excluded.token_ids,
            "current_prices": stmt.excluded.current_prices,
            "volume": stmt.excluded.volume,
            "liquidity": stmt.excluded.liquidity,
            "active": stmt.excluded.active,
            "settled": stmt.excluded.settled,
            "winning_outcome": stmt.excluded.winning_outcome,
            "updated_at": now,
        },
    )

    result = await session.execute(stmt)

    # Check if this was an insert or update
    return "inserted" if result.rowcount and result.rowcount > 0 else "updated"


def _parse_date(date_str: str | None) -> datetime | None:
    """Parse a date string from the API into a datetime."""
    if not date_str:
        return None

    try:
        # Try ISO format first
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        pass

    try:
        # Try Unix timestamp
        return datetime.fromtimestamp(float(date_str), tz=timezone.utc)
    except (ValueError, TypeError):
        return None
