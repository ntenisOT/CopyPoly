"""Scheduler — Orchestrates all data collection jobs.

Uses APScheduler to run collectors on configurable intervals.
Each collector runs as an independent async job.
"""

from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from copypoly.collectors.leaderboard import collect_leaderboard
from copypoly.collectors.markets import sync_markets
from copypoly.collectors.positions import collect_positions
from copypoly.config import settings
from copypoly.logging import get_logger

log = get_logger(__name__)


def create_scheduler() -> AsyncIOScheduler:
    """Create and configure the data collection scheduler.

    Jobs:
        1. Leaderboard collector — every N minutes (default: 5)
        2. Position monitor — every N seconds (default: 30)
        3. Market syncer — every N minutes (default: 15)

    Returns:
        Configured (but not started) scheduler.
    """
    scheduler = AsyncIOScheduler()

    # 1. Leaderboard collection
    scheduler.add_job(
        _run_leaderboard,
        trigger=IntervalTrigger(
            minutes=settings.leaderboard_update_interval_minutes,
        ),
        id="leaderboard_collector",
        name="Leaderboard Collector",
        max_instances=1,  # Only one instance at a time
        coalesce=True,    # If job was missed, run once (not N times)
    )

    # 2. Position monitoring (high frequency)
    scheduler.add_job(
        _run_positions,
        trigger=IntervalTrigger(
            seconds=settings.position_check_interval_seconds,
        ),
        id="position_monitor",
        name="Position Monitor",
        max_instances=1,
        coalesce=True,
    )

    # 3. Market data sync
    scheduler.add_job(
        _run_markets,
        trigger=IntervalTrigger(
            minutes=settings.market_sync_interval_minutes,
        ),
        id="market_syncer",
        name="Market Syncer",
        max_instances=1,
        coalesce=True,
    )

    # 4. Trader scoring & watchlist update (runs less frequently)
    scheduler.add_job(
        _run_scoring,
        trigger=IntervalTrigger(minutes=10),
        id="trader_scorer",
        name="Trader Scorer & Watchlist",
        max_instances=1,
        coalesce=True,
    )

    log.info(
        "scheduler_configured",
        leaderboard_interval=f"{settings.leaderboard_update_interval_minutes}m",
        position_interval=f"{settings.position_check_interval_seconds}s",
        market_interval=f"{settings.market_sync_interval_minutes}m",
        scoring_interval="10m",
    )

    return scheduler


async def _run_leaderboard() -> None:
    """Wrapper for leaderboard collector with error handling."""
    try:
        stats = await collect_leaderboard()
        log.info("leaderboard_job_complete", **stats)
    except Exception as e:
        log.error("leaderboard_job_failed", error=str(e), exc_info=True)


async def _run_positions() -> None:
    """Wrapper for position monitor with error handling."""
    try:
        stats = await collect_positions()
        if stats["traders_checked"] > 0:
            log.info("position_job_complete", **stats)
    except Exception as e:
        log.error("position_job_failed", error=str(e), exc_info=True)


async def _run_markets() -> None:
    """Wrapper for market syncer with error handling."""
    try:
        stats = await sync_markets()
        log.info("market_job_complete", **stats)
    except Exception as e:
        log.error("market_job_failed", error=str(e), exc_info=True)


async def _run_scoring() -> None:
    """Wrapper for trader scoring and watchlist update."""
    try:
        from copypoly.analysis.watchlist import update_watchlist

        stats = await update_watchlist()
        log.info("scoring_job_complete", **stats)
    except Exception as e:
        log.error("scoring_job_failed", error=str(e), exc_info=True)

