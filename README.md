# CopyPoly

**Polymarket copy-trading intelligence platform** — discover, score, and copy the best prediction market traders using on-chain data.

CopyPoly crawls Polymarket's Goldsky subgraph (on-chain data, no rate limits) to build a comprehensive historical trade database, scores traders using a multi-dimensional algorithm, and provides a real-time dashboard for monitoring and backtesting.

---

## Features

- **Leaderboard Crawler** — Fetches top 1,000+ traders across all time periods (all/month/week/day)
- **5-Dimension Scoring Engine** — Ranks traders by PnL, win rate, consistency, volume, and ROI
- **Subgraph Historical Crawler** — Crawls every trade from Polymarket's on-chain data (160K+ events per top trader)
- **Page-by-Page Storage** — Immediately persists each page of 1,000 events; crash-safe, memory-efficient
- **Real-Time Dashboard** — FastAPI SPA with dark theme, TradingView charts, and 12 REST endpoints
- **Paper Trading Engine** — Simulated copy-trading with slippage modeling
- **Conflict Resolver** — NET SIGNAL approach when multiple traders take opposing positions
- **Position Sizer** — Score-based allocation with configurable risk limits
- **Auto-Watchlist** — Top-scored traders are automatically promoted to the watch list

---

## Quick Start

```bash
# 1. Clone and configure
git clone <repo-url>
cd copypoly
cp .env.example .env    # No secrets needed — subgraph is public

# 2. Start everything (PostgreSQL + migrations + app)
docker compose up --build -d

# 3. Verify it's running
docker compose logs -f app

# 4. Open the dashboard
open http://localhost:8000
```

### Data Collection

```bash
# Step 1: Collect traders from Polymarket leaderboard
curl -X POST http://localhost:8000/api/collect

# Step 2: Score all traders
curl -X POST http://localhost:8000/api/score

# Step 3: Crawl all trader history (incremental, 20 parallel workers)
curl -X POST http://localhost:8000/api/crawl \
  -H "Content-Type: application/json" \
  -d '{"max_workers": 20}'

# Step 4: Monitor progress
curl http://localhost:8000/api/crawl/progress

# Update existing data (fetches only new trades since last crawl)
curl -X POST http://localhost:8000/api/crawl

# Custom delta threshold (auto-resync traders with PnL delta > $500)
curl -X POST http://localhost:8000/api/crawl \
  -H "Content-Type: application/json" \
  -d '{"delta_threshold": 500}'

# Disable auto-resync (set threshold to 0)
curl -X POST http://localhost:8000/api/crawl \
  -H "Content-Type: application/json" \
  -d '{"delta_threshold": 0}'

# Wipe everything and re-crawl from scratch (DESTRUCTIVE)
curl -X POST http://localhost:8000/api/crawl \
  -H "Content-Type: application/json" \
  -d '{"mode": "resync"}'

# View crawl run history
curl http://localhost:8000/api/crawl/runs
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    CopyPoly                             │
├──────────┬──────────┬──────────┬────────────┬───────────┤
│  API     │ Collectors│ Analysis │  Engine    │ Dashboard │
│  Clients │          │          │            │           │
│          │ Leaderboard│ Scorer │ Signal     │ FastAPI   │
│ Data API │ Positions│ Watchlist│ Detection  │ REST API  │
│ Gamma API│ Markets  │ Backtest │ Execution  │ SPA UI    │
│ CLOB     │ History  │          │ Paper/Live │ Charts    │
│          │ Crawler  │          │            │           │
└────┬─────┴────┬─────┴────┬─────┴─────┬──────┴─────┬─────┘
     │          │          │           │            │
     ▼          ▼          ▼           ▼            ▼
┌─────────────────────────────────────────────────────────┐
│              PostgreSQL 18 (Dockerized)                 │
│                                                         │
│  traders │ leaderboard_snapshots │ trade_history         │
│  trader_positions │ crawl_progress │ app_config          │
│  copy_signals │ copy_orders │ portfolio_snapshots        │
└─────────────────────────────────────────────────────────┘
```

### Data Sources

| Source | Type | Purpose |
|--------|------|---------|
| [Polymarket Data API](https://data-api.polymarket.com) | REST | Leaderboard rankings, trader profiles |
| [Goldsky Orderbook Subgraph](https://api.goldsky.com) | GraphQL | Every on-chain trade fill (primary data source) |
| [Goldsky Activity Subgraph](https://api.goldsky.com) | GraphQL | Splits, merges, redemptions |
| [Goldsky OI Subgraph](https://api.goldsky.com) | GraphQL | Open interest per market |
| [Polymarket Gamma API](https://gamma-api.polymarket.com) | REST | Market names, conditions, metadata |

### Subgraph Advantage over API

| Factor | Data API | Goldsky Subgraph |
|--------|----------|------------------|
| Rate limiting | Cloudflare blocks at ~80% | **None** |
| Speed | ~1 trade/sec | **~1,000 events/sec** |
| Historical range | Limited | **Full on-chain history** |
| Reliability | 20% success for bulk crawls | **100% success rate** |
| Cost | Free | **Free** |

---

## Project Structure

```
copypoly/
├── src/copypoly/
│   ├── api/              # Polymarket API clients (Data, Gamma, CLOB)
│   ├── analysis/         # Scorer, backtester, watchlist, conflict resolver
│   ├── collectors/       # Leaderboard, positions, markets, history crawler
│   ├── dashboard/        # FastAPI REST API + SPA frontend
│   ├── db/               # SQLAlchemy models, session, migrations
│   ├── engine/           # Copy trading signal detection + execution
│   ├── config.py         # Pydantic settings (env-based config)
│   ├── logging.py        # structlog setup (JSON in Docker, pretty in TTY)
│   └── main.py           # Application entrypoint
├── alembic/              # Database migrations
├── docker-compose.yml    # Full stack: PostgreSQL + migrations + app
├── Dockerfile            # Multi-stage Python 3.13 image
└── .agents/              # AI agent knowledge, tasks, workflows
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/collect` | Trigger leaderboard collection (1,000+ traders) |
| `POST` | `/api/score` | Score and rank all traders |
| `POST` | `/api/crawl` | Crawl/update trade history (incremental by default) |
| `POST` | `/api/crawl` `{"mode":"resync"}` | Wipe DB + full re-crawl from scratch |
| `GET` | `/api/crawl/progress` | Monitor crawl progress (real-time) |
| `GET` | `/api/crawl/runs` | Crawl run history with verification summaries |
| `GET` | `/api/overview` | Dashboard summary stats |
| `GET` | `/api/traders` | List scored traders with rankings |
| `GET` | `/api/positions` | Current positions across watched traders |
| `GET` | `/api/signals` | Recent copy-trading signals |
| `POST` | `/api/backtest` | Run backtesting simulation |
| `GET` | `/api/config` | List all configuration values |
| `PUT` | `/api/config/{key}` | Update a configuration value |
| `GET` | `/api/performance` | Portfolio performance data |

---

## Scoring Algorithm

Each trader is scored on 5 dimensions (configurable weights):

| Dimension | Weight | Source |
|-----------|--------|--------|
| **PnL** | 30% | All-time profit/loss |
| **Win Rate** | 20% | From leaderboard profile |
| **Consistency** | 20% | Presence across time periods (all/month/week/day) |
| **Volume** | 10% | Total trading volume |
| **ROI** | 20% | PnL / Volume efficiency |

Scores are normalized to 0.0–1.0 using min-max scaling. All traders are scored (no PnL minimum filter) to catch rising stars and insider patterns.

---

## Configuration

All thresholds are runtime-configurable via the `app_config` database table:

```bash
# Update scoring weights
curl -X PUT http://localhost:8000/api/config/scoring_weights \
  -H "Content-Type: application/json" \
  -d '{"value": {"pnl": 0.25, "win_rate": 0.25, "consistency": 0.20, "volume": 0.10, "roi": 0.20}}'

# Update max watched traders
curl -X PUT http://localhost:8000/api/config/max_watched_traders \
  -d '{"value": 50}'
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | (required) | PostgreSQL connection string |
| `DISABLE_SCHEDULER` | `false` | Set to `true` for backfill-only mode |
| `TRADING_MODE` | `paper` | `paper` or `live` |
| `LOG_LEVEL` | `info` | Logging level |

---

## Docker Commands

```bash
# Restart (preserves data)
docker compose down && docker compose up --build -d

# Nuke & rebuild (DESTROYS ALL DATA)
docker compose down -v && docker compose up --build -d

# View logs
docker compose logs -f app

# DB shell
docker compose exec -e PAGER=cat db psql -U copypoly -d copypoly

# Backup database
docker compose exec db pg_dump -U copypoly copypoly > backup.sql

# Restore database
docker compose exec -T db psql -U copypoly copypoly < backup.sql
```

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Runtime | Python 3.13+ |
| Database | PostgreSQL 18 (Alpine, Dockerized) |
| ORM | SQLAlchemy 2.0 (async) |
| Migrations | Alembic |
| Web Framework | FastAPI + Uvicorn |
| HTTP Client | httpx (async) |
| Config | Pydantic Settings |
| Logging | structlog (JSON in Docker) |
| Package Manager | uv |
| Containerization | Docker Compose |

---

## Roadmap

See [`.agents/tasks/todo.md`](.agents/tasks/todo.md) for the full task tracker.

### Current Phase: 7 — Historical Data Lake

- [x] Phase 2: Foundation & Infrastructure
- [x] Phase 3: Analysis & Backtesting
- [x] Phase 4: Copy Trading Engine (paper mode)
- [x] Phase 5: Dashboard
- [ ] Phase 6: Testing & CI/CD
- [ ] **Phase 7: Historical Data Lake** ← current
  - [x] 7.1 Subgraph trade history crawler (20 parallel workers)
  - [x] 7.2 Activity data (splits/merges/redemptions)
  - [x] 7.3 Per-market PnL verification (22/22 Theo4, 50/50 Fredi9999)
  - [x] 7.4 Incremental updates (timestamp-based, 5-day safety buffer)
  - [x] 7.5 Auto-retry failed traders (2 rounds)
  - [ ] 7.6 Market context (OI + volume)
  - [ ] 7.7 Backtesting engine
  - [ ] 7.8 Advanced analysis (insider detection, rising stars)

---

## License

MIT
