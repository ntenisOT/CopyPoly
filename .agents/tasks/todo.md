# CopyPoly — Task Tracker

## Phase 2: Foundation & Infrastructure

- [x] 2.1 Project structure (pyproject.toml, Dockerfile, docker-compose)
- [x] 2.2 Database schema & migrations (Alembic, 9 tables, seed data)
- [x] 2.2.1 Git repo setup (SSH key, remote, initial commit)
- [x] 2.2.2 AI agent rules & workflows
- [x] 2.3 Polymarket API clients (Data API, Gamma API, CLOB client)
- [x] 2.4 Data collectors (leaderboard, positions, markets)

## Phase 3: Analysis & Backtesting

- [x] 3.1 Trader scoring engine (5-dimension weighted composite score)
- [x] 3.2 Backtesting module (historical trade replay with slippage simulation)
- [x] 3.3 Conflict resolver (NET SIGNAL approach)
- [x] 3.4 Position sizer (score-based allocation with risk limits)
- [x] 3.5 Watchlist manager (auto-promotes top scorers)

## Phase 4: Copy Trading Engine

- [x] 4.1 Signal detection (position diffing — NEW/ADD/REDUCE/CLOSE)
- [x] 4.2 Position sizing algorithm (integrated into engine)
- [x] 4.3 Paper trading execution (PaperExecutor with slippage sim)
- [ ] 4.4 Live trading execution (CLOB API — stubbed, needs wallet setup)

## Phase 5: Dashboard

- [x] 5.1 FastAPI REST API (12 endpoints: overview, traders, positions, signals, config CRUD, backtest trigger)
- [x] 5.2 SPA Frontend (dark theme, 6 pages: overview, traders, positions, signals, backtest, settings)
- [x] 5.3 TradingView charts (Lightweight Charts: equity curve + drawdown + trade markers, simulated data fallback)

## Phase 6: Testing & Deployment

- [ ] 6.1 Unit & integration tests
- [ ] 6.2 CI/CD pipeline
- [ ] 6.3 Monitoring & alerts

## Phase 7: Historical Data Lake & Advanced Analysis

> Data source: Polymarket Goldsky subgraphs (on-chain, free, no rate limits)

### 7.1 Trade History (orderbook-subgraph)
- [x] 7.1.1 Rewrite crawler to use Goldsky subgraph (replaced unreliable Data API)
- [x] 7.1.2 Page-by-page storage (not memory-accumulate) with per-page logging
- [x] 7.1.3 Retry logic for subgraph timeouts + proper error handling
- [x] 7.1.4 Fix position upsert race condition (positions.py)
- [ ] 7.1.5 Complete initial crawl of top 50 traders (~2M events)
- [ ] 7.1.6 Enrich trades with market names (MarketData entity + Gamma API)
- [ ] 7.1.7 Daily incremental update (crawl only new events since last timestamp)

### 7.2 Activity Data (activity-subgraph)
- [ ] 7.2.1 Crawl Split events per trader (position entry via USDC → tokens)
- [ ] 7.2.2 Crawl Merge events per trader (position exit via tokens → USDC)
- [ ] 7.2.3 Crawl Redemption events per trader (market resolution payouts)
- [ ] 7.2.4 Store as trade_history rows with trade_type = SPLIT/MERGE/REDEEM

### 7.3 Market Context (oi-subgraph + orderbook)
- [ ] 7.3.1 Crawl Orderbook for per-market volume stats
- [ ] 7.3.2 Crawl MarketOpenInterest for market OI
- [ ] 7.3.3 Store in market_stats table

### 7.4 Computed PnL (derived from 7.1 + 7.2 data)
- [ ] 7.4.1 Calculate entry cost (USDC spent on buys)
- [ ] 7.4.2 Calculate exit proceeds (sells + redemptions)
- [ ] 7.4.3 Per-market and aggregate PnL per trader
- [ ] 7.4.4 Store in trader_pnl materialized view

### 7.5 Backtesting Engine
- [ ] 7.5.1 "Copy trader X" simulation (replay trades chronologically)
- [ ] 7.5.2 Performance metrics (win rate, Sharpe, max drawdown, ROI)
- [ ] 7.5.3 Comparison: simulated vs actual returns

### 7.6 Advanced Analysis
- [ ] 7.6.1 Rising star detection (improving win rate over time)
- [ ] 7.6.2 Insider pattern detection (trades before major price moves)
- [ ] 7.6.3 Correlation analysis (which traders trade similar markets)
- [ ] 7.6.4 Market timing analysis (OI + trade timing)

