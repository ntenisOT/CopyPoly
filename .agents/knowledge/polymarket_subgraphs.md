# Polymarket Goldsky Subgraph — Knowledge Base

> Last updated: 2026-03-14
> Source: Actual GraphQL schema introspection + real crawling experience

## Why Subgraphs Over Data API

| Factor | Data API | Goldsky Subgraph |
|--------|----------|------------------|
| Rate limiting | Cloudflare blocks at ~80% of requests | No rate limits |
| Authentication | None but aggressively rate-limited | None needed |
| Historical range | Limited, returns empty for old data | Full on-chain history |
| Data completeness | Some trades missing | Every on-chain fill event |
| Speed | ~1 trade/sec (with errors) | ~1000 events/sec |
| Cost | Free | Free |
| Reliability | 20% success rate for bulk crawling | 100% success rate |

## Subgraph Endpoints

Base URL: `https://api.goldsky.com/api/public/project_cl6mb8i9h0003e201j6li0diw/subgraphs/`

| Subgraph | Version | Status | Endpoint Suffix |
|----------|---------|--------|-----------------|
| **orderbook-subgraph** | 0.0.1 | ✅ Active | `orderbook-subgraph/0.0.1/gn` |
| **activity-subgraph** | 0.0.3 | ✅ Active | `activity-subgraph/0.0.3/gn` |
| **oi-subgraph** | 0.0.6 | ✅ Active | `oi-subgraph/0.0.6/gn` |
| **pnl-subgraph** | all tested | ❌ 404 | Not available |
| **polymarket-subgraph** | all tested | ❌ 404 | Not available |

> **Tested versions**: 0.0.1 through 0.0.12, 0.1.0, 0.2.0, 1.0.0-1.0.2

---

## Orderbook Subgraph Schema (v0.0.1)

### OrderFilledEvent ⭐ (Primary - what we crawl)
Every individual trade fill on the CTF exchange.

| Field | Type | Description |
|-------|------|-------------|
| `id` | ID | Unique: `txHash_orderHash` format (~133 chars) |
| `transactionHash` | Bytes | On-chain tx hash |
| `timestamp` | BigInt | Unix timestamp |
| `orderHash` | Bytes | Order identifier |
| `maker` | String | Maker wallet address (lowercase) |
| `taker` | String | Taker wallet address (lowercase) |
| `makerAssetId` | String | Token ID of asset maker provides |
| `takerAssetId` | String | Token ID of asset taker provides |
| `makerAmountFilled` | BigInt | Amount of maker asset (in wei, /1e6) |
| `takerAmountFilled` | BigInt | Amount of taker asset (in wei, /1e6) |
| `fee` | BigInt | Fee amount |

**Key facts:**
- A single TX can have multiple fills (one taker matched against many makers)
- `id` is unique per fill — use this, NOT just `transactionHash`
- Wallet addresses are always lowercase hex
- Use `id_gt` for cursor-based pagination (most reliable)
- Can query by `maker` or `taker` filter
- kch123 (top trader) has ~134K maker + ~26K taker = ~160K events
- Average top-50 trader has ~40K events

### MarketData
Maps token IDs to market conditions.

| Field | Type | Description |
|-------|------|-------------|
| `id` | ID | Token ID (same as makerAssetId/takerAssetId) |
| `condition` | String | Condition ID (links to market) |
| `outcomeIndex` | BigInt | 0 = No, 1 = Yes |

**Use case:** Enrich trades with market context. Token ID → Condition → Market name (via Gamma API).

### Orderbook
Per-market aggregate volume stats.

| Field | Type | Description |
|-------|------|-------------|
| `id` | ID | Market identifier |
| `tradesQuantity` | BigInt | Total number of trades |
| `buysQuantity` | BigInt | Number of buy trades |
| `sellsQuantity` | BigInt | Number of sell trades |
| `collateralVolume` | BigInt | Total USDC volume |
| `scaledCollateralVolume` | BigDecimal | Human-readable volume |
| `collateralBuyVolume` / `collateralSellVolume` | BigInt | Buy/sell volume breakdown |

### OrdersMatchedEvent
Matched order pairs (higher-level than fills).

| Field | Type |
|-------|------|
| `id` | ID |
| `timestamp` | BigInt |
| `makerAssetID` | BigInt |
| `takerAssetID` | BigInt |
| `makerAmountFilled` | BigInt |
| `takerAmountFilled` | BigInt |

### OrdersMatchedGlobal
Platform-wide aggregate stats (same fields as Orderbook).

---

## Activity Subgraph Schema (v0.0.3)

### Split
User splits USDC into conditional tokens (entering a position).

| Field | Type | Description |
|-------|------|-------------|
| `id` | ID | Unique identifier |
| `timestamp` | BigInt | When the split occurred |
| `stakeholder` | String | User wallet address |
| `condition` | String | Market condition ID |
| `amount` | BigInt | USDC amount split |

### Merge
User merges Yes+No tokens back to USDC (exiting without market resolution).

| Field | Type | Description |
|-------|------|-------------|
| `id` | ID | Unique identifier |
| `timestamp` | BigInt | When the merge occurred |
| `stakeholder` | String | User wallet address |
| `condition` | String | Market condition ID |
| `amount` | BigInt | Amount merged |

### Redemption
User redeems winning tokens after market resolution.

| Field | Type | Description |
|-------|------|-------------|
| `id` | ID | Unique identifier |
| `timestamp` | BigInt | When the redemption occurred |
| `redeemer` | String | User wallet address |
| `condition` | String | Market condition ID |
| `indexSets` | ? | Which outcome(s) redeemed |

### Other entities
- `NegRiskConversion` — Neg-risk market operations
- `NegRiskEvent` — Neg-risk events
- `FixedProductMarketMaker` — AMM data
- `Position` — `{id, condition, outcomeIndex}`
- `Condition` — `{id}`

---

## OI Subgraph Schema (v0.0.6)

### MarketOpenInterest
Per-market open interest.

| Field | Type | Description |
|-------|------|-------------|
| `id` | ID | Market identifier |
| `amount` | BigInt | Open interest amount |

### Other entities
- `GlobalOpenInterest` — Platform-wide OI
- `Condition` — Market condition refs
- `NegRiskEvent` — Neg-risk tracking

---

## Crawling Best Practices (Learned from Experience)

### Pagination
- Use `id_gt` cursor-based pagination, NOT skip/offset
- `first: 1000` is the max page size
- Always `orderBy: id, orderDirection: asc`
- Example: `where: {maker: "0xabc...", id_gt: "<last_id>"}`

### Performance
- Average page fetch: 0.7-1.1 seconds
- Throughput: ~8,000 events per 15 seconds
- kch123 (160K events): ~2.5 minutes total

### Timeout Handling
```python
timeout = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)
```
- Catch `RuntimeError` (subgraph error in body), `httpx.TimeoutException`, `httpx.HTTPStatusError`
- Retry up to 3 times with exponential backoff (3s, 6s, 9s)

### Storage Strategy
- **ALWAYS store page-by-page**, never accumulate in memory
- Use `INSERT ... ON CONFLICT DO NOTHING` for idempotency
- Batch inserts in chunks of 500-1000 for optimal PostgreSQL performance
- Full event ID as unique key (not just txHash)

### Wallet Address Handling
- Subgraph stores/queries addresses in lowercase hex
- Polymarket leaderboard API returns checksummed addresses (mixed case)
- Always `.lower()` before querying subgraph

---

## Trade Lifecycle on Polymarket

```
1. SPLIT: User deposits USDC → gets Yes + No tokens
   Source: activity-subgraph → Split entity

2. TRADE: User trades tokens on the CTF exchange
   Source: orderbook-subgraph → OrderFilledEvent

3a. MERGE: User merges Yes+No → gets USDC back (exit before resolution)
    Source: activity-subgraph → Merge entity

3b. REDEEM: Market resolves → user redeems winning tokens for USDC
    Source: activity-subgraph → Redemption entity
```

**For accurate PnL calculation, you need ALL of these.**
The PnL subgraph (which would pre-compute this) is currently unavailable (404).

---

## Computing PnL Without PnL Subgraph

Since the PnL subgraph is unavailable, compute from raw data:

1. **Entry cost** = Sum of USDC spent via:
   - Splits (direct USDC → tokens)
   - OrderFilledEvents where trader is taker buying tokens

2. **Exit proceeds** = Sum of USDC received via:
   - Merges (tokens → USDC)
   - OrderFilledEvents where trader is taker selling tokens
   - Redemptions (winning tokens → USDC)

3. **Realized PnL** = Exit proceeds - Entry cost (for closed positions)
4. **Unrealized PnL** = Current token value - Entry cost (for open positions)
