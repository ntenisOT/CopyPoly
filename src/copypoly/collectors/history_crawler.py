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

from copypoly.db.models import CrawlProgress, CrawlRun, TradeHistory, Trader
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

# Activity subgraph for merges, splits, redemptions
ACTIVITY_SUBGRAPH = (
    "https://api.goldsky.com/api/public/"
    "project_cl6mb8i9h0003e201j6li0diw/"
    "subgraphs/activity-subgraph/0.0.3/gn"
)


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

    my_asset = event["makerAssetId"] if is_maker else event["takerAssetId"]
    my_amount = int(event["makerAmountFilled"]) if is_maker else int(event["takerAmountFilled"])
    their_asset = event["takerAssetId"] if is_maker else event["makerAssetId"]
    their_amount = int(event["takerAmountFilled"]) if is_maker else int(event["makerAmountFilled"])

    # CTF token amounts are in 1e6 precision
    if my_asset == "0":
        # We gave USDC, received tokens -> This is a BUY of tokens
        side = "BUY"
        asset = their_asset
        usdc_size = my_amount / 1e6
        size = their_amount / 1e6
    else:
        # We gave tokens, received USDC -> This is a SELL of tokens
        side = "SELL"
        asset = my_asset
        size = my_amount / 1e6
        usdc_size = their_amount / 1e6

    price = usdc_size / size if size > 0 else None

    # Use FULL event ID as transaction_hash (unique per fill)
    return {
        "trader_wallet": wallet.lower(),
        "timestamp": ts,
        "condition_id": None,
        "trade_type": "TRADE",
        "side": side,
        "size": size,
        "usdc_size": usdc_size,
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
    resume_from_ts: int = 0,
) -> dict[str, int]:
    """Crawl one side (maker/taker) and store PAGE BY PAGE.

    If resume_from_ts > 0, only fetches events with timestamp >= that value.
    Dedup on insert handles overlap at the boundary.
    Returns dict with total_fetched, total_inserted, pages.
    """
    wallet_lower = wallet.lower()
    last_id = ""
    total_fetched = 0
    total_inserted = 0
    page = 0
    ts_filter = f', timestamp_gte: {resume_from_ts}' if resume_from_ts > 0 else ""
    if resume_from_ts > 0:
        log.info("resuming_from_ts", trader=trader_name, side=side, timestamp=resume_from_ts)

    while True:
        query = f"""{{
  orderFilledEvents(
    first: {PAGE_SIZE},
    orderBy: id,
    orderDirection: asc,
    where: {{{side}: "{wallet_lower}", id_gt: "{last_id}"{ts_filter}}}
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
        # Get resume timestamp from DB (for incremental updates)
        # Subtract 5 days as safety buffer; dedup handles overlap
        resume_ts = 0
        try:
            async with async_session_factory() as session:
                cp = (await session.execute(
                    select(CrawlProgress.newest_timestamp)
                    .where(CrawlProgress.trader_wallet == wallet_lower)
                )).scalar()
                if cp:
                    from datetime import timedelta
                    buffer = cp - timedelta(days=5)
                    resume_ts = int(buffer.timestamp())
                    log.info("incremental_resume", trader=name,
                             newest=cp.isoformat(), resume_from=buffer.isoformat())
        except Exception:
            pass  # Fresh crawl if DB query fails

        # 1. Crawl maker side from subgraph (store page-by-page)
        log.info("crawling_side", trader=name, side="maker")
        maker_stats = await _crawl_and_store_side(wallet, "maker", client, name, resume_ts)

        # 2. Crawl taker side from subgraph (store page-by-page)
        log.info("crawling_side", trader=name, side="taker")
        taker_stats = await _crawl_and_store_side(wallet, "taker", client, name, resume_ts)

        # 3. Crawl activity data (MERGE, SPLIT, REDEEM)
        # Redeems are always re-fetched per-condition (few events, dedup safe)
        log.info("crawling_activity", trader=name)
        activity_stats = await _crawl_activity_data(wallet, client, name, resume_ts)

        total_fetched = (
            maker_stats["fetched"] + taker_stats["fetched"]
            + activity_stats["fetched"]
        )
        total_inserted = (
            maker_stats["inserted"] + taker_stats["inserted"]
            + activity_stats["inserted"]
        )

        log.info(
            "trader_crawl_complete",
            trader=name,
            maker=maker_stats["fetched"],
            taker=taker_stats["fetched"],
            activity=activity_stats["fetched"],
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


async def _crawl_activity_data(
    wallet: str,
    client: httpx.AsyncClient,
    trader_name: str,
    resume_from_ts: int = 0,
) -> dict[str, int]:
    """Crawl MERGE, SPLIT, REDEMPTION events from Polymarket Activity Subgraph.

    Uses on-chain activity subgraph (not Data API) for complete data
    with no offset limits. This is critical for accurate PnL computation.
    If resume_from_ts > 0, only fetches events with timestamp >= that value.
    """
    wallet_lower = wallet.lower()
    total_fetched = 0
    total_inserted = 0

    activity_sg = (
        "https://api.goldsky.com/api/public/"
        "project_cl6mb8i9h0003e201j6li0diw/"
        "subgraphs/activity-subgraph/0.0.3/gn"
    )
    timeout = httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0)
    ts_filter = f', timestamp_gte: {resume_from_ts}' if resume_from_ts > 0 else ""

    # ── 1. Merges ──
    last_id = ""
    merge_count = 0
    while True:
        for attempt in range(3):
            try:
                resp = await client.post(activity_sg, json={"query": f"""{{
                    merges(first:1000, where:{{stakeholder:"{wallet_lower}", id_gt:"{last_id}"{ts_filter}}}, orderBy:id) {{
                        id timestamp condition amount
                    }}
                }}"""}, timeout=timeout)
                resp.raise_for_status()
                data = resp.json().get("data", {}).get("merges", [])
                break
            except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
                if attempt < 2:
                    await asyncio.sleep(3 * (attempt + 1))
                    continue
                log.warning("merge_fetch_failed", trader=trader_name, error=str(e)[:100])
                data = []
                break

        if not data:
            break

        rows = []
        for m in data:
            ts = datetime.fromtimestamp(int(m["timestamp"]), tz=timezone.utc)
            rows.append({
                "trader_wallet": wallet_lower,
                "timestamp": ts,
                "condition_id": m["condition"],
                "trade_type": "MERGE",
                "side": "MERGE",
                "size": int(m["amount"]) / 1e6,
                "usdc_size": int(m["amount"]) / 1e6,
                "price": 0.5,  # Merge = sell at $0.50
                "asset": m["condition"],  # Use condition as asset for merges
                "outcome_index": None,
                "outcome": None,
                "transaction_hash": m["id"],
                "market_title": None,
                "market_slug": None,
            })

        if rows:
            inserted = await _store_batch(rows)
            total_inserted += inserted

        merge_count += len(data)
        total_fetched += len(data)
        last_id = data[-1]["id"]
        if len(data) < 1000:
            break
        await asyncio.sleep(INTER_PAGE_DELAY)

    # ── 2. Splits ──
    last_id = ""
    split_count = 0
    while True:
        for attempt in range(3):
            try:
                resp = await client.post(activity_sg, json={"query": f"""{{
                    splits(first:1000, where:{{stakeholder:"{wallet_lower}", id_gt:"{last_id}"{ts_filter}}}, orderBy:id) {{
                        id timestamp condition amount
                    }}
                }}"""}, timeout=timeout)
                resp.raise_for_status()
                data = resp.json().get("data", {}).get("splits", [])
                break
            except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
                if attempt < 2:
                    await asyncio.sleep(3 * (attempt + 1))
                    continue
                log.warning("split_fetch_failed", trader=trader_name, error=str(e)[:100])
                data = []
                break

        if not data:
            break

        rows = []
        for s in data:
            ts = datetime.fromtimestamp(int(s["timestamp"]), tz=timezone.utc)
            rows.append({
                "trader_wallet": wallet_lower,
                "timestamp": ts,
                "condition_id": s["condition"],
                "trade_type": "SPLIT",
                "side": "SPLIT",
                "size": int(s["amount"]) / 1e6,
                "usdc_size": int(s["amount"]) / 1e6,
                "price": 0.5,  # Split = buy at $0.50
                "asset": s["condition"],
                "outcome_index": None,
                "outcome": None,
                "transaction_hash": s["id"],
                "market_title": None,
                "market_slug": None,
            })

        if rows:
            inserted = await _store_batch(rows)
            total_inserted += inserted

        split_count += len(data)
        total_fetched += len(data)
        last_id = data[-1]["id"]
        if len(data) < 1000:
            break
        await asyncio.sleep(INTER_PAGE_DELAY)

    # ── 3. Redemptions ──
    # CRITICAL: NegRisk redeems have the NegRiskAdapter as `redeemer`, NOT
    # the user wallet. So we CANNOT filter by redeemer.
    # Strategy: get condition list from PM closed-positions API, then query
    # redemptions per-condition (no redeemer filter).
    redeem_count = 0

    # Get conditions from PM closed-positions API (most complete source)
    conditions_set = set()
    try:
        resp = await client.get(
            "https://data-api.polymarket.com/closed-positions",
            params={"user": wallet_lower, "limit": 200},
            timeout=timeout,
        )
        resp.raise_for_status()
        for pos in resp.json():
            cid = pos.get("conditionId", "")
            if cid:
                conditions_set.add(cid)
    except Exception as e:
        log.warning("closed_positions_fetch_failed", trader=trader_name, error=str(e)[:100])

    # Also add conditions from merge events we already stored
    try:
        async with async_session_factory() as session:
            from sqlalchemy import func as sqlfunc
            db_conds = (await session.execute(
                select(sqlfunc.distinct(TradeHistory.condition_id))
                .where(TradeHistory.trader_wallet == wallet_lower)
                .where(TradeHistory.condition_id.isnot(None))
            )).scalars().all()
            conditions_set.update(db_conds)
    except Exception:
        pass

    log.info("redemption_conditions", trader=trader_name, conditions=len(conditions_set))

    # Query redemptions per-condition WITH redeemer filter
    # (matches verify_full_account.py which got 12/12 correct)
    for cond in conditions_set:
        for attempt in range(3):
            try:
                resp = await client.post(activity_sg, json={"query": f"""{{
                    redemptions(first:100, where:{{redeemer:"{wallet_lower}", condition:"{cond}"}}) {{
                        id timestamp condition payout
                    }}
                }}"""}, timeout=timeout)
                resp.raise_for_status()
                redeem_data = resp.json().get("data", {}).get("redemptions", [])
                break
            except (httpx.TimeoutException, httpx.HTTPStatusError):
                if attempt < 2:
                    await asyncio.sleep(3 * (attempt + 1))
                    continue
                redeem_data = []
                break

        if redeem_data:
            rows = []
            for rd in redeem_data:
                ts = datetime.fromtimestamp(int(rd["timestamp"]), tz=timezone.utc)
                rows.append({
                    "trader_wallet": wallet_lower,
                    "timestamp": ts,
                    "condition_id": rd["condition"],
                    "trade_type": "REDEEM",
                    "side": "REDEEM",
                    "size": int(rd["payout"]) / 1e6,
                    "usdc_size": int(rd["payout"]) / 1e6,
                    "price": 1.0,
                    "asset": rd["condition"],
                    "outcome_index": None,
                    "outcome": None,
                    "transaction_hash": rd["id"],
                    "market_title": None,
                    "market_slug": None,
                })
            if rows:
                inserted = await _store_batch(rows)
                total_inserted += inserted
            redeem_count += len(rows)
            total_fetched += len(rows)

        await asyncio.sleep(INTER_PAGE_DELAY)

    # ── 4. NegRisk Conversions ──
    # These are distinct from merges/splits — they convert NO tokens to YES
    # and vice versa within a NegRisk market. Important for PnL tracking.
    conversion_count = 0
    last_id = ""
    while True:
        for attempt in range(3):
            try:
                resp = await client.post(activity_sg, json={"query": f"""{{
                    negRiskConversions(first:1000, where:{{stakeholder:"{wallet_lower}", id_gt:"{last_id}"}}, orderBy:id) {{
                        id timestamp condition amount
                    }}
                }}"""}, timeout=timeout)
                resp.raise_for_status()
                data = resp.json().get("data", {}).get("negRiskConversions", [])
                break
            except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
                if attempt < 2:
                    await asyncio.sleep(3 * (attempt + 1))
                    continue
                log.warning("conversion_fetch_failed", trader=trader_name, error=str(e)[:100])
                data = []
                break

        if not data:
            break

        rows = []
        for c in data:
            ts = datetime.fromtimestamp(int(c["timestamp"]), tz=timezone.utc)
            rows.append({
                "trader_wallet": wallet_lower,
                "timestamp": ts,
                "condition_id": c["condition"],
                "trade_type": "CONVERSION",
                "side": "CONVERSION",
                "size": int(c["amount"]) / 1e6,
                "usdc_size": int(c["amount"]) / 1e6,
                "price": 0.0,
                "asset": c["condition"],
                "outcome_index": None,
                "outcome": None,
                "transaction_hash": c["id"],
                "market_title": None,
                "market_slug": None,
            })

        if rows:
            inserted = await _store_batch(rows)
            total_inserted += inserted

        conversion_count += len(data)
        total_fetched += len(data)
        last_id = data[-1]["id"]
        if len(data) < 1000:
            break
        await asyncio.sleep(INTER_PAGE_DELAY)

    log.info(
        "activity_complete",
        trader=trader_name,
        merges=merge_count,
        splits=split_count,
        redeems=redeem_count,
        conversions=conversion_count,
        total=total_fetched,
        inserted=total_inserted,
    )

    return {"fetched": total_fetched, "inserted": total_inserted, "pages": 0}


async def _verify_trader(wallet: str, name: str, crawl_result: dict) -> dict:
    """Verify crawled data using the EXACT per-market PnL calculator.

    Uses the same logic as verify_full_account.py which scored 22/22 on Theo4.
    Processes maker fills + merges + splits + redeems through PositionTracker,
    then compares per-position to PM's closed-positions API.
    """
    from collections import defaultdict
    from copypoly.pnl_calculator import PositionTracker, COLLATERAL_SCALE, FIFTY_CENTS

    wallet_lower = wallet.lower()
    report = {"trader": name, "wallet": wallet_lower[:12]}

    try:
        async with httpx.AsyncClient() as client:
            # 1. Get PM official data
            r = await client.get(
                "https://data-api.polymarket.com/closed-positions",
                params={"user": wallet_lower, "limit": 200},
                timeout=httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0),
            )
            all_pos = r.json()

            r_lb = await client.get(
                "https://data-api.polymarket.com/v1/leaderboard",
                params={"timePeriod": "all", "user": wallet_lower},
                timeout=httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0),
            )
            lb_data = r_lb.json()
            lb_pnl = float(lb_data[0].get("pnl", 0)) if lb_data else 0

            # Build lookup: asset -> PM data, condition -> [asset_ids]
            pm_by_asset = {}
            cond_to_assets = defaultdict(set)
            for p in all_pos:
                pm_by_asset[p["asset"]] = p
                cond = p.get("conditionId", "")
                cond_to_assets[cond].add(p["asset"])
                if p.get("oppositeAsset"):
                    cond_to_assets[cond].add(p["oppositeAsset"])

            # 2. Fetch MAKER fills from subgraph
            fills = []
            last_id = ""
            while True:
                q = f"""{{ orderFilledEvents(first:1000, orderBy:id, orderDirection:asc,
                  where:{{maker:"{wallet_lower}", id_gt:"{last_id}"}}) {{
                  id timestamp makerAssetId takerAssetId makerAmountFilled takerAmountFilled }} }}"""
                resp = await client.post(ORDERBOOK_SUBGRAPH, json={"query": q},
                                         timeout=httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0))
                data = resp.json().get("data", {}).get("orderFilledEvents", [])
                if not data:
                    break
                fills.extend(data)
                last_id = data[-1]["id"]
                if len(data) < 1000:
                    break
                await asyncio.sleep(0.05)

            # 3. Fetch merges, splits, redemptions from activity subgraph
            activity_sg = ACTIVITY_SUBGRAPH
            timeout = httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0)

            merges = []
            last_id = ""
            while True:
                resp = await client.post(activity_sg, json={"query": f"""{{
                    merges(first:1000, where:{{stakeholder:"{wallet_lower}", id_gt:"{last_id}"}}, orderBy:id) {{
                        id timestamp condition amount }} }}"""}, timeout=timeout)
                data = resp.json().get("data", {}).get("merges", [])
                if not data:
                    break
                merges.extend(data)
                last_id = data[-1]["id"]
                if len(data) < 1000:
                    break

            splits = []
            last_id = ""
            while True:
                resp = await client.post(activity_sg, json={"query": f"""{{
                    splits(first:1000, where:{{stakeholder:"{wallet_lower}", id_gt:"{last_id}"}}, orderBy:id) {{
                        id timestamp condition amount }} }}"""}, timeout=timeout)
                data = resp.json().get("data", {}).get("splits", [])
                if not data:
                    break
                splits.extend(data)
                last_id = data[-1]["id"]
                if len(data) < 1000:
                    break

            redeems = []
            for cond in cond_to_assets.keys():
                resp = await client.post(activity_sg, json={"query": f"""{{
                    redemptions(first:100, where:{{redeemer:"{wallet_lower}", condition:"{cond}"}}) {{
                        id timestamp condition payout }} }}"""}, timeout=timeout)
                rd_data = resp.json().get("data", {}).get("redemptions", [])
                redeems.extend(rd_data)
                await asyncio.sleep(0.05)

        # 4. Build sorted event list (timestamp, log_index, type, raw)
        def log_idx(eid: str) -> int:
            parts = eid.split("_")
            try:
                return int(parts[-1], 16) if len(parts) > 1 else 0
            except ValueError:
                return 0

        all_events = []
        for f in fills:
            all_events.append((int(f["timestamp"]), log_idx(f["id"]), "FILL", f))
        for m in merges:
            all_events.append((int(m["timestamp"]), log_idx(m["id"]), "MERGE", m))
        for s in splits:
            all_events.append((int(s["timestamp"]), log_idx(s["id"]), "SPLIT", s))
        for rd in redeems:
            all_events.append((int(rd["timestamp"]), log_idx(rd["id"]), "REDEEM", rd))

        all_events.sort(key=lambda x: (x[0], x[1]))

        # 5. Process through PnL calculator
        trackers = {}
        for ts, li, etype, raw in all_events:
            if etype == "FILL":
                maker_asset = raw["makerAssetId"]
                taker_asset = raw["takerAssetId"]
                maker_amount = int(raw["makerAmountFilled"])
                taker_amount = int(raw["takerAmountFilled"])

                if maker_asset == "0":
                    pos_id, base, quote = taker_asset, taker_amount, maker_amount
                    side = "BUY"
                else:
                    pos_id, base, quote = maker_asset, maker_amount, taker_amount
                    side = "SELL"

                if base <= 0:
                    continue
                price = quote * COLLATERAL_SCALE // base
                if pos_id not in trackers:
                    trackers[pos_id] = PositionTracker(pos_id)
                if side == "BUY":
                    trackers[pos_id].buy(price, base)
                else:
                    trackers[pos_id].sell(price, base)

            elif etype == "MERGE":
                cond = raw["condition"]
                amount = int(raw["amount"])
                for asset in cond_to_assets.get(cond, []):
                    if asset not in trackers:
                        trackers[asset] = PositionTracker(asset)
                    trackers[asset].sell(FIFTY_CENTS, amount)

            elif etype == "SPLIT":
                cond = raw["condition"]
                amount = int(raw["amount"])
                for asset in cond_to_assets.get(cond, []):
                    if asset not in trackers:
                        trackers[asset] = PositionTracker(asset)
                    trackers[asset].buy(FIFTY_CENTS, amount)

            elif etype == "REDEEM":
                cond = raw["condition"]
                for asset in cond_to_assets.get(cond, []):
                    if asset not in trackers:
                        continue
                    tracker = trackers[asset]
                    pm = pm_by_asset.get(asset, {})
                    cur_price = pm.get("curPrice", 0)
                    res_price = int(cur_price * COLLATERAL_SCALE)
                    tracker.sell(res_price, tracker.amount)

        # 6. Compare to PM
        matches = 0
        total = 0
        total_calc_pnl = 0.0
        total_pm_pnl = 0.0

        for p in all_pos:
            asset = p["asset"]
            tracker = trackers.get(asset)
            if not tracker:
                continue
            pm_pnl = p.get("realizedPnl", 0)
            pm_tb = p.get("totalBought", 0)
            pm_avg = p.get("avgPrice", 0)

            tb_ok = abs(tracker.total_bought_f - pm_tb) < max(0.01, pm_tb * 0.0001)
            avg_ok = abs(tracker.avg_price_f - pm_avg) < 0.001
            pnl_ok = abs(tracker.realized_pnl_f - pm_pnl) < max(0.01, abs(pm_pnl) * 0.0001)

            if tb_ok and avg_ok and pnl_ok:
                matches += 1
            total += 1
            total_calc_pnl += tracker.realized_pnl_f
            total_pm_pnl += pm_pnl

        report["positions_matched"] = f"{matches}/{total}"
        report["calc_pnl"] = round(total_calc_pnl, 2)
        report["pm_pnl"] = round(total_pm_pnl, 2)
        report["leaderboard_pnl"] = round(lb_pnl, 2)
        report["pnl_delta"] = round(total_calc_pnl - total_pm_pnl, 2)
        report["sane"] = matches == total
        report["verified"] = True

        report["stored_events"] = len(fills) + len(merges) + len(splits) + len(redeems)
        log.info("trader_verified", **report)

    except Exception as e:
        report["verified"] = False
        report["sane"] = False
        report["positions_matched"] = "0/0"
        report["calc_pnl"] = 0
        report["pm_pnl"] = 0
        report["leaderboard_pnl"] = 0
        report["pnl_delta"] = 0
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
            sane = verification.get("sane", False)

            # ── Auto-resync if verification fails with significant delta ──
            DELTA_THRESHOLD = 100  # $100 tolerance
            MAX_RESYNC = 3
            resync_attempts = 0

            while (
                not sane
                and abs(verification.get("pnl_delta", 0)) > DELTA_THRESHOLD
                and resync_attempts < MAX_RESYNC
            ):
                resync_attempts += 1
                log.warning(
                    "auto_resync_triggered",
                    trader=name,
                    attempt=resync_attempts,
                    delta=verification.get("pnl_delta", 0),
                )

                # Wipe this trader's trade_history and reset progress
                async with async_session_factory() as session:
                    await session.execute(
                        TradeHistory.__table__.delete()
                        .where(TradeHistory.trader_wallet == wallet.lower())
                    )
                    await session.execute(
                        update(CrawlProgress)
                        .where(CrawlProgress.trader_wallet == wallet.lower())
                        .values(
                            newest_timestamp=None,
                            oldest_timestamp=None,
                            activities_crawled=0,
                            resync_count=resync_attempts,
                        )
                    )
                    await session.commit()

                # Re-crawl from scratch and re-verify
                result = await crawl_trader_history(wallet, client, name)
                verification = await _verify_trader(wallet, name, result)
                sane = verification.get("sane", False)

            # Store verification notes in crawl_progress
            matched = verification.get("positions_matched", "?/?")
            calc_pnl = verification.get("calc_pnl", 0)
            pm_pnl = verification.get("pm_pnl", 0)
            lb_pnl = verification.get("leaderboard_pnl", 0)
            delta = verification.get("pnl_delta", 0)
            resync_tag = f" resync={resync_attempts}" if resync_attempts > 0 else ""
            notes = (
                f"{'[OK]' if sane else '[WARN]'} "
                f"matched={matched}, "
                f"calc=${calc_pnl:,.0f}, "
                f"pm=${pm_pnl:,.0f}, "
                f"lb=${lb_pnl:,.0f}, "
                f"delta=${delta:,.0f}"
                f"{resync_tag}"
            )
            async with async_session_factory() as session:
                await session.execute(
                    update(CrawlProgress)
                    .where(CrawlProgress.trader_wallet == wallet.lower())
                    .values(error_message=notes, resync_count=resync_attempts)
                )
                await session.commit()

            async with stats_lock:
                stats["completed"] += 1
                stats["total_activities"] += result["fetched"]
                stats["total_inserted"] += result["inserted"]
                if sane:
                    stats["ok"] = stats.get("ok", 0) + 1
                else:
                    stats["warn"] = stats.get("warn", 0) + 1
                if resync_attempts > 0:
                    stats["resynced"] = stats.get("resynced", 0) + 1

            log.info(
                "trader_crawled",
                worker=worker_id,
                trader=name,
                n=n,
                fetched=result["fetched"],
                inserted=result["inserted"],
                matched=matched,
                calc_pnl=round(calc_pnl, 0),
                resyncs=resync_attempts,
            )
        except Exception as e:
            async with stats_lock:
                stats["failed"] += 1
            log.error("trader_crawl_failed", worker=worker_id, trader=name, error=str(e))


async def crawl_all_history(
    top_n: int = 9999,
    skip_complete: bool = True,
    max_workers: int = 20,
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

    run_start = datetime.now(timezone.utc)
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
        "ok": 0,
        "warn": 0,
        "resynced": 0,
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

    # ── Auto-retry failed traders (up to 2 retries) ──
    for retry_round in range(1, 3):
        async with async_session_factory() as session:
            failed = (await session.execute(
                select(CrawlProgress.trader_wallet)
                .where(CrawlProgress.status == "ERROR")
            )).scalars().all()

        if not failed:
            break

        log.info("retry_starting", round=retry_round, failed=len(failed))

        # Reset status so workers pick them up
        async with async_session_factory() as session:
            await session.execute(
                update(CrawlProgress)
                .where(CrawlProgress.status == "ERROR")
                .values(status="PENDING", error_message=None)
            )
            await session.commit()

        # Look up usernames
        async with async_session_factory() as session:
            retry_traders = (await session.execute(
                select(Trader.wallet, Trader.username)
                .where(Trader.wallet.in_(failed))
            )).all()

        retry_sem = asyncio.Semaphore(5)  # fewer workers for retries
        async with httpx.AsyncClient() as client:
            retry_tasks = [
                _crawl_worker(
                    semaphore=retry_sem,
                    wallet=w,
                    username=u or "",
                    worker_id=(i % 5) + 1,
                    n=i + 1,
                    total=len(retry_traders),
                    client=client,
                    stats=stats,
                    stats_lock=stats_lock,
                )
                for i, (w, u) in enumerate(retry_traders)
            ]
            await asyncio.gather(*retry_tasks)

        log.info("retry_complete", round=retry_round)

    # ── Record run summary ──
    run_end = datetime.now(timezone.utc)
    duration = int((run_end - run_start).total_seconds())
    try:
        async with async_session_factory() as session:
            run = CrawlRun(
                started_at=run_start,
                completed_at=run_end,
                mode="crawl",
                total_traders=stats["total_traders"],
                ok_count=stats.get("ok", 0),
                warn_count=stats.get("warn", 0),
                error_count=stats["failed"],
                resync_count=stats.get("resynced", 0),
                total_events=stats["total_activities"],
                new_events=stats["total_inserted"],
                duration_seconds=duration,
                notes=(
                    f"OK={stats.get('ok',0)}, WARN={stats.get('warn',0)}, "
                    f"ERR={stats['failed']}, RESYNC={stats.get('resynced',0)}, "
                    f"events={stats['total_inserted']:,} new"
                ),
            )
            session.add(run)
            await session.commit()
    except Exception as e:
        log.warning("run_summary_save_failed", error=str(e)[:100])

    log.info("crawl_complete", **stats)
    return stats

