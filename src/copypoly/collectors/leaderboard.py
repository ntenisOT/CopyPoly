"""Leaderboard Collector — Fetches and stores top trader data.

Runs on a schedule (default: every 5 minutes).
Covers all time periods (ALL, MONTH, WEEK, DAY) and stores
snapshots in leaderboard_snapshots for trend analysis.
Also upserts trader profiles into the traders table.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from copypoly.api.data import DataAPIClient
from copypoly.db.models import LeaderboardSnapshot, Trader
from copypoly.db.session import async_session_factory
from copypoly.logging import get_logger

log = get_logger(__name__)

# Periods to scrape (matches API timePeriod values)
PERIODS = ["all", "month", "week", "day"]

# How many traders to fetch per period
LEADERBOARD_LIMIT = 1000


async def collect_leaderboard() -> dict[str, int]:
    """Fetch leaderboard data for all periods and store in DB.

    Returns:
        Dict mapping period → number of traders stored.
    """
    client = DataAPIClient()
    stats: dict[str, int] = {}

    try:
        for period in PERIODS:
            count = await _collect_period(client, period)
            stats[period] = count
    finally:
        await client.close()

    total = sum(stats.values())
    log.info("leaderboard_collection_complete", stats=stats, total_snapshots=total)
    return stats


async def _collect_period(
    client: DataAPIClient,
    period: str,
) -> int:
    """Fetch and store leaderboard for a single period.

    Args:
        client: Data API client.
        period: Time period (all, month, week, day).

    Returns:
        Number of entries stored.
    """
    log.info("collecting_leaderboard", period=period)

    try:
        entries = await client.get_full_leaderboard(
            period=period,
            max_traders=LEADERBOARD_LIMIT,
        )
    except Exception as e:
        log.error(
            "leaderboard_fetch_failed",
            period=period,
            error=str(e),
        )
        return 0

    if not entries:
        log.warning("leaderboard_empty", period=period)
        return 0

    now = datetime.now(timezone.utc)

    async with async_session_factory() as session:
        for entry in entries:
            await _upsert_trader(session, entry, now)
            await _insert_snapshot(session, entry, period, "overall", now)

        await session.commit()

    log.info(
        "leaderboard_stored",
        period=period,
        entries=len(entries),
    )
    return len(entries)


async def _upsert_trader(
    session: AsyncSession,
    entry: dict,
    now: datetime,
) -> None:
    """Insert or update a trader profile from leaderboard data.

    On conflict (wallet already exists), updates scores and last_seen_at.
    """
    wallet = entry.get("proxyWallet", "").lower()
    if not wallet:
        return

    # Map leaderboard fields to our model
    stmt = pg_insert(Trader).values(
        wallet=wallet,
        username=entry.get("userName"),
        profile_image=entry.get("profileImage"),
        x_username=entry.get("xUsername"),
        last_seen_at=now,
    )

    # On conflict: update profile data and last_seen
    stmt = stmt.on_conflict_do_update(
        index_elements=["wallet"],
        set_={
            "username": stmt.excluded.username,
            "profile_image": stmt.excluded.profile_image,
            "x_username": stmt.excluded.x_username,
            "last_seen_at": now,
            "updated_at": now,
        },
    )

    await session.execute(stmt)


async def _insert_snapshot(
    session: AsyncSession,
    entry: dict,
    period: str,
    category: str,
    captured_at: datetime,
) -> None:
    """Insert a leaderboard snapshot row.

    Uses ON CONFLICT DO NOTHING to avoid duplicates from
    the same collection run.
    """
    wallet = entry.get("proxyWallet", "").lower()
    if not wallet:
        return

    pnl = float(entry.get("pnl", 0))
    volume = float(entry.get("vol", 0))
    rank = int(entry.get("rank", 0))

    stmt = pg_insert(LeaderboardSnapshot).values(
        trader_wallet=wallet,
        period=period,
        category=category,
        rank=rank,
        pnl=pnl,
        volume=volume,
        captured_at=captured_at,
    )

    # Skip duplicates (same trader+period+category+timestamp)
    stmt = stmt.on_conflict_do_nothing(
        constraint="uq_leaderboard_snapshot",
    )

    await session.execute(stmt)


async def update_trader_best_pnl(wallet: str) -> None:
    """Update a trader's best PnL fields from stored snapshots.

    Called after collecting new snapshots to keep the traders table current.
    """
    async with async_session_factory() as session:
        # Get best PnL per period from snapshots
        for period, column in [
            ("all", "best_pnl_all_time"),
            ("month", "best_pnl_monthly"),
            ("week", "best_pnl_weekly"),
            ("day", "best_pnl_daily"),
        ]:
            result = await session.execute(
                select(LeaderboardSnapshot.pnl)
                .where(
                    LeaderboardSnapshot.trader_wallet == wallet,
                    LeaderboardSnapshot.period == period,
                )
                .order_by(LeaderboardSnapshot.pnl.desc())
                .limit(1)
            )
            best_pnl = result.scalar()

            if best_pnl is not None:
                await session.execute(
                    text(
                        f"UPDATE traders SET {column} = :pnl, updated_at = now() "
                        "WHERE wallet = :wallet"
                    ),
                    {"pnl": float(best_pnl), "wallet": wallet},
                )

        await session.commit()
