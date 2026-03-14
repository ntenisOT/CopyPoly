# Implementation Plan

## Phase Overview

```
Phase 1 ──▶ Phase 2 ──▶ Phase 3 ───────────▶ Phase 4 ────────▶ Phase 5 ──▶ Phase 6
Research    Data         Analysis, Scoring    Copy Trading     Dashboard   Testing &
& Docs      Collection   & Backtesting        Engine           & Alerts    Polish
✅ DONE
1-2 days    3-5 days     3-5 days             5-7 days         3-5 days    3-5 days
```

> **All configuration values (thresholds, weights, intervals) are stored in `app_config`
> and are adjustable at runtime via the dashboard. Nothing is hardcoded.**

---

## Phase 1: Research & Documentation ✅ COMPLETE

### Deliverables
- [x] Project overview document
- [x] Polymarket API research
- [x] Technology decisions
- [x] Architecture design
- [x] Database schema
- [x] Implementation plan (this document)
- [x] Trader scoring algorithm
- [x] Position sizing algorithm

---

## Phase 2: Project Setup & Data Collection Layer

### 2.1 Project Bootstrapping

| Task | Description | Priority |
|------|-------------|----------|
| 2.1.1 | Initialize Python project with `uv` and `pyproject.toml` | 🔴 Critical |
| 2.1.2 | Set up project structure (src/copypoly/...) | 🔴 Critical |
| 2.1.3 | Create `Dockerfile`, `docker-compose.yml` (app + PostgreSQL + frontend) | 🔴 Critical |
| 2.1.4 | Configure Ruff, mypy, pre-commit | 🟡 High |
| 2.1.5 | Create `.env.example` and config module (Pydantic Settings) | 🔴 Critical |
| 2.1.6 | Set up structured logging with structlog | 🟡 High |
| 2.1.7 | Create Makefile with Docker shortcuts | 🟢 Medium |

### 2.2 Database Setup

| Task | Description | Priority |
|------|-------------|----------|
| 2.2.1 | Set up PostgreSQL database (use internal-postgresql-cache MCP or local) | 🔴 Critical |
| 2.2.2 | Create SQLAlchemy models matching schema | 🔴 Critical |
| 2.2.3 | Set up Alembic migrations | 🔴 Critical |
| 2.2.4 | Seed `app_config` table with defaults | 🟡 High |
| 2.2.5 | Create async session management | 🔴 Critical |

### 2.3 Polymarket API Clients

| Task | Description | Priority |
|------|-------------|----------|
| 2.3.1 | Create base HTTP client with retry logic (tenacity + httpx) | 🔴 Critical |
| 2.3.2 | Implement Gamma API client (market discovery) | 🟡 High |
| 2.3.3 | Implement Data API client (leaderboard + positions) | 🔴 Critical |
| 2.3.4 | Implement CLOB API client wrapper (read-only initially) | 🟡 High |
| 2.3.5 | Add comprehensive error handling and logging | 🟡 High |

### 2.4 Data Collectors

| Task | Description | Priority |
|------|-------------|----------|
| 2.4.1 | **Leaderboard Collector**: Fetch all periods × categories, upsert to DB | 🔴 Critical |
| 2.4.2 | **Market Syncer**: Fetch and cache market metadata | 🟡 High |
| 2.4.3 | **Position Tracker**: Poll positions for watched traders | 🔴 Critical |
| 2.4.4 | Set up APScheduler for periodic execution | 🔴 Critical |
| 2.4.5 | Add data quality checks (deduplication, validation) | 🟡 High |

### 2.5 Testing

| Task | Description | Priority |
|------|-------------|----------|
| 2.5.1 | Unit tests for API clients (mock responses) | 🟡 High |
| 2.5.2 | Integration tests for DB operations | 🟡 High |
| 2.5.3 | Manual validation: run collectors, verify data in DB | 🔴 Critical |

### Phase 2 Success Criteria
- ✅ Database populated with leaderboard data across all timeframes
- ✅ At least 100 traders profiled
- ✅ Market metadata cached for active markets
- ✅ Collectors running on schedule without errors
- ✅ Logs show clean operation over 1 hour

---

## Phase 3: Trader Analysis, Scoring & Backtesting

### 3.1 Performance Metrics

| Task | Description | Priority |
|------|-------------|----------|
| 3.1.1 | Calculate win rate from historical positions | 🔴 Critical |
| 3.1.2 | Calculate ROI (PnL / Volume) | 🔴 Critical |
| 3.1.3 | Calculate consistency score (std deviation of returns) | 🟡 High |
| 3.1.4 | Calculate active recency (days since last trade) | 🟡 High |
| 3.1.5 | Identify specializations from category performance | 🟢 Medium |

### 3.2 Composite Scorer

| Task | Description | Priority |
|------|-------------|----------|
| 3.2.1 | Implement weighted composite score formula | 🔴 Critical |
| 3.2.2 | Normalize metrics (z-score or min-max) | 🔴 Critical |
| 3.2.3 | All weights and thresholds configurable via `app_config` | 🔴 Critical |
| 3.2.4 | Store scores on `traders` table | 🔴 Critical |

### 3.3 Trader Filtering (All Thresholds Configurable)

| Task | Description | Priority |
|------|-------------|----------|
| 3.3.1 | Minimum PnL threshold filter (configurable, default >$0) | 🔴 Critical |
| 3.3.2 | Minimum win rate filter (configurable, default ≥55%) | 🔴 Critical |
| 3.3.3 | Minimum trade count filter (configurable, default ≥50) | 🔴 Critical |
| 3.3.4 | Recency filter (configurable, default 7 days) | 🟡 High |
| 3.3.5 | Concentration risk filter (configurable, default max 60%) | 🟡 High |
| 3.3.6 | Liquidity filter (configurable, default >$5K) | 🟡 High |

### 3.4 Watchlist Management

| Task | Description | Priority |
|------|-------------|----------|
| 3.4.1 | Auto-select top N traders as watchlist | 🔴 Critical |
| 3.4.2 | Manual override: add/remove traders | 🟡 High |
| 3.4.3 | Watchlist rotation logic (drop underperformers) | 🟢 Medium |

### 3.5 Backtesting Module

| Task | Description | Priority |
|------|-------------|----------|
| 3.5.1 | Historical data ingestion (Kaggle datasets + our snapshots) | 🟡 High |
| 3.5.2 | Backtest runner: "if we had copied top N from period X, what would P&L be?" | 🔴 Critical |
| 3.5.3 | Performance report generation (Sharpe, drawdown, win rate, ROI) | 🟡 High |
| 3.5.4 | Weight optimization: grid search over scorer weights | 🟢 Medium |

### Phase 3 Success Criteria
- ✅ All traders have composite scores
- ✅ Top 10 traders identified and match intuition (cross-reference with Polymarket leaderboard)
- ✅ Internal leaderboard ranking diverges meaningfully from Polymarket's (proves our value)
- ✅ Filtering rules correctly exclude low-quality traders (all filters configurable)
- ✅ Scoring updates run automatically after each leaderboard fetch
- ✅ Backtester validates positive expected returns on historical data

---

## Phase 4: Copy Trading Engine

> **Phase 4 always starts in PAPER MODE.** Live trading is a flag flip (`TRADING_MODE=paper|live`)
> that should only be enabled after validating paper results.

### 4.1 Signal Detection

| Task | Description | Priority |
|------|-------------|----------|
| 4.1.1 | Compare position snapshots to detect changes | 🔴 Critical |
| 4.1.2 | Generate signals: NEW, INCREASE, DECREASE, CLOSE | 🔴 Critical |
| 4.1.3 | Ignore noise (very small size changes, configurable threshold) | 🟡 High |
| 4.1.4 | Store signals in `copy_signals` table | 🔴 Critical |

### 4.2 Conflict Resolution (Opposite Bets)

| Task | Description | Priority |
|------|-------------|----------|
| 4.2.1 | Detect when watched traders hold opposite sides of the same market | 🔴 Critical |
| 4.2.2 | Implement **Net Signal / Consensus** resolution: sum all watched traders' positions in a market, follow the majority side | 🔴 Critical |
| 4.2.3 | Reduce position size proportionally when conflict exists | 🟡 High |
| 4.2.4 | Log all conflict resolutions with full detail | 🟡 High |

### 4.3 Position Sizing (Score-Based Allocation)

| Task | Description | Priority |
|------|-------------|----------|
| 4.3.1 | Implement score-based per-trader allocation (score / sum_of_scores) | 🔴 Critical |
| 4.3.2 | Confidence multiplier (composite_score / median_score) | 🟡 High |
| 4.3.3 | Risk adjustment for market liquidity | 🟡 High |
| 4.3.4 | Max per-trader allocation cap (configurable, default 25%) | 🔴 Critical |
| 4.3.5 | Max per-market allocation cap (configurable, default 15%) | 🟡 High |
| 4.3.6 | Cash reserve enforcement (configurable, default 20%) | 🔴 Critical |

### 4.4 Risk Management

| Task | Description | Priority |
|------|-------------|----------|
| 4.4.1 | Max single position size check | 🔴 Critical |
| 4.4.2 | Max total exposure check | 🔴 Critical |
| 4.4.3 | Market liquidity check (configurable min) | 🔴 Critical |
| 4.4.4 | Slippage estimation (compare book vs intended size) | 🟡 High |
| 4.4.5 | Portfolio diversity check | 🟡 High |
| 4.4.6 | Daily loss limit | 🟡 High |

### 4.5 Order Execution & Paper Trading

| Task | Description | Priority |
|------|-------------|----------|
| 4.5.1 | **Paper trading mode** — log hypothetical orders, track paper P&L (DEFAULT MODE) | 🔴 Critical |
| 4.5.2 | Set up authenticated CLOB client (for live mode) | 🔴 Critical |
| 4.5.3 | Implement market order execution (FOK) | 🔴 Critical |
| 4.5.4 | Implement limit order execution (GTC) | 🟢 Medium |
| 4.5.5 | Handle partial fills and retries | 🟡 High |
| 4.5.6 | Record all orders in `copy_orders` table (paper + live) | 🔴 Critical |
| 4.5.7 | Verify order fills (poll order status) | 🔴 Critical |

### 4.6 Position Management

| Task | Description | Priority |
|------|-------------|----------|
| 4.6.1 | Track our own positions vs copied trader positions | 🟡 High |
| 4.6.2 | Auto-exit when copied trader exits | 🔴 Critical |
| 4.6.3 | Handle market settlement (redemption) | 🟡 High |

### 4.7 Safety Features

| Task | Description | Priority |
|------|-------------|----------|
| 4.7.1 | Kill switch — immediately stop all copying | 🔴 Critical |
| 4.7.2 | Error rate circuit breaker | 🟡 High |
| 4.7.3 | Detailed audit log of all decisions | 🟡 High |
| 4.7.4 | `TRADING_MODE` env var: `paper` (default) or `live` | 🔴 Critical |

### Phase 4 Success Criteria
- ✅ Paper trading mode successfully simulates 24+ hours of copying
- ✅ Conflict resolution correctly handles opposite bets
- ✅ Position sizing allocates proportionally to composite scores
- ✅ All risk checks functioning correctly
- ✅ Kill switch tested and working
- ✅ Full audit trail in database and logs
- ✅ Paper P&L tracking matches expected outcomes

---

## Phase 5: Dashboard & Monitoring

### 5.1 FastAPI Backend API

| Task | Description | Priority |
|------|-------------|----------|
| 5.1.1 | `/api/traders` — List traders with scores, filterable | 🟡 High |
| 5.1.2 | `/api/traders/{wallet}` — Trader detail + history + positions | 🟡 High |
| 5.1.3 | `/api/watchlist` — Current watchlist with add/remove controls | 🟡 High |
| 5.1.4 | `/api/portfolio` — Portfolio overview + P&L time series | 🟡 High |
| 5.1.5 | `/api/signals` — Recent signals with outcomes | 🟡 High |
| 5.1.6 | `/api/config` — View/update runtime config (thresholds, weights) | 🟡 High |
| 5.1.7 | `/api/backtest` — Trigger and view backtest results | 🟢 Medium |

### 5.2 React Frontend (shadcn/ui + TradingView)

| Task | Description | Priority |
|------|-------------|----------|
| 5.2.1 | Scaffold React app (Vite + TypeScript + shadcn/ui) | 🔴 Critical |
| 5.2.2 | **Leaderboard page**: Our internal ranking (filterable by period/category) with comparison to Polymarket's | 🟡 High |
| 5.2.3 | **Trader detail page**: TradingView charts for P&L history, positions table, trade history | 🟡 High |
| 5.2.4 | **Portfolio overview**: TradingView chart for portfolio equity curve, open positions, P&L breakdown | 🟡 High |
| 5.2.5 | **Signal feed**: Live signal stream with conflict resolution annotations | 🟢 Medium |
| 5.2.6 | **Configuration panel**: Adjust all scoring weights, filters, risk params with live preview | 🟢 Medium |
| 5.2.7 | Dockerize frontend, add to `docker-compose.yml` | 🟡 High |

### 5.3 Telegram Notifications

| Task | Description | Priority |
|------|-------------|----------|
| 5.3.1 | Trade execution alerts (with [PAPER]/[LIVE] prefix) | 🟡 High |
| 5.3.2 | Error/warning alerts | 🟡 High |
| 5.3.3 | Daily performance summary | 🟢 Medium |
| 5.3.4 | Watchlist change notifications | 🟢 Medium |
| 5.3.5 | Conflict resolution notifications | 🟢 Medium |

### Phase 5 Success Criteria
- ✅ Dashboard accessible, responsive, and premium-looking (shadcn/ui)
- ✅ TradingView charts rendering trader P&L and portfolio equity curves
- ✅ Real-time data updates via API polling
- ✅ All config params adjustable from dashboard
- ✅ Telegram alerts received within 5 seconds of events
- ✅ Portfolio P&L matches actual Polymarket positions

---

## Phase 6: Testing, Hardening & Polish

### 6.1 Comprehensive Testing

| Task | Description | Priority |
|------|-------------|----------|
| 6.1.1 | End-to-end integration tests (full signal → order pipeline) | 🟡 High |
| 6.1.2 | Load testing (simulate high-frequency position updates) | 🟢 Medium |
| 6.1.3 | Error recovery tests (API downtime, DB connection loss) | 🟡 High |
| 6.1.4 | Security audit (key handling, env vars, Docker secrets) | 🟡 High |
| 6.1.5 | Conflict resolution edge case tests | 🟡 High |

### 6.2 Documentation & Deployment

| Task | Description | Priority |
|------|-------------|----------|
| 6.2.1 | README with Docker setup instructions | 🟡 High |
| 6.2.2 | Production deployment guide (docker-compose for VPS) | 🟢 Medium |
| 6.2.3 | API documentation (auto-generated from FastAPI) | 🟢 Medium |
| 6.2.4 | Runbook for common operations and troubleshooting | 🟢 Medium |

### Phase 6 Success Criteria
- ✅ All tests passing
- ✅ System runs stable for 48+ hours in paper mode
- ✅ Documentation complete for future development
- ✅ Docker deployment works cleanly on a fresh machine

---

## Immediate Next Steps (After This Document)

1. **Initialize the Python project** — `uv init`, `pyproject.toml`, directory structure
2. **Set up the database** — Create tables in PostgreSQL
3. **Build the leaderboard collector** — First data flowing into the system
4. **Validate data** — Confirm leaderboard data matches polymarket.com
5. **Begin scorer implementation** — Start ranking traders

---

## Risk Mitigation During Development

| Risk | Mitigation |
|------|------------|
| API changes | Pin SDK version; add response validation |
| Rate limiting | Start with conservative intervals; monitor response headers |
| Key security | Use `.env` from day 1; never commit keys |
| Data integrity | Deduplication constraints in DB; idempotent collectors |
| Scope creep | Stick to phase plan; defer nice-to-haves to Phase 6+ |
