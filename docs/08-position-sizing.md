# Position Sizing Algorithm

## Overview

The Position Sizing Algorithm determines **how much capital** to allocate to each copy trade. It bridges the gap between "who to copy" (the Trader Scorer) and "how to execute" (the Order Executor). The key principle is: **higher-scored traders get a larger share of the portfolio.**

All parameters in this document are stored in `app_config` and adjustable at runtime via the dashboard.

---

## Core Formula

```
Trade Size = Portfolio Value
           × (1 - Cash Reserve %)
           × Per-Trader Allocation %
           × Confidence Multiplier
           × Risk Adjustment
           × Conflict Discount
```

### Step-by-Step Breakdown

### Step 1: Available Capital

```
Available Capital = Total Portfolio Value × (1 - cash_reserve_pct)

Config: cash_reserve_pct (default: 0.20 = 20%)
```

We always keep a cash reserve to handle:
- Slippage on executions
- Opportunity to add positions
- Buffer against sudden drawdowns

**Example:** $1,000 portfolio × (1 - 0.20) = **$800 available**

---

### Step 2: Per-Trader Allocation (Score-Based)

Each watched trader gets a share of the available capital proportional to their composite score:

```python
def calculate_trader_allocation(trader_score: float, all_watched_scores: list[float]) -> float:
    """
    Returns a percentage (0.0 - 1.0) of available capital for this trader.
    Capped by max_per_trader_allocation.
    """
    total_score = sum(all_watched_scores)
    if total_score == 0:
        return 0
    
    raw_allocation = trader_score / total_score
    return min(raw_allocation, max_per_trader_allocation)
```

**Config:** `max_per_trader_allocation` (default: 0.25 = 25%)

**Example with 5 watched traders:**

| Trader | Score | Raw Allocation | Capped (max 25%) | Base $ (of $800) |
|--------|-------|----------------|-------------------|------------------|
| WindWalk3 | 1.72 | 22.8% | 22.8% | $182 |
| Erasmus | 1.68 | 22.3% | 22.3% | $178 |
| tomatosauce | 1.61 | 21.4% | 21.4% | $171 |
| Bama124 | 1.38 | 18.3% | 18.3% | $146 |
| Trader5 | 1.14 | 15.1% | 15.1% | $121 |
| **Total** | **7.53** | **100%** | **100%** | **$800** |

---

### Step 3: Confidence Multiplier

Scales the trade based on how good the trader is relative to the median:

```python
def confidence_multiplier(trader_score: float, median_score: float) -> float:
    """
    Traders above median get full size (1.0).
    Traders below median get reduced size.
    Capped between 0.5 and 1.0 to avoid extremes.
    """
    if median_score == 0:
        return 1.0
    ratio = trader_score / median_score
    return max(0.5, min(1.0, ratio))
```

**Example:**
- Median score = 1.61
- WindWalk3 (1.72): multiplier = min(1.0, 1.72/1.61) = **1.0**
- Bama124 (1.38): multiplier = max(0.5, 1.38/1.61) = **0.857**
- Trader5 (1.14): multiplier = max(0.5, 1.14/1.61) = **0.708**

---

### Step 4: Risk Adjustment (Liquidity)

Reduces trade size if the target market has low liquidity:

```python
def risk_adjustment(market_liquidity: float, trade_size: float) -> float:
    """
    Ensure our trade doesn't exceed a fraction of market liquidity.
    Config: max_market_impact_pct (default: 0.02 = 2%)
    """
    max_size = market_liquidity * max_market_impact_pct
    if trade_size <= max_size:
        return 1.0
    return max_size / trade_size
```

**Config:** `max_market_impact_pct` (default: 0.02 = 2%)

**Example:**
- Market liquidity = $10,000
- Max trade size = $10,000 × 2% = $200
- If we want to trade $182: adjustment = **1.0** (fits within 2%)
- If we want to trade $250: adjustment = $200/$250 = **0.80**

---

### Step 5: Conflict Discount

When multiple watched traders disagree on a market (opposite bets), reduce the position:

```python
def conflict_discount(yes_score_sum: float, no_score_sum: float) -> float:
    """
    If traders are split on a market, reduce size based on consensus strength.
    1.0 = full consensus (all YES or all NO)
    0.0 = perfect split (skip the trade)
    """
    total = yes_score_sum + no_score_sum
    if total == 0:
        return 0.0
    
    consensus = abs(yes_score_sum - no_score_sum) / total
    
    # Apply minimum threshold — if consensus < 0.3, skip entirely
    if consensus < min_consensus_threshold:
        return 0.0
    
    return consensus
```

**Config:** `min_consensus_threshold` (default: 0.30)

**Examples:**

| Scenario | YES Score Sum | NO Score Sum | Consensus | Discount | Action |
|----------|--------------|-------------|-----------|----------|--------|
| All agree YES | 5.0 | 0.0 | 1.00 | 1.0 | Full size |
| Strong YES | 4.0 | 1.0 | 0.60 | 0.6 | 60% size |
| Weak YES | 3.0 | 2.0 | 0.20 | 0.0 | **SKIP** (below 0.30) |
| Perfect split | 2.5 | 2.5 | 0.00 | 0.0 | **SKIP** |

---

## Complete Example

**Scenario:** WindWalk3 opens a new YES position in "BTC > 100K?" market.

```
Portfolio:              $1,000
Cash Reserve (20%):     $200
Available Capital:      $800

WindWalk3 Score:         1.72
All Watched Scores Sum: 7.53
Per-Trader Allocation:  1.72 / 7.53 = 22.8% → $182.40

Confidence Multiplier:  1.72 / 1.61 (median) → 1.0 (capped)

Market Liquidity:       $50,000
Max Impact (2%):        $1,000
Risk Adjustment:        1.0 (trade << market limit)

Conflict Check:
  - WindWalk3 YES (score 1.72)
  - Erasmus YES (score 1.68)
  - No one holds NO
  Consensus:           1.0 (full agreement)
  Conflict Discount:   1.0

Final Trade Size = $182.40 × 1.0 × 1.0 × 1.0 = $182.40

→ BUY $182.40 of YES shares in "BTC > 100K?"
```

---

## Configuration Summary

All parameters stored in `app_config`:

```json
{
  "position_sizing": {
    "cash_reserve_pct": 0.20,
    "max_per_trader_allocation": 0.25,
    "max_per_market_allocation": 0.15,
    "max_single_position_usdc": 200,
    "max_market_impact_pct": 0.02,
    "min_consensus_threshold": 0.30,
    "min_trade_size_usdc": 5.0
  }
}
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `cash_reserve_pct` | 0.20 | Always keep 20% of portfolio in cash |
| `max_per_trader_allocation` | 0.25 | No single trader gets >25% of portfolio |
| `max_per_market_allocation` | 0.15 | No single market across all traders gets >15% |
| `max_single_position_usdc` | 200 | Hard cap on any individual trade |
| `max_market_impact_pct` | 0.02 | Max 2% of market liquidity per trade |
| `min_consensus_threshold` | 0.30 | Skip trade if consensus <30% |
| `min_trade_size_usdc` | 5.0 | Skip trades smaller than $5 (not worth gas/slippage) |

---

## Safety Guardrails

Even after sizing, these hard limits apply:

1. **Max single position**: Never exceed `max_single_position_usdc` regardless of score
2. **Max per-market exposure**: Total across all traders in one market ≤ `max_per_market_allocation` × portfolio
3. **Daily loss limit**: If cumulative daily losses exceed threshold, halt all copying
4. **Minimum trade size**: Skip trades below `min_trade_size_usdc`
5. **Cash reserve enforcement**: Never dip below `cash_reserve_pct` of portfolio

---

## Future Enhancements

### Kelly Criterion (Optional, Post-Phase 6)

For advanced users, offer Kelly-based sizing using the trader's win rate and average payoff:

```
Kelly % = Win_Rate - ((1 - Win_Rate) / Avg_Win_Loss_Ratio)
```

This mathematically optimizes growth rate of the portfolio but requires robust win rate estimates. We could offer a "half-Kelly" variant for more conservative sizing.

### Dynamic Weighting

As we accumulate data on which traders we've profited from most, dynamically adjust allocations:
- Increase allocation to traders whose copies have been profitable
- Decrease allocation to traders whose copies have lost money
- This creates a feedback loop that improves over time
