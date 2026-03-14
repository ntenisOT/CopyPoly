"""Historical trade crawler — Phase 7 (Subgraph edition).

Crawls all trade activities for tracked traders from Polymarket's
public Goldsky subgraph (on-chain data). No rate limiting, no errors,
data from Jan 2024+.

Key design: stores data PAGE BY PAGE (not all at once) so:
  - Progress is visible immediately
  - Memory stays low even for traders with 100K+ events
  - Crashes don't lose already-stored data
  - Each page logs its status

Usage:
    from copypoly.collectors.history_crawler import crawl_all_history
    stats = await crawl_all_history(top_n=500)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from copypoly.db.models import CrawlProgress, TradeHistory, Trader
from copypoly.db.session import async_session_factory
from copypoly.logging import get_logger

log = get_logger(__name__)

# Polymarket's public subgraph on Goldsky (free, no auth, no rate limits)
ORDERBOOK_SUBGRAPH = (
    "https://api.goldsky.com/api/public/"
    "project_cl6mb8i9h0003e201j6li0diw/"
    "subgraphs/orderbook-subgraph/0.0.1/gn"
)
PAGE_SIZE = 1000  # Max allowed by The Graph
INTER_PAGE_DELAY = 0.05  # Tiny polite delay between pages


async def _query_subgraph(
    client: httpx.AsyncClient,
    query: str,
) -> dict:
    """Execute a GraphQL query against the subgraph."""
    timeout = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)
    resp = await client.post(
        ORDERBOOK_SUBGRAPH,
        json={"query": query},
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(f"Subgraph error: {data['errors']}")
    return data["data"]


def _parse_event(event: dict, wallet: str) -> dict:
    """Parse a subgraph orderFilledEvent into a trade_history row."""
    ts = datetime.fromtimestamp(int(event["timestamp"]), tz=timezone.utc)
    is_maker = event["maker"].lower() == wallet.lower()

    if is_maker:
        side = "MAKER"
        asset = event["makerAssetId"]
        size_raw = int(event["makerAmountFilled"])
        counterpart_raw = int(event["takerAmountFilled"])
    else:
        side = "TAKER"
        asset = event["takerAssetId"]
        size_raw = int(event["takerAmountFilled"])
        counterpart_raw = int(event["makerAmountFilled"])

    # CTF token amounts are in 1e6 precision
    size = size_raw / 1e6
    counterpart = counterpart_raw / 1e6
    price = counterpart / size if size > 0 else None

    # Use FULL event ID as transaction_hash (unique per fill)
    return {
        "trader_wallet": wallet.lower(),
        "timestamp": ts,
        "condition_id": None,
        "trade_type": "TRADE",
        "side": side,
        "size": size,
        "usdc_size": counterpart,
        "price": price,
        "asset": asset,
        "outcome_index": None,
        "outcome": None,
        "transaction_hash": event["id"],
        "market_title": None,
        "market_slug": None,
    }


async def _store_batch(rows: list[dict]) -> int:
    """Store a batch of parsed events. Returns number of new rows inserted."""
    if not rows:
        return 0
    async with async_session_factory() as session:
        stmt = pg_insert(TradeHistory).values(rows)
        stmt = stmt.on_conflict_do_nothing(constraint="uq_trade_history_tx")
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount


async def _crawl_and_store_side(
    wallet: str,
    side: str,
    client: httpx.AsyncClient,
    trader_name: str,
) -> dict[str, int]:
    """Crawl one side (maker/taker) and store PAGE BY PAGE.

    Returns dict with total_fetched, total_inserted, pages.
    """
    wallet_lower = wallet.lower()
    last_id = ""
    total_fetched = 0
    total_inserted = 0
    page = 0

    while True:
        query = f"""{{
  orderFilledEvents(
    first: {PAGE_SIZE},
    orderBy: id,
    orderDirection: asc,
    where: {{{side}: "{wallet_lower}", id_gt: "{last_id}"}}
  ) {{
    id
    timestamp
    maker
    taker
    makerAssetId
    takerAssetId
    makerAmountFilled
    takerAmountFilled
  }}
}}"""
        # Retry on errors (up to 3 times)
        events = None
        for attempt in range(3):
            try:
                data = await _query_subgraph(client, query)
                events = data.get("orderFilledEvents", [])
                break
            except (RuntimeError, httpx.TimeoutException, httpx.HTTPStatusError) as e:
                if attempt < 2:
                    wait = 3 * (attempt + 1)
                    log.warning(
                        "subgraph_retry",
                        attempt=attempt + 1,
                        trader=trader_name,
                        side=side,
                        page=page,
                        error=str(e)[:100],
                        wait=wait,
                    )
                    await asyncio.sleep(wait)
                    continue
                raise

        if events is None or not events:
            break

        # Parse and store THIS page immediately
        rows = [_parse_event(e, wallet) for e in events]
        inserted = await _store_batch(rows)

        total_fetched += len(events)
        total_inserted += inserted
        page += 1
        last_id = events[-1]["id"]

        # Log every page for visibility
        log.info(
            "page_stored",
            trader=trader_name,
            side=side,
            page=page,
            fetched=len(events),
            inserted=inserted,
            total_fetched=total_fetched,
            total_inserted=total_inserted,
        )

        if len(events) < PAGE_SIZE:
            break

        await asyncio.sleep(INTER_PAGE_DELAY)

    return {
        "fetched": total_fetched,
        "inserted": total_inserted,
        "pages": page,
    }


async def crawl_trader_history(
    wallet: str,
    client: httpx.AsyncClient,
    trader_name: str = "",
) -> dict[str, Any]:
    """Crawl all trades for a single trader from the subgraph.

    Fetches both maker and taker sides, stores page-by-page.
    """
    wallet_lower = wallet.lower()
    name = trader_name or wallet[:10]

    # Mark as running
    async with async_session_factory() as session:
        await session.execute(
            pg_insert(CrawlProgress)
            .values(
                trader_wallet=wallet_lower,
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
        # Crawl maker side (store page-by-page)
        log.info("crawling_side", trader=name, side="maker")
        maker_stats = await _crawl_and_store_side(wallet, "maker", client, name)

        # Crawl taker side (store page-by-page)
        log.info("crawling_side", trader=name, side="taker")
        taker_stats = await _crawl_and_store_side(wallet, "taker", client, name)

        total_fetched = maker_stats["fetched"] + taker_stats["fetched"]
        total_inserted = maker_stats["inserted"] + taker_stats["inserted"]

        log.info(
            "trader_sides_complete",
            trader=name,
            maker_fetched=maker_stats["fetched"],
            maker_pages=maker_stats["pages"],
            taker_fetched=taker_stats["fetched"],
            taker_pages=taker_stats["pages"],
            total_inserted=total_inserted,
        )

        # Get date range from stored data
        async with async_session_factory() as session:
            from sqlalchemy import func
            oldest = (await session.execute(
                select(func.min(TradeHistory.timestamp))
                .where(TradeHistory.trader_wallet == wallet_lower)
            )).scalar()
            newest = (await session.execute(
                select(func.max(TradeHistory.timestamp))
                .where(TradeHistory.trader_wallet == wallet_lower)
            )).scalar()

        # Mark complete
        async with async_session_factory() as session:
            await session.execute(
                update(CrawlProgress)
                .where(CrawlProgress.trader_wallet == wallet_lower)
                .values(
                    status="COMPLETE",
                    activities_crawled=total_fetched,
                    oldest_timestamp=oldest,
                    newest_timestamp=newest,
                    completed_at=datetime.now(timezone.utc),
                    error_message=None,
                )
            )
            await session.commit()

    except Exception as e:
        async with async_session_factory() as session:
            await session.execute(
                update(CrawlProgress)
                .where(CrawlProgress.trader_wallet == wallet_lower)
                .values(status="ERROR", error_message=str(e)[:500])
            )
            await session.commit()
        log.error("crawl_error", trader=name, error=str(e))
        raise

    return {
        "wallet": wallet,
        "fetched": total_fetched,
        "inserted": total_inserted,
        "oldest": oldest.isoformat() if oldest else None,
        "newest": newest.isoformat() if newest else None,
    }


async def _verify_trader(wallet: str, name: str, crawl_result: dict) -> dict:
    """Verify crawled data against our stored leaderboard info.

    Returns verification report dict.
    """
    wallet_lower = wallet.lower()
    report = {"trader": name, "wallet": wallet_lower[:12]}

    try:
        async with async_session_factory() as session:
            from sqlalchemy import func as sqlfunc

            # Our stored data stats
            row = (await session.execute(
                select(
                    sqlfunc.count().label("events"),
                    sqlfunc.count(sqlfunc.distinct(TradeHistory.asset)).label("tokens"),
                    sqlfunc.min(TradeHistory.timestamp).label("oldest"),
                    sqlfunc.max(TradeHistory.timestamp).label("newest"),
                    sqlfunc.sum(TradeHistory.usdc_size).label("volume"),
                ).where(TradeHistory.trader_wallet == wallet_lower)
            )).one()

            report["stored_events"] = row.events
            report["unique_tokens"] = row.tokens
            report["first_trade"] = row.oldest.isoformat() if row.oldest else None
            report["last_trade"] = row.newest.isoformat() if row.newest else None
            report["total_volume"] = round(float(row.volume or 0), 2)

            # Compare with leaderboard data
            from copypoly.db.models import LeaderboardSnapshot
            lb_row = (await session.execute(
                select(
                    sqlfunc.max(LeaderboardSnapshot.pnl).label("pnl"),
                    sqlfunc.max(LeaderboardSnapshot.volume).label("lb_volume"),
                ).where(LeaderboardSnapshot.trader_wallet == wallet_lower)
                .where(LeaderboardSnapshot.period == "all")
            )).one()

            report["leaderboard_pnl"] = round(float(lb_row.pnl or 0), 2)
            report["leaderboard_volume"] = round(float(lb_row.lb_volume or 0), 2)

            # Data integrity checks
            report["fetched_eq_stored"] = crawl_result["fetched"] == row.events
            report["verified"] = True

        log.info("trader_verified", **report)

    except Exception as e:
        report["verified"] = False
        report["error"] = str(e)[:200]
        log.warning("verification_failed", trader=name, error=str(e)[:100])

    return report


async def _crawl_worker(
    semaphore: asyncio.Semaphore,
    wallet: str,
    username: str,
    worker_id: int,
    n: int,
    total: int,
    client: httpx.AsyncClient,
    stats: dict,
    stats_lock: asyncio.Lock,
) -> None:
    """Worker that crawls one trader with semaphore-controlled concurrency."""
    name = username or wallet[:10]

    async with semaphore:
        log.info(
            "crawling_trader",
            worker=worker_id,
            n=n,
            total=total,
            trader=name,
            wallet=wallet[:12],
        )

        try:
            result = await crawl_trader_history(wallet, client, name)

            # Verify data after crawl
            verification = await _verify_trader(wallet, name, result)

            # Store verification notes in crawl_progress
            notes = (
                f"events={verification.get('stored_events', '?')}, "
                f"tokens={verification.get('unique_tokens', '?')}, "
                f"volume=${verification.get('total_volume', 0):,.0f}, "
                f"lb_pnl=${verification.get('leaderboard_pnl', 0):,.0f}, "
                f"match={'YES' if verification.get('fetched_eq_stored') else 'NO'}"
            )
            async with async_session_factory() as session:
                await session.execute(
                    update(CrawlProgress)
                    .where(CrawlProgress.trader_wallet == wallet.lower())
                    .values(error_message=notes)  # reuse field for notes when COMPLETE
                )
                await session.commit()

            async with stats_lock:
                stats["completed"] += 1
                stats["total_activities"] += result["fetched"]
                stats["total_inserted"] += result["inserted"]

            log.info(
                "trader_crawled",
                worker=worker_id,
                trader=name,
                n=n,
                fetched=result["fetched"],
                inserted=result["inserted"],
                verified=verification.get("fetched_eq_stored", False),
            )
        except Exception as e:
            async with stats_lock:
                stats["failed"] += 1
            log.error("trader_crawl_failed", worker=worker_id, trader=name, error=str(e))


async def crawl_all_history(
    top_n: int = 500,
    skip_complete: bool = True,
    max_workers: int = 10,
) -> dict[str, Any]:
    """Crawl trade history for the top N traders via subgraph.

    Runs up to max_workers traders in PARALLEL for speed.

    Args:
        top_n: Number of top traders to crawl
        skip_complete: Skip traders already marked COMPLETE
        max_workers: Number of parallel crawl workers (default: 10)
    """
    async with async_session_factory() as session:
        result = await session.execute(
            select(Trader.wallet, Trader.username)
            .order_by(Trader.composite_score.desc().nulls_last())
            .limit(top_n)
        )
        traders = result.all()

        if skip_complete:
            complete = (await session.execute(
                select(CrawlProgress.trader_wallet)
                .where(CrawlProgress.status == "COMPLETE")
            )).scalars().all()
            complete_set = set(complete)
            traders = [t for t in traders if t.wallet.lower() not in complete_set]

    log.info(
        "crawl_starting",
        total_traders=len(traders),
        max_workers=max_workers,
        source="subgraph",
    )

    stats = {
        "total_traders": len(traders),
        "completed": 0,
        "failed": 0,
        "total_activities": 0,
        "total_inserted": 0,
    }
    stats_lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(max_workers)

    async with httpx.AsyncClient() as client:
        tasks = [
            _crawl_worker(
                semaphore=semaphore,
                wallet=wallet,
                username=username or "",
                worker_id=(i % max_workers) + 1,
                n=i + 1,
                total=len(traders),
                client=client,
                stats=stats,
                stats_lock=stats_lock,
            )
            for i, (wallet, username) in enumerate(traders)
        ]
        await asyncio.gather(*tasks)

    log.info("crawl_complete", **stats)
    return stats

