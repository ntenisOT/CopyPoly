# CopyPoly — Lessons Learned

Log of corrections and patterns to prevent recurring mistakes.

---

## 2026-03-14: Hatchling build-backend typo
- **Mistake**: Used `hatchling.backends` instead of `hatchling.build` in pyproject.toml
- **Rule**: Always verify build-backend module paths — check official docs, not memory

## 2026-03-14: JSONB server_default double-quoting
- **Mistake**: Used `server_default="'[]'"` for JSONB columns, which SQLAlchemy double-quoted to `'''[]'''`
- **Rule**: For JSONB defaults, always use `server_default=text("'[]'::jsonb")` with explicit cast

## 2026-03-14: Missing psycopg2 for Alembic
- **Mistake**: Only included `asyncpg` but Alembic runs synchronously and needs `psycopg2`
- **Rule**: Always include both `asyncpg` (for app) AND `psycopg2-binary` (for Alembic) in dependencies

## 2026-03-14: Missing README.md for hatchling
- **Mistake**: pyproject.toml referenced `readme = "README.md"` but file didn't exist in Docker build
- **Rule**: If pyproject.toml references README.md, ensure it exists AND is copied in Dockerfile

## 2026-03-14: GPG signing blocks git commit
- **Mistake**: Git commit hung because global GPG signing was enabled
- **Rule**: Disable GPG signing per-repo with `git config --local commit.gpgsign false`

## 2026-03-14: Polymarket API uses `timePeriod` not `period`
- **Mistake**: Used `period=ALL` based on third-party docs; API silently ignored it and returned all-time data for every period
- **Rule**: Always verify API params against the actual website's network requests. The correct param is `timePeriod` with lowercase values: `day`, `week`, `month`, `all`
- **Impact**: This would have made our entire analysis engine worthless — it was comparing identical data across "different" periods

## 2026-03-14: Data API is unreliable for historical data
- **Mistake**: Used Polymarket Data API for historical trade crawling; got 80% error rate due to Cloudflare rate limiting
- **Rule**: For large-scale historical data crawling, always prefer on-chain data (subgraphs) over REST APIs
- **Solution**: Replaced with Polymarket's Goldsky subgraph (free, no auth, no rate limits)

## 2026-03-14: Never accumulate large datasets in memory before writing
- **Mistake**: Collected ALL events for a trader (~160K) in memory before writing to DB. Appeared "stuck" for 10+ minutes
- **Rule**: Store page-by-page as data arrives. Each page (1000 events) should be immediately persisted and logged
- **Impact**: Fixed the apparent hang, provided real-time progress visibility, and reduced memory usage

## 2026-03-14: Use full event ID for trade uniqueness, not just txHash
- **Mistake**: Extracted only `txHash` from subgraph event ID (`txHash_orderHash`). A single transaction can have multiple fills, causing uniqueness collisions
- **Rule**: Use the full event ID as the unique identifier. In The Graph, event IDs are already unique per fill

## 2026-03-14: Scheduled jobs can race with themselves
- **Mistake**: Position scanner job used plain INSERT for new positions. When two scheduler cycles overlapped, the same position was inserted twice → UniqueViolation error
- **Rule**: Always use INSERT...ON CONFLICT (upsert) for data that could be detected by concurrent job runs

## 2026-03-14: Polymarket Volume and PnL metrics calculation
- **Mistake**: Tried calculating Volume directly from public trades (subgraph). None of the 7 formulas tested precisely matched Polymarket's reported volume because they calculate it server-side using internal CLOB logic (potentially double-counting maker-taker pairs or handling partial fills differently).
- **Rule**: Volume cannot be reliably derived from public data. Read Volume directly from the Leaderboard API. PnL is straightforward `Amount Won - Total Cost`, except the "initial deposit" must be derived by subtracting Leaderboard PnL from Net Cashflow (Buys/Sells/Redeems/Merges/Rewards).

## 2026-03-14: Subgraph event sides (BUY vs SELL)
- **Mistake**: Did not explicitly consider which token ID in a subgraph fill event corresponds to USDC (asset="0") when parsing TRADE events.
- **Rule**: To determine if a trade is a BUY or SELL of condition tokens, inspect if `makerAssetId == "0"` or `takerAssetId == "0"`. The side giving USDC ("0") is BUYING tokens. The side giving actual tokens is SELLING into USDC.

## 2026-03-14: Per-market PnL links YES+NO via MERGE/REDEEM (Taylor Swift reconciliation)
- **Discovery**: Polymarket's per-market `realizedPnl` in `closed-positions` accounts for BOTH sides of a condition (YES and NO tokens together), not just the single asset.
- **Example**: Taylor Swift "No" token — PM says pnl=-21.35, but raw trades show only a 50-share buy at $46.35. The missing piece: trader also bought YES shares for $3.72, then did a MERGE (YES+NO→USDC) returning $49.99. PM's PnL formula factors in this cross-token MERGE cost.
- **Rule**: Per-market PnL = `(merge_returns + redeem_returns + sell_usdc) - (buy_usdc_yes + buy_usdc_no)` for the entire `conditionId`, not per individual asset token.
- **Implication**: To reconcile per-market, you MUST track both YES and NO tokens under each `conditionId` and account for MERGE events that consume tokens from both sides.

## 2026-03-14: Data API activity endpoint is heavily truncated
- **Discovery**: The Data API `/activity` endpoint has a hard 3000-offset limit AND aggregates multiple fills into single "TRADE" entries. For Theo4's largest market (Trump popular vote), Data API returned only 283 trades (2M shares) vs Subgraph's 6,327 fills (14M shares).
- **Rule**: The Data API is NOT suitable for historical trade reconstruction. Use it ONLY for `REDEEM`, `MERGE`, `SPLIT`, `REWARD` events (which are not in the subgraph) and for recent activity. The subgraph is the ground truth for trade fills.
- **Verified**: For the tiny Taylor Swift market (50 shares), Data API and Subgraph both returned the same single BUY trade, confirming the Data API is accurate for recent/small datasets but truncates for large ones.

## 2026-03-14: Polymarket fee structure
- **Discovery**: Polymarket does NOT charge fees on most markets. They make money through:
  1. **Dynamic taker fees** on specific high-frequency markets (crypto short-term, sports). Fees peak at ~1.56% at 50% probability, decrease toward 0%/100%.
  2. **No fees on winnings** — winning shares redeem at $1.00 USDC with no platform cut.
  3. **Maker rebates** — a portion of taker fees goes back to liquidity providers.
- **Rule**: For most political/event markets (like all of Theo4's), there are NO trading fees. This means our subgraph data should match PM's numbers exactly (no hidden fee deductions). Any PnL discrepancy is due to data completeness or aggregation logic, not fees.
- **Impact**: This simplifies reconciliation — we don't need to account for commissions in our PnL calculations for standard markets.

## 2026-03-14: Polymarket API endpoints discovered
- **Discovery**: By inspecting the Polymarket frontend network calls, we identified the exact API surface:
  - `data-api.polymarket.com/activity` — paginated activity feed (trades, redeems, merges)
  - `data-api.polymarket.com/closed-positions` — per-market realized PnL with `totalBought`, `avgPrice`, `realizedPnl`
  - `data-api.polymarket.com/positions` — active (open) positions
  - `data-api.polymarket.com/v1/leaderboard` — global PnL, volume, rank
  - `user-pnl-api.polymarket.com/user-pnl` — historical PnL time series for charting
- **Rule**: Always inspect the frontend network tab to discover the real API surface rather than relying on documentation or guesswork. Valid `sortBy` values for `closed-positions`: `realizedpnl`, `avgprice`, `price`, `title`, `timestamp`.

## 2026-03-14: Activity Subgraph — merges/redeems/splits on-chain
- **Discovery**: The `polymarket-subgraph` GitHub repo (github.com/Polymarket/polymarket-subgraph) contains **7 subgraphs**, not just the 2 listed in the Goldsky docs. The critical one we were missing:
  - **`activity-subgraph/0.0.3`** — has `Split`, `Merge`, `Redemption`, `NegRiskConversion` entities
  - URL: `https://api.goldsky.com/api/public/project_cl6mb8i9h0003e201j6li0diw/subgraphs/activity-subgraph/0.0.3/gn`
- **Schema**: Merge/Split use `stakeholder` + `condition` + `amount`. Redemption uses `redeemer` + `condition` + `payout`.
- **Caveat**: This subgraph is NOT listed in the official Goldsky docs. Only `orderbook-subgraph/0.0.1` and `oi-subgraph/0.0.6` are. Risk of deprecation exists but it's under Polymarket's own project ID.
- **Performance**: Wallet-level redemption queries timeout for large traders. Use condition-level filters (`condition: "0x..."`) instead.

## 2026-03-14: Global PnL reconciliation confirmed ✅ 
- **Result**: Using purely on-chain data (orderbook-subgraph + activity-subgraph), we successfully reconciled Theo4's PnL:
  - `buy_usdc = $26,523,931` (from 20,498 fills)
  - `sell_usdc = $17,006,500`
  - `merge_usdc = $815,379` (33 events from activity-subgraph)
  - `redeem_usdc = $41,281,118` (from activity-subgraph per-condition queries)
  - `Net Cashflow = sell + merge + redeem - buy = $27,869,935`
  - `Leaderboard PnL = $22,053,934`
  - `Implied Deposit = $5,816,001`
- **Rule**: Global PnL = `Net Cashflow - Implied Deposit`. The implied deposit is always a positive number representing actual USDC deposited by the trader. If it comes out negative, something is wrong with the data.
- **Per-market PnL still doesn't match** PM's closed-positions because PM uses a different internal formula (see below).

## 2026-03-14: Complete Polymarket data architecture
- **Orderbook Subgraph** (`orderbook-subgraph/0.0.1`): Only `OrderFilledEvent` — raw CLOB fills. No merges, redeems, or splits. This is where ALL trades live.
- **Activity Subgraph** (`activity-subgraph/0.0.3`): `Split`, `Merge`, `Redemption`, `NegRiskConversion`. These are CTF contract events, NOT on the CLOB.
- **Data API** (`data-api.polymarket.com/activity`): Aggregated view of both — combines trades, redeems, merges. BUT has a hard 3000-offset limit AND aggregates multiple fills into single trades. Not suitable for large-scale historical data.
- **Rule**: For complete data, use BOTH subgraphs: orderbook for trades, activity for everything else. The Data API is only useful for finding `closed-positions`, `leaderboard` stats, and recent activity.

## 2026-03-14: Per-market PnL formula — FULLY CRACKED from source code ✅
- **Source**: `github.com/Polymarket/polymarket-subgraph/tree/main/pnl-subgraph/src/`
- **PnL subgraph is NOT deployed publicly** on Goldsky (probed versions 0.0.0 through 2.9.9, all 404). But the DATA API uses the same logic internally.
- **BUY logic** (`updateUserPositionWithBuy.ts`):
  - `avgPrice = (avgPrice * currentAmount + price * buyAmount) / (currentAmount + buyAmount)`
  - `amount += buyAmount`
  - `totalBought += buyAmount`
- **SELL logic** (`updateUserPositionWithSell.ts`):
  - `adjustedAmount = min(sellAmount, currentAmount)` ← caps at held amount
  - `realizedPnl += adjustedAmount * (sellPrice - avgPrice)`
  - `amount -= adjustedAmount`
- **Event mapping** (`ConditionalTokensMapping.ts`):
  - **MERGE → SELL at $0.50** for BOTH YES and NO positions
  - **SPLIT → BUY at $0.50** for BOTH YES and NO positions
  - **REDEEM → SELL at resolution price** (`payoutNumerator/payoutDenominator`) for remaining amount
  - Events from NegRiskAdapter or CTFExchange address are SKIPPED (handled separately in NegRiskAdapterMapping.ts)
- **This explains everything**: merge at $0.50 means if you bought YES at $0.40, you realize $0.10/share profit. If you bought NO at $0.60, you realize -$0.10/share loss. Net is always zero.

## 2026-03-14: Subgraph fill parsing — maker gives makerAsset, taker gives takerAsset
- **Mistake**: Confused which amount maps to shares vs USDC. Got sell events showing 45 shares for 3.29 USDC when it was actually 3.29 USDC for 45 shares.
- **Rule**: In the orderbook subgraph: **maker GIVES `makerAssetId` (amount=`makerAmountFilled`)**, **taker GIVES `takerAssetId` (amount=`takerAmountFilled`)**. To determine what OUR wallet gave/got: check if wallet is maker or taker, then map accordingly. The asset with ID "0" is always USDC.

## 2026-03-14: PnL subgraph only tracks MAKER fills ⚠️
- **Source**: `parseOrderFilled.ts` — comment says `"the taker is always the exchange!"`. The `account` is always `event.params.maker`.
- **Impact**: When computing PnL from raw fills, ONLY use fills where our wallet is the `maker`. Taker fills are the exchange proxy re-routing — not the user's trade.
- **Exception**: For our storage/display purposes (showing trade history), we DO want both sides. But for PnL CALCULATION specifically, maker-only.

## 2026-03-14: Phase 2 verification — 22/22 positions match ✅
- **Result**: All 22 positions for Theo4 match PM's closed-positions within tolerance.
- **Data processed**: 16,002 maker fills + 33 merges + 12 redemptions + 0 splits = 16,047 events.
- **Total PnL**: calc=$22,053,861 vs PM=$22,053,934 — **$73 delta on $22M** (0.0003% — integer division rounding).
- **All `totalBought` values**: EXACT MATCH (0.000000 delta).
- **All `avgPrice` values**: match within 0.000004.
- **Rounding note**: Large positions (5-10M shares) accumulate tiny rounding diffs from `BigInt.div()` floor division over thousands of operations.

## 2026-03-14: Crawler should use activity subgraph, not Data API
- **Problem**: The Data API (`/v1/activity`) is truncated at offset 3000. For large traders, most merges/redeems are lost.
- **Fix**: Replace Data API activity crawl with the **activity subgraph** (`activity-subgraph/0.0.3`) which has no limits and is paginated like the orderbook subgraph.
- **Activity subgraph entities**: `merges` (stakeholder, condition, amount), `splits` (same), `redemptions` (redeemer, condition, payout).

## 2026-03-14: Redemption queries need condition list from PM API
- **Problem**: Trade fills don't store `condition_id`, so we can't get the list of conditions a trader participated in from our own DB. Without conditions, wallet-level redemption queries either timeout (large traders) or miss data.
- **Fix**: Fetch the condition list from PM's `closed-positions` API, then query `redemptions(redeemer: wallet, condition: cond)` per-condition — exactly as verified in `verify_full_account.py`.
- **Verified**: This approach gets 12/12 redeems for Theo4 ($41.3M), matching Phase 2 perfectly.
- **Trap**: Removing the `redeemer` filter to "catch NegRisk" causes storing ALL redeems for those conditions (1400+ from random users). Always filter by redeemer.

## 2026-03-14: Use per-market PnL calculator for verification, not cashflow
- **Problem**: Global cashflow formula (`sell + redeem - buy - merge = net → pnl = net - deposit`) gives false negatives for traders with open positions.
- **Fix**: Use the exact per-market PnL calculator from `verify_full_account.py` — processes all events through `PositionTracker`, compares per-position to PM's `closed-positions` API.
- **Result**: 22/22 Theo4 ($73 delta on $22M), 50/50 Fredi9999 ($24 delta on $18.6M). All rounding errors from integer division.

## 2026-03-15: Don't use MAX() on hex subgraph IDs for resume cursors
- **Problem**: Subgraph event IDs are hex strings (`0xabc..._0xdef...`). SQL `MAX()` returns the lexicographically largest, NOT the chronologically latest. Using this as `id_gt` cursor skips events with smaller hex IDs that occurred later.
- **Fix**: Use `timestamp_gte` with the `newest_timestamp` from `crawl_progress` minus a 5-day safety buffer. Dedup (`on_conflict_do_nothing`) handles the overlap.

## 2026-03-15: Incremental crawl design
- **Pattern**: Always crawl incrementally by default. Read `newest_timestamp` from `crawl_progress`, subtract 5 days, use `timestamp_gte` in subgraph queries.
- **Modes**: `crawl` (default, incremental) and `resync` (wipe DB + full re-crawl).
- **Safety**: Dedup constraint on `transaction_hash` ensures re-fetching overlap events is harmless.

## 2026-03-15: CRITICAL — Docker Compose volume recreation on config change
- **Problem**: Changed `docker-compose.yml` (added `command`, `deploy` to PG service) then ran `docker compose down && up --build`. Docker Compose recreated the named volume `copypoly-pgdata` because the service config hash changed. **Lost 85M events / 80GB of data.**
- **Root Cause**: Docker Compose tracks a `config-hash` label on each volume. When the service definition changes, the hash changes, and compose may recreate the volume.
- **Prevention**: **ALWAYS `pg_dump` before modifying docker-compose.yml service definitions that affect the DB container.** Use `docker volume inspect` to verify volume creation date after restarts.
- **Alembic lesson**: Autogenerated migration was garbage (only nullable diffs, missed CREATE TABLE / ADD COLUMN). Always review autogenerated migrations before applying. Had to manually apply SQL and rewrite the migration file.
