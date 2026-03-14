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
- [ ] 5.3 TradingView charts (deferred — needs more time-series data)

## Phase 6: Testing & Deployment

- [ ] 6.1 Unit & integration tests
- [ ] 6.2 CI/CD pipeline
- [ ] 6.3 Monitoring & alerts

## Phase 7: Historical Data Lake & Advanced Analysis

- [ ] 7.1 Full trade history crawler (all leaderboard traders → local DB)
- [ ] 7.2 Rising star detector (new traders with sudden high win rates)
- [ ] 7.3 Insider pattern detector (traders who enter before big moves)
- [ ] 7.4 Seasonal/category pattern analysis
- [ ] 7.5 Comprehensive offline backtester (all traders, all periods)
