# Trader Scoring Algorithm

## Overview

The Trader Scoring Algorithm is the core intelligence of CopyPoly. It takes raw leaderboard data and transforms it into a single **composite score** that reflects a trader's overall quality and reliability for copy trading purposes.

## Why a Composite Score?

Raw PnL alone is misleading:
- A trader with $1M PnL from a single lucky bet is **not** someone to copy
- A trader with $50K PnL from 200 consistently profitable trades **is**
- We need to weight **consistency**, **win rate**, **risk management**, and **recency** alongside raw profit

## Scoring Formula

```
CompositeScore = Σ (wᵢ × normalize(metricᵢ))

Where:
  w₁ = 0.30  →  PnL (absolute profit)
  w₂ = 0.25  →  Win Rate (% of winning positions)
  w₃ = 0.20  →  Consistency (inverse of PnL variance)
  w₄ = 0.15  →  Volume-Adjusted ROI (PnL / Volume)
  w₅ = 0.10  →  Recency (time decay on older data)
```

### Normalization

All metrics are normalized using **z-score normalization** across the trader population:

```python
def z_score_normalize(value: float, mean: float, std: float) -> float:
    """Normalize a value to z-score, capped at [-3, 3]."""
    if std == 0:
        return 0
    z = (value - mean) / std
    return max(-3.0, min(3.0, z))  # Cap at ±3 std devs
```

### Metric Definitions

#### 1. PnL Score (w=0.30)
```
PnL_Score = z_normalize(trader_pnl, mean_pnl, std_pnl)
```
- Source: `leaderboard_snapshots.pnl` (period=ALL, category=OVERALL)
- Higher PnL = higher score

#### 2. Win Rate Score (w=0.25)
```
Win_Rate = closed_winning_positions / total_closed_positions
Win_Rate_Score = z_normalize(win_rate, mean_win_rate, std_win_rate)
```
- Minimum 50 closed positions required (otherwise score = 0)
- Source: Derived from `trader_positions` where status=CLOSED or SETTLED

#### 3. Consistency Score (w=0.20)
```
Daily_Returns = [daily PnL changes over last 30 days]
Consistency = 1 / (1 + std(Daily_Returns))
Consistency_Score = z_normalize(consistency, mean_consistency, std_consistency)
```
- Higher consistency (lower variance) = higher score
- Penalizes traders with wild swings, even if overall profitable
- Source: Derived from `leaderboard_snapshots` daily data

#### 4. Volume-Adjusted ROI (w=0.15)
```
ROI = PnL / Volume  (if Volume > 0, else 0)
ROI_Score = z_normalize(roi, mean_roi, std_roi)
```
- Rewards traders who make more profit per dollar traded
- Penalizes "churn" — high volume with low returns
- Source: `leaderboard_snapshots.pnl` / `leaderboard_snapshots.volume`

#### 5. Recency Score (w=0.10)
```
Days_Since_Last_Trade = (now - last_seen_at).days
Recency = exp(-0.05 * Days_Since_Last_Trade)  # Exponential decay
Recency_Score = recency  # Already 0-1 range
```
- Recent activity gets higher weight
- Traders inactive for 20+ days essentially get 0
- Source: `traders.last_seen_at`

## Eligibility Filters (Pre-Scoring)

Before a trader is even scored, they must pass these minimum filters.
**All thresholds are stored in `app_config` and adjustable at runtime — nothing is hardcoded.**

| Filter | Config Key | Default | Rationale |
|--------|-----------|---------|-----------|
| Min Total Trades | `min_trader_trades` | 50 | Statistical significance |
| Min Win Rate | `min_trader_win_rate` | 0.55 | Better than random |
| Active Recency | `active_recency_days` | 7 | Still active |
| Min PnL | `min_trader_pnl` | 0 | Must be profitable |
| Max Concentration | `max_concentration_pct` | 0.60 | Diversification |
| Min Liquidity | `min_market_liquidity_usdc` | 5000 | Executable |

Traders failing any filter get `composite_score = 0` and `is_watched = FALSE`.

## Score Decay

Scores decay over time if not refreshed:

```python
def apply_decay(score: float, hours_since_update: float) -> float:
    """Apply exponential decay to stale scores."""
    decay_rate = 0.01  # 1% per hour
    return score * math.exp(-decay_rate * hours_since_update)
```

This ensures the watchlist naturally rotates as traders become inactive.

## Watchlist Selection

After scoring all eligible traders:

1. Sort by `composite_score` descending
2. Take top N (configurable, default 10)
3. Ensure diversity: no more than 3 traders specializing in same category
4. Set `is_watched = TRUE` for selected traders
5. Set `is_watched = FALSE` for deselected traders
6. Notify via Telegram on watchlist changes

## Tuning & Backtesting

The weights (w₁ through w₅) are stored in `app_config` and can be tuned:

```json
{
  "scorer_weights": {
    "pnl": 0.30,
    "win_rate": 0.25,
    "consistency": 0.20,
    "volume": 0.15,
    "roi": 0.10
  }
}
```

Phase 3 backtesting module will:
1. Run the scorer against historical data
2. Simulate copy trading with the resulting watchlist
3. Measure portfolio returns
4. Optimize weights using grid search or Bayesian optimization

See [08-position-sizing.md](./08-position-sizing.md) for how composite scores translate into trade allocation amounts.

## Example Scoring Output

| Rank | Trader | PnL | Win Rate | Consistency | ROI | Recency | **Composite** |
|------|--------|-----|----------|-------------|-----|---------|---------------|
| 1 | WindWalk3 | 2.1 | 1.8 | 1.5 | 1.2 | 0.95 | **1.72** |
| 2 | Erasmus | 1.9 | 2.0 | 1.8 | 0.9 | 0.98 | **1.68** |
| 3 | tomatosauce | 1.5 | 1.6 | 2.2 | 1.4 | 0.90 | **1.61** |
| 4 | Bama124 | 2.3 | 1.2 | 0.8 | 0.7 | 0.85 | **1.38** |
| 5 | Beachboy4 | 3.0 | 0.5 | -1.0 | 0.3 | 0.95 | **0.98** |

Note how Beachboy4 ranks lower despite highest PnL — the low consistency (-1.0) and win rate (0.5) drag down their composite score. This is by design: we want *reliable* traders, not lucky ones.
