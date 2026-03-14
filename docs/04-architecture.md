# System Architecture

## High-Level Architecture

```
                          ┌──────────────────────────────┐
                          │     Polymarket Platform       │
                          │                               │
                          │  ┌────────┐ ┌──────┐ ┌────┐  │
                          │  │ Gamma  │ │ Data │ │CLOB│  │
                          │  │  API   │ │ API  │ │API │  │
                          │  └───┬────┘ └──┬───┘ └─┬──┘  │
                          │      │         │       │      │
                          │  ┌───┴─────────┴───────┴──┐  │
                          │  │    WebSocket Streams     │  │
                          │  └─────────────────────────┘  │
                          └──────────┬─────────┬──────────┘
                                     │         │
                    ╔════════════════╧═════════╧════════════════╗
                    ║            CopyPoly System                ║
                    ║                                           ║
          ┌─────────╨───────────┐                               ║
          │   Data Collection   │                               ║
          │      Layer          │                               ║
          │                     │                               ║
          │ ┌─────────────────┐ │    ┌───────────────────────┐  ║
          │ │  Leaderboard    │ │    │   Analysis Engine     │  ║
          │ │  Collector      │─┼───▶│                       │  ║
          │ │ (every 5 min)   │ │    │ ┌───────────────────┐ │  ║
          │ └─────────────────┘ │    │ │  Trader Scorer    │ │  ║
          │                     │    │ │  (composite rank) │ │  ║
          │ ┌─────────────────┐ │    │ └───────────────────┘ │  ║
          │ │  Position       │ │    │                       │  ║
          │ │  Monitor        │─┼───▶│ ┌───────────────────┐ │  ║
          │ │ (every 30 sec)  │ │    │ │  Performance      │ │  ║
          │ └─────────────────┘ │    │ │  Metrics          │ │  ║
          │                     │    │ └───────────────────┘ │  ║
          │ ┌─────────────────┐ │    │                       │  ║
          │ │  Market Data    │ │    │ ┌───────────────────┐ │  ║
          │ │  Syncer         │─┼───▶│ │  Filter Engine    │ │  ║
          │ │ (every 15 min)  │ │    │ │  (eligibility)    │ │  ║
          │ └─────────────────┘ │    │ └───────────────────┘ │  ║
          └─────────────────────┘    └───────────┬───────────┘  ║
                       │                         │              ║
                       ▼                         ▼              ║
          ┌─────────────────────────────────────────────────┐   ║
          │              PostgreSQL Database                 │   ║
          │                                                  │   ║
          │  ┌──────────┐ ┌──────────┐ ┌─────────────────┐  │   ║
          │  │ traders  │ │positions │ │ leaderboard_    │  │   ║
          │  │          │ │          │ │ snapshots       │  │   ║
          │  └──────────┘ └──────────┘ └─────────────────┘  │   ║
          │  ┌──────────┐ ┌──────────┐ ┌─────────────────┐  │   ║
          │  │ trades   │ │ markets  │ │ copy_orders     │  │   ║
          │  │          │ │          │ │                  │  │   ║
          │  └──────────┘ └──────────┘ └─────────────────┘  │   ║
          └──────────────────────┬──────────────────────────┘   ║
                                 │                              ║
                                 ▼                              ║
          ┌────────────────────────────────────────────────────────┐  ║
          │              Copy Trading Engine                        │  ║
          │                                                         │  ║
          │  ┌──────────┐ ┌───────────┐ ┌──────────┐ ┌──────────┐ │  ║
          │  │ Signal   │ │ Conflict  │ │ Risk     │ │ Order    │ │  ║
          │  │ Detector │─│ Resolver  │─│ Manager  │─│ Executor │─┼──╝
          │  │          │ │ (opposite │ │          │ │ or Paper │ │(CLOB API
          │  └──────────┘ │  bets)    │ └──────────┘ │ Logger   │ │ or log)
          │               └───────────┘              └──────────┘ │
          │                                                         │
          │  ┌──────────────────────────────────────────────────┐   │
          │  │  Position Sizer (score-based allocation engine)  │   │
          │  └──────────────────────────────────────────────────┘   │
          └──────────────────────────┬─────────────────────────────┘
                                     │
                                     ▼
          ┌──────────────────────────────────────────────────┐
          │            Monitoring & Alerts                    │
          │                                                   │
          │  ┌────────────┐  ┌────────────┐  ┌────────────┐  │
          │  │  React +   │  │  Telegram  │  │  Logging   │  │
          │  │  shadcn +  │  │  Notifier  │  │  (struct)  │  │
          │  │  TV Charts │  │            │  │            │  │
          │  └────────────┘  └────────────┘  └────────────┘  │
          └──────────────────────────────────────────────────┘
```

---

## Data Flow

### 1. Discovery Flow (Finding Top Traders)

```
                    Polymarket Data API
                          │
                   GET /v1/leaderboard
                  (DAY/WEEK/MONTH/ALL)
                  (OVERALL + categories)
                          │
                          ▼
              ┌──────────────────────┐
              │  Leaderboard         │
              │  Collector           │
              │                      │
              │  • Fetch all periods │
              │  • Deduplicate       │
              │  • Normalize data    │
              └──────────┬───────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │  Trader Scorer       │
              │                      │
              │  Composite Score =   │
              │  w₁ × PnL_norm    + │
              │  w₂ × WinRate     + │
              │  w₃ × Consistency + │
              │  w₄ × Volume_norm + │
              │  w₅ × ROI           │
              │                      │
              │  where weights are   │
              │  configurable        │
              └──────────┬───────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │  Filter Engine       │
              │                      │
              │  • Min PnL > $X      │
              │  • Win Rate > 55%    │
              │  • Min 50 trades     │
              │  • Active in last 7d │
              │  • Not concentrated  │
              │    on single market  │
              └──────────┬───────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │  "Watchlist"         │
              │  (top N traders      │
              │   to follow)         │
              └──────────────────────┘
```

### 2. Copy Trading Flow (Replicating Trades)

```
         Position Monitor (polling every 30s)
                         │
          For each trader in watchlist:
          GET /positions?user={wallet}
                         │
                         ▼
              ┌──────────────────────┐
              │  Signal Detector     │
              │                      │
              │  Compare current     │
              │  positions vs last   │
              │  known positions     │
              │                      │
              │  Detect:             │
              │  • NEW positions     │
              │  • INCREASED sizes   │
              │  • CLOSED positions  │
              │  • REDUCED sizes     │
              └──────────┬───────────┘
                         │
                    [New Signal]
                         │
                         ▼
              ┌──────────────────────┐
              │  Conflict Resolver   │
              │                      │
              │  Check if any other  │
              │  watched traders     │
              │  hold OPPOSITE side  │
              │  in the same market  │
              │                      │
              │  Resolution:         │
              │  NET SIGNAL approach │
              │  (consensus of all   │
              │   watched traders)   │
              │                      │
              │  If conflict:        │
              │  → Sum positions     │
              │  → Follow majority   │
              │  → Reduce size       │
              └──────────┬───────────┘
                         │
                    [Resolved Signal]
                         │
                         ▼
              ┌──────────────────────┐
              │  Position Sizer      │
              │                      │
              │  Score-based sizing:  │
              │  • Allocation % from │
              │    composite score   │
              │  • Confidence mult.  │
              │  • Risk adjustment   │
              │  • Max per-trader %  │
              │  • Cash reserve %    │
              └──────────┬───────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │  Risk Manager        │
              │                      │
              │  Checks:             │
              │  ✓ Max position size │
              │  ✓ Max total exposure│
              │  ✓ Market liquidity  │
              │  ✓ Slippage estimate │
              │  ✓ Portfolio balance │
              │  ✓ Daily loss limit  │
              └──────────┬───────────┘
                         │
                    [Approved]
                         │
                         ▼
              ┌──────────────────────┐
              │  Order Executor      │
              │  (or Paper Logger)   │
              │                      │
              │  Mode: PAPER / LIVE  │
              │                      │
              │  PAPER:              │
              │  • Log hypothetical  │
              │  • Record in DB      │
              │  • Track paper P&L   │
              │                      │
              │  LIVE:               │
              │  • Sign order        │
              │  • Submit to CLOB    │
              │  • Verify fill       │
              │  • Log result        │
              └──────────┬───────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │  Notifications       │
              │                      │
              │  📱 Telegram alert:  │
              │  "[PAPER] Copied     │
              │   @trader X BUY 10   │
              │   YES 'BTC > 100k?'  │
              │   @ $0.65"           │
              └──────────────────────┘
```

---

## Component Responsibilities

### Data Collection Layer

| Component | Frequency | Purpose |
|-----------|-----------|---------|
| **Leaderboard Collector** | Every 5 minutes | Fetch leaderboard across all periods and categories; upsert trader profiles |
| **Position Monitor** | Every 30 seconds | Check current positions of watched traders; detect changes |
| **Market Data Syncer** | Every 15 minutes | Update market metadata (questions, prices, liquidity, status) |

### Analysis Engine

| Component | Trigger | Purpose |
|-----------|---------|---------|
| **Trader Scorer** | After leaderboard update | Calculate composite score for all known traders |
| **Performance Metrics** | On demand / scheduled | Calculate win rate, ROI, Sharpe ratio, drawdown |
| **Filter Engine** | After scoring | Apply eligibility rules, update watchlist |

### Copy Trading Engine

| Component | Trigger | Purpose |
|-----------|---------|---------|
| **Signal Detector** | After position check | Compare snapshots, emit trade signals |
| **Conflict Resolver** | On new signal | Detect & resolve opposite bets via net signal consensus |
| **Position Sizer** | On resolved signal | Calculate allocation based on composite score |
| **Risk Manager** | On sized signal | Validate trade against risk rules |
| **Order Executor / Paper Logger** | On approved signal | Submit order to CLOB (live) or log hypothetical (paper) |

### Monitoring

| Component | Type | Purpose |
|-----------|------|---------|
| **React + shadcn + TradingView Dashboard** | Web SPA | Premium visual overview of portfolio, traders, P&L |
| **FastAPI** | JSON API | Backend data API consumed by React frontend |
| **Telegram Notifier** | Push | Real-time alerts for trades, errors, daily summaries |
| **Structured Logger** | File/stdout | Full audit trail of all system actions |

---

## Concurrency Model

```python
# Main event loop orchestration (simplified)
async def main():
    # Initialize
    db = await create_db_pool()
    polymarket = PolymarketClient()
    
    # Start background tasks
    tasks = [
        asyncio.create_task(leaderboard_collector(db, polymarket)),  # every 5 min
        asyncio.create_task(position_monitor(db, polymarket)),       # every 30 sec
        asyncio.create_task(market_syncer(db, polymarket)),          # every 15 min
        asyncio.create_task(dashboard_server(db)),                   # FastAPI
    ]
    
    await asyncio.gather(*tasks)
```

All IO-bound operations (API calls, DB queries, WebSocket reads) run concurrently using Python's `asyncio`, maximizing throughput without threads.

---

## Security Architecture

```
┌─────────────────────────────────────────┐
│         Environment Variables            │
│  (.env file, never committed to git)     │
│                                          │
│  POLYMARKET_PRIVATE_KEY=0x...           │
│  DATABASE_URL=postgresql://...          │
│  TELEGRAM_BOT_TOKEN=...                 │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│         Pydantic Settings                │
│  (validates + casts at startup)          │
│                                          │
│  class Settings(BaseSettings):           │
│    private_key: SecretStr               │
│    database_url: PostgresDsn            │
│                                          │
│  # SecretStr prevents logging keys      │
└─────────────────────────────────────────┘
```

**Key security measures:**
1. Private keys stored as `SecretStr` — prevents accidental logging
2. `.env` file in `.gitignore` — never committed
3. API credentials derived at runtime — not stored persistently
4. Signed orders — private key never sent over network
5. Position size limits — hardware enforcement of max risk
