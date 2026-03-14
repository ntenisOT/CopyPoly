"""Position Monitor — Tracks watched traders' positions for signal detection.

Runs on a schedule (default: every 30 seconds).
Detects new positions, size changes, and closed positions
by comparing current API data against stored positions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from copypoly.api.data import DataAPIClient
from copypoly.db.models import PositionSnapshot, Trader, TraderPosition
from copypoly.db.session import async_session_factory
from copypoly.logging import get_logger

log = get_logger(__name__)


async def collect_positions() -> dict[str, int]:
    """Fetch positions for all watched traders and detect changes.

    Returns:
        Dict with stats: traders_checked, new_positions, updated, closed.
    """
    stats = {
        "traders_checked": 0,
        "new_positions": 0,
        "updated_positions": 0,
        "closed_positions": 0,
    }

    # Get all watched traders
    async with async_session_factory() as session:
        result = await session.execute(
            select(Trader.wallet).where(Trader.is_watched == True)  # noqa: E712
        )
        watched_wallets = [row[0] for row in result.fetchall()]

    if not watched_wallets:
        log.debug("no_watched_traders")
        return stats

    client = DataAPIClient()

    try:
        for wallet in watched_wallets:
            trader_stats = await _collect_trader_positions(client, wallet)
            stats["traders_checked"] += 1
            stats["new_positions"] += trader_stats["new"]
            stats["updated_positions"] += trader_stats["updated"]
            stats["closed_positions"] += trader_stats["closed"]
    finally:
        await client.close()

    log.info("position_collection_complete", **stats)
    return stats


async def _collect_trader_positions(
    client: DataAPIClient,
    wallet: str,
) -> dict[str, int]:
    """Fetch and reconcile positions for a single trader.

    Compares API positions against stored positions to detect:
    - New positions (not in our DB)
    - Size changes (position exists but size differs)
    - Closed positions (in our DB but not in API response)

    Returns:
        Dict with counts: new, updated, closed.
    """
    stats = {"new": 0, "updated": 0, "closed": 0}

    try:
        api_positions = await client.get_all_positions(wallet)
    except Exception as e:
        log.error("position_fetch_failed", wallet=wallet[:10], error=str(e))
        return stats

    now = datetime.now(timezone.utc)

    async with async_session_factory() as session:
        # Get current stored open positions for this trader
        result = await session.execute(
            select(TraderPosition).where(
                TraderPosition.trader_wallet == wallet,
                TraderPosition.status == "OPEN",
            )
        )
        stored_positions = {
            pos.token_id: pos for pos in result.scalars().all()
        }

        # Track which positions we've seen in the API response
        seen_token_ids: set[str] = set()

        for api_pos in api_positions:
            token_id = api_pos.get("asset", "")
            if not token_id:
                continue

            seen_token_ids.add(token_id)
            size = float(api_pos.get("size", 0))

            if size <= 0:
                continue

            if token_id in stored_positions:
                # Position exists — check for size change
                stored = stored_positions[token_id]
                stored_size = float(stored.size) if stored.size else 0

                if abs(size - stored_size) > 0.001:
                    # Size changed — update and record snapshot
                    await session.execute(
                        update(TraderPosition)
                        .where(TraderPosition.id == stored.id)
                        .values(
                            size=size,
                            current_value=float(api_pos.get("currentValue", 0)),
                            last_updated_at=now,
                        )
                    )
                    await _insert_snapshot(session, stored.id, wallet, token_id, size, api_pos)
                    stats["updated"] += 1

                    log.info(
                        "position_changed",
                        wallet=wallet[:10],
                        token_id=token_id[:16],
                        old_size=stored_size,
                        new_size=size,
                    )
            else:
                # New position — insert it
                condition_id = api_pos.get("conditionId", api_pos.get("market", ""))
                outcome = api_pos.get("outcome", "")

                new_pos = TraderPosition(
                    trader_wallet=wallet,
                    condition_id=condition_id,
                    token_id=token_id,
                    outcome=outcome,
                    size=size,
                    avg_entry_price=float(api_pos.get("avgPrice", 0)) or None,
                    current_value=float(api_pos.get("currentValue", 0)) or None,
                    status="OPEN",
                    first_detected_at=now,
                    last_updated_at=now,
                )
                session.add(new_pos)
                await session.flush()  # Get the ID

                await _insert_snapshot(
                    session, new_pos.id, wallet, token_id, size, api_pos
                )
                stats["new"] += 1

                log.info(
                    "new_position_detected",
                    wallet=wallet[:10],
                    token_id=token_id[:16],
                    outcome=outcome,
                    size=size,
                )

        # Detect closed positions (in DB but not in API)
        for token_id, stored in stored_positions.items():
            if token_id not in seen_token_ids:
                await session.execute(
                    update(TraderPosition)
                    .where(TraderPosition.id == stored.id)
                    .values(
                        status="CLOSED",
                        closed_at=now,
                        last_updated_at=now,
                    )
                )
                stats["closed"] += 1

                log.info(
                    "position_closed",
                    wallet=wallet[:10],
                    token_id=token_id[:16],
                )

        await session.commit()

    return stats


async def _insert_snapshot(
    session: AsyncSession,
    position_id: int,
    wallet: str,
    token_id: str,
    size: float,
    api_pos: dict,
) -> None:
    """Insert a position snapshot for historical tracking."""
    snapshot = PositionSnapshot(
        position_id=position_id,
        trader_wallet=wallet,
        token_id=token_id,
        size=size,
        current_price=float(api_pos.get("curPrice", 0)) or None,
        current_value=float(api_pos.get("currentValue", 0)) or None,
    )
    session.add(snapshot)
