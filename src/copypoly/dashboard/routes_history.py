"""History / Data Lake API endpoints — Phase 7.

Provides endpoints to trigger the historical trade crawler
(subgraph-based) and monitor its progress.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select

from copypoly.db.models import CrawlProgress, TradeHistory
from copypoly.db.session import async_session_factory
from copypoly.logging import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["history"])


class CrawlRequest(BaseModel):
    top_n: int = 500
    skip_complete: bool = True


# Background crawl task reference
_crawl_task: asyncio.Task | None = None


async def _run_crawl_background(top_n: int, skip_complete: bool):
    """Run the crawl in background (not blocking the API response)."""
    from copypoly.collectors.history_crawler import crawl_all_history

    try:
        await crawl_all_history(top_n=top_n, skip_complete=skip_complete)
    except Exception as e:
        log.error("background_crawl_failed", error=str(e))


@router.post("/crawl")
async def trigger_crawl(body: CrawlRequest) -> dict:
    """Start the historical trade crawler in the background.

    Uses Polymarket's Goldsky subgraph (on-chain data).
    Returns immediately — monitor progress via GET /api/crawl/progress.
    """
    global _crawl_task

    if _crawl_task and not _crawl_task.done():
        return {"status": "already_running", "message": "Crawl is already in progress"}

    _crawl_task = asyncio.create_task(
        _run_crawl_background(body.top_n, body.skip_complete)
    )

    return {
        "status": "started",
        "source": "subgraph",
        "top_n": body.top_n,
        "skip_complete": body.skip_complete,
    }


@router.get("/crawl/progress")
async def get_crawl_progress() -> dict:
    """Get current crawl progress across all traders."""
    from copypoly.db.models import Trader

    async with async_session_factory() as session:
        # Total scored traders (the denominator for progress)
        total_scored = (await session.execute(
            select(func.count()).select_from(Trader)
            .where(Trader.composite_score > 0)
        )).scalar() or 0

        # Crawl progress stats
        processed = (await session.execute(
            select(func.count()).select_from(CrawlProgress)
        )).scalar() or 0

        complete = (await session.execute(
            select(func.count()).select_from(CrawlProgress)
            .where(CrawlProgress.status == "COMPLETE")
        )).scalar() or 0

        running = (await session.execute(
            select(func.count()).select_from(CrawlProgress)
            .where(CrawlProgress.status == "RUNNING")
        )).scalar() or 0

        errors = (await session.execute(
            select(func.count()).select_from(CrawlProgress)
            .where(CrawlProgress.status == "ERROR")
        )).scalar() or 0

        total_activities = (await session.execute(
            select(func.count()).select_from(TradeHistory)
        )).scalar() or 0

        total_crawled = (await session.execute(
            select(func.sum(CrawlProgress.activities_crawled))
        )).scalar() or 0

        recent = (await session.execute(
            select(CrawlProgress)
            .order_by(CrawlProgress.completed_at.desc().nulls_last())
            .limit(10)
        )).scalars().all()

    is_running = _crawl_task is not None and not _crawl_task.done()
    denominator = total_scored if total_scored > 0 else processed

    return {
        "is_running": is_running,
        "source": "subgraph",
        "total_traders": total_scored,
        "processed": processed,
        "complete": complete,
        "running": running,
        "errors": errors,
        "total_activities_crawled": total_crawled,
        "total_activities_stored": total_activities,
        "progress_pct": round((complete / denominator) * 100, 1) if denominator > 0 else 0,
        "recent": [
            {
                "wallet": p.trader_wallet[:10] + "...",
                "status": p.status,
                "activities": p.activities_crawled,
                "completed_at": p.completed_at.isoformat() if p.completed_at else None,
                "error": p.error_message[:80] if p.error_message else None,
            }
            for p in recent
        ],
    }


@router.get("/history/stats")
async def get_history_stats() -> dict:
    """Get statistics about the stored trade history data."""
    async with async_session_factory() as session:
        total = (await session.execute(
            select(func.count()).select_from(TradeHistory)
        )).scalar() or 0

        traders_with_data = (await session.execute(
            select(func.count(func.distinct(TradeHistory.trader_wallet)))
        )).scalar() or 0

        if total > 0:
            oldest = (await session.execute(
                select(func.min(TradeHistory.timestamp))
            )).scalar()
            newest = (await session.execute(
                select(func.max(TradeHistory.timestamp))
            )).scalar()
            avg_per_trader = total / traders_with_data if traders_with_data else 0

            type_counts = (await session.execute(
                select(TradeHistory.trade_type, func.count())
                .group_by(TradeHistory.trade_type)
            )).all()
        else:
            oldest = newest = None
            avg_per_trader = 0
            type_counts = []

    return {
        "source": "subgraph",
        "total_activities": total,
        "traders_with_data": traders_with_data,
        "avg_per_trader": round(avg_per_trader),
        "oldest_activity": oldest.isoformat() if oldest else None,
        "newest_activity": newest.isoformat() if newest else None,
        "by_type": {t: c for t, c in type_counts},
        "estimated_size_mb": round(total * 400 / 1024 / 1024, 1),
    }
