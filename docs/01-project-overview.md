# CopyPoly — Project Overview

## Mission Statement

**CopyPoly** is an automated copy-trading system for [Polymarket](https://polymarket.com), the world's largest prediction market. The system identifies the most profitable traders across multiple timeframes, analyzes their performance, and enables users to automatically replicate their positions.

## Problem Statement

Polymarket is a prediction market built on the Polygon blockchain where all trades are transparent and publicly accessible. While the platform provides basic leaderboards, there is no native copy-trading feature. Successful traders consistently outperform the market by leveraging domain expertise, information arbitrage, and sophisticated strategies.

**The opportunity:** By systematically identifying, ranking, and copying the top traders, we can:
- Reduce the research burden of individual market analysis
- Leverage the "wisdom of the best" rather than the crowd
- Automate position management and risk controls
- Build a data-driven edge in prediction markets

## Core Features

### 1. Trader Discovery & Ranking
- Fetch leaderboard data across multiple timeframes: **All-time, Monthly, Weekly, Daily, Hourly**
- Rank traders by: PnL, Win Rate, Volume, ROI, Consistency
- Filter by market category: Overall, Politics, Sports, Crypto, Culture, Weather, Economics, Tech

### 2. Trader Analysis & Scoring
- Build composite "trader score" based on weighted metrics
- Track performance trends over time (is a trader consistently good or just had one lucky bet?)
- Identify trading patterns and specializations
- Flag risk factors (concentrated bets, high variance, low liquidity markets)

### 3. Internal Database & Periodic Updates
- Store trader profiles, positions, and historical performance
- Configurable update frequency (real-time via WebSocket, or periodic polling)
- Track portfolio changes and new position entries
- Historical performance snapshots for backtesting

### 4. Copy Trading Engine
- Automated trade replication with configurable parameters
- Position sizing: fixed amount, proportional to trader, or Kelly criterion
- Risk management: max exposure, slippage protection, position limits
- Portfolio diversification across multiple top traders

### 5. Monitoring Dashboard
- Real-time portfolio overview
- Trader performance tracking
- P&L visualization
- Alert system for significant events

## Success Metrics

| Metric | Target |
|--------|--------|
| Top trader identification accuracy | Consistently identify traders with >55% win rate |
| Trade replication latency | < 30 seconds from detection to execution |
| Portfolio tracking uptime | 99%+ |
| Data freshness | Leaderboard updated at least every 5 minutes |
| Risk-adjusted returns | Positive Sharpe ratio over 30-day rolling window |

## Constraints & Risks

| Risk | Mitigation |
|------|------------|
| Alpha decay — Too many copiers erode trader edge | Limit number of traders copied simultaneously |
| Slippage — Price moves between detection and execution | Slippage tolerance thresholds, skip if too wide |
| API rate limits — Polymarket may throttle requests | Intelligent caching, exponential backoff |
| Regulatory — Prediction markets face legal uncertainty | Awareness only; not providing financial advice |
| Wallet security — Private key management | Environment variables, never log keys, hardware wallet support |
| Liquidity — Low liquidity in some markets can cause losses | Filter for minimum liquidity thresholds |

## Timeline

| Phase | Description | Duration |
|-------|-------------|----------|
| Phase 1 | Research & Documentation (current) | 1-2 days |
| Phase 2 | Data Collection Layer (leaderboard + profiles) | 3-5 days |
| Phase 3 | Trader Analysis & Scoring Engine | 3-5 days |
| Phase 4 | Copy Trading Engine (order execution) | 5-7 days |
| Phase 5 | Dashboard & Monitoring | 3-5 days |
| Phase 6 | Testing, Backtesting & Polish | 3-5 days |
