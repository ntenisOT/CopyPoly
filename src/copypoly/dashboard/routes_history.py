"""History / Data Lake API endpoints — Phase 7.

Provides endpoints to trigger the historical trade crawler
(subgraph-based) and monitor its progress.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select
import sqlalchemy as sa

from copypoly.db.models import CrawlProgress, CrawlRun, TradeHistory
from copypoly.db.session import async_session_factory
from copypoly.logging import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["history"])


class CrawlRequest(BaseModel):
    top_n: int = 9999
    mode: str = "crawl"            # "crawl" = incremental, "resync" = wipe DB + full re-crawl
    max_workers: int = 20
    delta_threshold: float = 0.001  # 0.1% PnL tolerance for auto-resync (0 = disable)


# Background crawl task reference
_crawl_task: asyncio.Task | None = None


async def _run_crawl_background(
    top_n: int, mode: str, max_workers: int = 20, delta_threshold: float = 100
):
    """Run the crawl in background (not blocking the API response)."""
    from copypoly.collectors.history_crawler import crawl_all_history

    # Reset in-memory stats
    _crawl_stats.clear()

    try:
        if mode == "resync":
            async with async_session_factory() as session:
                await session.execute(TradeHistory.__table__.delete())
                await session.execute(CrawlProgress.__table__.delete())
                await session.commit()
            log.info("resync_wiped_db")

        await crawl_all_history(
            top_n=top_n,
            skip_complete=False,
            max_workers=max_workers,
            delta_threshold=delta_threshold,
            live_stats=_crawl_stats,
        )
    except Exception as e:
        log.error("background_crawl_failed", error=str(e))


@router.post("/crawl")
async def trigger_crawl(body: CrawlRequest) -> dict:
    """Start the historical trade crawler in the background.

    mode='crawl': Incremental update. Fetches new data since last crawl.
    mode='resync': Wipes all trade data and re-crawls everything from scratch.

    Returns immediately — monitor progress via GET /api/crawl/progress.
    """
    global _crawl_task

    if _crawl_task and not _crawl_task.done():
        return {"status": "already_running", "message": "Crawl is already in progress"}

    _crawl_task = asyncio.create_task(
        _run_crawl_background(body.top_n, body.mode, body.max_workers, body.delta_threshold)
    )

    return {
        "status": "started",
        "source": "subgraph",
        "top_n": body.top_n,
        "mode": body.mode,
        "delta_threshold": body.delta_threshold,
    }


# In-memory crawl stats — updated by the crawler, read by the progress endpoint.
# Zero DB queries needed for progress checks.
_crawl_stats: dict = {}


@router.get("/crawl/progress")
async def get_crawl_progress() -> dict:
    """Get current crawl progress — pure in-memory, no DB queries."""
    is_running = _crawl_task is not None and not _crawl_task.done()
    s = _crawl_stats

    total = s.get("total_traders", 0)
    completed = s.get("completed", 0)
    failed = s.get("failed", 0)
    running = total - completed - failed if total > 0 else 0

    return {
        "is_running": is_running,
        "source": "subgraph",
        "total_traders": total,
        "processed": completed + failed,
        "complete": completed,
        "running": max(0, running),
        "errors": failed,
        "ok": s.get("ok", 0),
        "warn": s.get("warn", 0),
        "resynced": s.get("resynced", 0),
        "total_activities_crawled": s.get("total_activities", 0),
        "total_activities_stored": s.get("total_inserted", 0),
        "progress_pct": round((completed / total) * 100, 1) if total > 0 else 0,
        "recent": s.get("recent", []),
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


@router.get("/crawl/runs")
async def get_crawl_runs() -> list[dict]:
    """Get the last 20 crawl run summaries."""
    async with async_session_factory() as session:
        runs = (await session.execute(
            select(CrawlRun)
            .order_by(CrawlRun.id.desc())
            .limit(20)
        )).scalars().all()

    return [
        {
            "id": r.id,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "mode": r.mode,
            "total_traders": r.total_traders,
            "ok": r.ok_count,
            "warn": r.warn_count,
            "errors": r.error_count,
            "resynced": r.resync_count,
            "total_events": r.total_events,
            "new_events": r.new_events,
            "duration_seconds": r.duration_seconds,
            "notes": r.notes,
        }
        for r in runs
    ]
