# Trade History Data Analysis — Backtesting Readiness

> Crawl in progress: 181K events stored so far, 3/2,594 traders complete

## What We Have

| Field | Status | Example |
|-------|--------|---------|
| `trader_wallet` | ✅ Full | `0x6a72f618...` |
| `timestamp` | ✅ Full | 2024-10-14 → 2026-03-14 (**516 days**) |
| `side` | ✅ Full | `MAKER` (83%) / `TAKER` (17%) |
| `size` | ✅ Full | Amount of asset the trader provides |
| `usdc_size` | ✅ Full | Amount of counterpart asset received |
| `price` | ✅ Full | `usdc_size / size` ratio |
| `asset` | ✅ Full | Token ID (`0` = USDC, else CTF token) |
| `transaction_hash` | ✅ Full | Unique event ID |

## What's Missing (NULL)

| Field | Status | Impact |
|-------|--------|--------|
| `condition_id` | ❌ NULL | Can't group trades by market yet |
| `market_title` | ❌ NULL | No human-readable market name |
| `market_slug` | ❌ NULL | Can't link to Polymarket UI |
| `outcome` | ❌ NULL | Don't know if it's YES/NO token |
| `outcome_index` | ❌ NULL | Don't know outcome index |

## Key Insight: The `asset=0` Trick

The **critical discovery** is that `asset = '0'` means the trader is providing **USDC** (the stablecoin), and `asset != '0'` means they're providing a **CTF token** (prediction market token).

This lets us determine **trade direction**:

```
If asset = '0' → Trader is PROVIDING USDC → They are BUYING tokens
If asset ≠ '0' → Trader is PROVIDING tokens → They are SELLING tokens
```

### Distribution

| Direction | Side | Count | Avg Size | Avg Counterpart | Avg Price |
|-----------|------|-------|----------|-----------------|-----------|
| **Buying tokens** (asset=0) | MAKER | 153,081 | $958 | 1,908 tokens | - |
| **Selling tokens** (asset≠0) | TAKER | 22,831 | 3,466 tokens | $1,723 | $0.46 |
| **Buying tokens** (asset=0) | TAKER | 7,450 | $849 | 1,620 tokens | - |
| **Selling tokens** (asset≠0) | MAKER | 99 | 14,985 tokens | $14,798 | $0.81 |

## Can We Backtest With Current Data?

### ✅ YES — Here's What's Possible

**Basic "Copy Trader" Backtesting:**

1. **Replay trades** in chronological order per trader
2. **Determine direction** using the `asset=0` trick:
   - `asset = '0'` → BUY (spending USDC to get tokens)
   - `asset ≠ '0'` → SELL (giving tokens to get USDC)
3. **Calculate PnL** per token:
   - Entry cost = USDC spent when buying
   - Exit proceeds = USDC received when selling same token
   - PnL = exit - entry
4. **Simulate copying** with configurable delay, slippage, position sizing

### What Works Without Market Names

- ✅ Total PnL per trader (sum of all buy/sell cycles)
- ✅ Win rate (how many token cycles were profitable)
- ✅ Trade frequency and timing patterns
- ✅ Average trade size and holding period
- ✅ Risk metrics (max drawdown, Sharpe ratio)
- ✅ Copy-delay impact (what if we copied 1 min / 5 min / 1 hour later)

### What Requires Phase 7.2-7.4 Data

- ❌ Per-market PnL breakdown (need `condition_id` → market mapping)
- ❌ Category analysis (politics vs sports vs crypto)
- ❌ Resolution PnL (need redemption events from activity subgraph)
- ❌ "Which markets does trader X specialize in?"

## Enrichment Path (Quick Win)

> [!TIP]
> We can enrich existing data WITHOUT re-crawling by querying the MarketData entity:
>
> ```graphql
> { marketDatas(where: {id: "<token_id>"}) { condition outcomeIndex } }
> ```
>
> This maps token IDs → condition IDs → market names (via Gamma API).
> Can be done as a post-processing step on the stored data.

## Recommendation

**Start backtesting NOW** with current data. The `asset=0` trick gives us buy/sell direction, and we have full price + size + timestamp data. We can add market-level analysis later as an enrichment pass.

### Stats Summary

| Metric | Value |
|--------|-------|
| Total events | 181,461 |
| Date range | 516 days (Oct 2024 → Mar 2026) |
| Traders with data | 3 (of 2,594 being crawled) |
| Unique token IDs | 2,073 |
| Price range | $0.01 → $1.00 (prediction market odds) |
| Median price | $0.50 (balanced bets) |
| Dominant direction | 88% buying, 12% selling |
