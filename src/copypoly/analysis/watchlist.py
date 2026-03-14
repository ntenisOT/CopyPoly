"""Watchlist Manager — Promotes top-scoring traders to the watchlist.

After scoring, this module selects the top N traders (configurable)
and marks them as `is_watched=True` in the database. The position
monitor then tracks their positions.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update

from copypoly.analysis.scorer import TraderScore, score_all_traders
from copypoly.db.models import AppConfig, Trader
from copypoly.db.session import async_session_factory
from copypoly.logging import get_logger

log = get_logger(__name__)

DEFAULT_WATCHLIST_SIZE = 20


async def update_watchlist(
    max_traders: int | None = None,
    min_score: float = 0.0,
) -> dict[str, int]:
    """Re-score all traders and update the watchlist.

    Steps:
        1. Score all traders
        2. Select top N eligible traders (by composite score)
        3. Mark selected traders as is_watched=True
        4. Unwatch any traders that fell off the list

    Args:
        max_traders: Maximum traders to watch. If None, reads from app_config.
        min_score: Minimum composite score to be watchlisted.

    Returns:
        Dict with stats: scored, eligible, watched, unwatched.
    """
    # Load watchlist size from config if not provided
    if max_traders is None:
        max_traders = await _load_watchlist_size()

    # Step 1: Score everyone
    all_scores = await score_all_traders()

    eligible = [s for s in all_scores if s.eligible and s.composite_score >= min_score]
    top_traders = eligible[:max_traders]
    top_wallets = {s.wallet for s in top_traders}

    # Step 2: Update database
    now = datetime.now(timezone.utc)
    watched = 0
    unwatched = 0

    async with async_session_factory() as session:
        # Get currently watched wallets
        result = await session.execute(
            select(Trader.wallet).where(Trader.is_watched == True)  # noqa: E712
        )
        currently_watched = {row[0] for row in result.fetchall()}

        # Watch new traders
        to_watch = top_wallets - currently_watched
        if to_watch:
            await session.execute(
                update(Trader)
                .where(Trader.wallet.in_(to_watch))
                .values(
                    is_watched=True,
                    watch_started_at=now,
                    updated_at=now,
                )
            )
            watched = len(to_watch)

        # Unwatch traders that fell off
        to_unwatch = currently_watched - top_wallets
        if to_unwatch:
            await session.execute(
                update(Trader)
                .where(Trader.wallet.in_(to_unwatch))
                .values(
                    is_watched=False,
                    watch_started_at=None,
                    updated_at=now,
                )
            )
            unwatched = len(to_unwatch)

        await session.commit()

    stats = {
        "scored": len(all_scores),
        "eligible": len(eligible),
        "watched": watched,
        "unwatched": unwatched,
        "total_watched": len(top_wallets),
    }

    log.info("watchlist_updated", **stats)

    # Log top 5
    for i, s in enumerate(top_traders[:5], 1):
        log.info(
            "watchlist_top",
            rank=i,
            wallet=s.wallet[:12],
            username=s.username,
            score=round(s.composite_score, 4),
            pnl=round(s.pnl_all, 2),
        )

    return stats


async def _load_watchlist_size() -> int:
    """Load watchlist size from app_config."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(AppConfig.value).where(AppConfig.key == "max_watched_traders")
        )
        row = result.scalar()

    if row and isinstance(row, dict):
        return int(row.get("value", DEFAULT_WATCHLIST_SIZE))
    return DEFAULT_WATCHLIST_SIZE
