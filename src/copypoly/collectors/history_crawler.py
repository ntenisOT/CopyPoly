"""Historical trade crawler — Phase 7.

Crawls all trade activities for tracked traders from the Polymarket
Data API and stores them in the `trade_history` table.

Features:
  - Incremental: tracks progress per trader, skips already-crawled
  - Idempotent: uses INSERT ... ON CONFLICT DO NOTHING
  - Rate-limited: configurable delay between API pages
  - Resumable: can restart at any point without duplicates

Usage:
    from copypoly.collectors.history_crawler import crawl_all_history
    stats = await crawl_all_history(top_n=500)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from copypoly.db.models import CrawlProgress, TradeHistory, Trader
from copypoly.db.session import async_session_factory
from copypoly.logging import get_logger

log = get_logger(__name__)

DATA_API = "https://data-api.polymarket.com"
PAGE_SIZE = 500
# Polymarket rate limit: 1000 req / 10 sec (100/s).
# We use 0.5s delay (~2 req/s) to stay well under limit.
DEFAULT_DELAY = 0.5
MAX_RETRIES = 3
RETRY_BACKOFF = [2, 4, 8]  # seconds between retries


async def crawl_trader_history(
    wallet: str,
    client: httpx.AsyncClient,
    delay: float = DEFAULT_DELAY,
) -> dict[str, Any]:
    """Crawl all activities for a single trader.

    Returns stats dict with counts and timestamps.
    """
    total_inserted = 0
    total_fetched = 0
    oldest_ts = None
    newest_ts = None
    offset = 0

    # Mark as running
    async with async_session_factory() as session:
        await session.execute(
            pg_insert(CrawlProgress)
            .values(
                trader_wallet=wallet,
                status="RUNNING",
                started_at=datetime.now(timezone.utc),
            )
            .on_conflict_do_update(
                index_elements=["trader_wallet"],
                set_={"status": "RUNNING", "started_at": datetime.now(timezone.utc)},
            )
        )
        await session.commit()

    try:
        while True:
            url = f"{DATA_API}/activity"
            params = {
                "user": wallet,
                "limit": PAGE_SIZE,
                "offset": offset,
                "sortDirection": "ASC",
            }

            # Retry with backoff for transient 400/429/5xx
            activities = None
            for attempt in range(MAX_RETRIES + 1):
                resp = await client.get(url, params=params, timeout=30)
                if resp.status_code == 200:
                    activities = resp.json()
                    break
                if resp.status_code in (400, 429, 500, 502, 503) and attempt < MAX_RETRIES:
                    wait = RETRY_BACKOFF[attempt]
                    log.warning(
                        "crawl_retry",
                        wallet=wallet[:10],
                        status=resp.status_code,
                        attempt=attempt + 1,
                        wait=wait,
                    )
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()

            if activities is None:
                break

            if not activities:
                break

            total_fetched += len(activities)

            # Prepare batch for insert
            rows = []
            for a in activities:
                ts = datetime.fromtimestamp(a["timestamp"], tz=timezone.utc)
                if oldest_ts is None or ts < oldest_ts:
                    oldest_ts = ts
                if newest_ts is None or ts > newest_ts:
                    newest_ts = ts

                rows.append({
                    "trader_wallet": wallet,
                    "timestamp": ts,
                    "condition_id": a.get("conditionId"),
                    "trade_type": a.get("type", "UNKNOWN"),
                    "side": a.get("side"),
                    "size": float(a["size"]) if a.get("size") else None,
                    "usdc_size": float(a["usdcSize"]) if a.get("usdcSize") else None,
                    "price": float(a["price"]) if a.get("price") else None,
                    "asset": a.get("asset"),
                    "outcome_index": a.get("outcomeIndex"),
                    "outcome": a.get("outcome"),
                    "transaction_hash": a.get("transactionHash"),
                    "market_title": a.get("title"),
                    "market_slug": a.get("slug"),
                })

            # Batch upsert (ON CONFLICT DO NOTHING)
            if rows:
                async with async_session_factory() as session:
                    stmt = pg_insert(TradeHistory).values(rows)
                    stmt = stmt.on_conflict_do_nothing(
                        constraint="uq_trade_history_tx"
                    )
                    result = await session.execute(stmt)
                    await session.commit()
                    total_inserted += result.rowcount

            log.debug(
                "crawl_page",
                wallet=wallet[:10],
                offset=offset,
                fetched=len(activities),
                inserted=total_inserted,
            )

            if len(activities) < PAGE_SIZE:
                break

            offset += PAGE_SIZE
            await asyncio.sleep(delay)

        # Mark complete
        async with async_session_factory() as session:
            await session.execute(
                update(CrawlProgress)
                .where(CrawlProgress.trader_wallet == wallet)
                .values(
                    status="COMPLETE",
                    activities_crawled=total_fetched,
                    oldest_timestamp=oldest_ts,
                    newest_timestamp=newest_ts,
                    completed_at=datetime.now(timezone.utc),
                    error_message=None,
                )
            )
            await session.commit()

    except Exception as e:
        # Mark error
        async with async_session_factory() as session:
            await session.execute(
                update(CrawlProgress)
                .where(CrawlProgress.trader_wallet == wallet)
                .values(status="ERROR", error_message=str(e)[:500])
            )
            await session.commit()
        log.error("crawl_error", wallet=wallet[:10], error=str(e))
        raise

    return {
        "wallet": wallet,
        "fetched": total_fetched,
        "inserted": total_inserted,
        "oldest": oldest_ts.isoformat() if oldest_ts else None,
        "newest": newest_ts.isoformat() if newest_ts else None,
    }


async def crawl_all_history(
    top_n: int = 500,
    delay: float = DEFAULT_DELAY,
    skip_complete: bool = True,
) -> dict[str, Any]:
    """Crawl trade history for the top N traders by composite score.

    Args:
        top_n: Number of top traders to crawl
        delay: Seconds between API pages (rate limiting)
        skip_complete: Skip traders already marked COMPLETE

    Returns:
        Summary stats dict
    """
    # Get traders to crawl
    async with async_session_factory() as session:
        result = await session.execute(
            select(Trader.wallet, Trader.username)
            .order_by(Trader.composite_score.desc())
            .limit(top_n)
        )
        traders = result.all()

        # If skipping complete, filter out
        if skip_complete:
            complete = (await session.execute(
                select(CrawlProgress.trader_wallet)
                .where(CrawlProgress.status == "COMPLETE")
            )).scalars().all()
            complete_set = set(complete)
            traders = [t for t in traders if t.wallet not in complete_set]

    log.info("crawl_starting", total_traders=len(traders), skip_complete=skip_complete)

    stats = {
        "total_traders": len(traders),
        "completed": 0,
        "failed": 0,
        "total_activities": 0,
        "total_inserted": 0,
    }

    async with httpx.AsyncClient() as client:
        for i, (wallet, username) in enumerate(traders):
            name = username or wallet[:10]
            log.info("crawling_trader", n=i + 1, total=len(traders), trader=name)

            # Pause between traders to avoid rate limiting
            if i > 0:
                await asyncio.sleep(2)

            try:
                result = await crawl_trader_history(wallet, client, delay)
                stats["completed"] += 1
                stats["total_activities"] += result["fetched"]
                stats["total_inserted"] += result["inserted"]
                log.info(
                    "trader_crawled",
                    trader=name,
                    fetched=result["fetched"],
                    inserted=result["inserted"],
                )
            except Exception as e:
                stats["failed"] += 1
                log.error("trader_crawl_failed", trader=name, error=str(e))

    log.info("crawl_complete", **stats)
    return stats
