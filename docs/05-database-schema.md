# Database Schema

## Overview

The database schema is designed to capture the full lifecycle of trader discovery, analysis, and copy trading. It uses PostgreSQL for its strong JSON support, window functions for analytics, and robust indexing for time-series queries.

---

## Entity Relationship Diagram

```
┌──────────────────┐       ┌──────────────────────┐
│     traders      │       │  leaderboard_        │
│                  │ 1───N │  snapshots            │
│  wallet (PK)     │───────│                       │
│  username        │       │  trader_wallet (FK)   │
│  profile_image   │       │  period               │
│  x_username      │       │  category             │
│  first_seen      │       │  rank                 │
│  last_seen       │       │  pnl                  │
│  composite_score │       │  volume               │
│  is_watched      │       │  captured_at          │
└────────┬─────────┘       └──────────────────────┘
         │
         │ 1
         │
         │ N
┌────────┴─────────┐       ┌──────────────────────┐
│  trader_         │       │     markets           │
│  positions       │ N───1 │                       │
│                  │───────│  condition_id (PK)    │
│  id (PK)         │       │  question             │
│  trader_wallet   │       │  slug                 │
│  condition_id    │       │  category             │
│  token_id        │       │  outcomes             │
│  outcome         │       │  current_prices       │
│  size            │       │  volume               │
│  avg_price       │       │  liquidity            │
│  current_value   │       │  active               │
│  detected_at     │       │  settled              │
│  status          │       │  end_date             │
└──────────────────┘       └──────────────────────┘
         │
         │ triggers
         │
         ▼
┌──────────────────┐       ┌──────────────────────┐
│  copy_signals    │       │  copy_orders          │
│                  │ 1───N │                       │
│  id (PK)         │───────│  id (PK)              │
│  trader_wallet   │       │  signal_id (FK)       │
│  signal_type     │       │  order_type           │
│  condition_id    │       │  token_id             │
│  token_id        │       │  side                 │
│  detail (JSON)   │       │  size                 │
│  status          │       │  price                │
│  created_at      │       │  slippage             │
│  processed_at    │       │  status               │
└──────────────────┘       │  polymarket_order_id  │
                           │  fill_price           │
                           │  fill_size            │
                           │  error_message        │
                           │  created_at           │
                           │  executed_at          │
                           └──────────────────────┘

┌──────────────────┐
│  portfolio_      │
│  snapshots       │
│                  │
│  id (PK)         │
│  total_value     │
│  total_pnl       │
│  num_positions   │
│  captured_at     │
└──────────────────┘
```

---

## Table Definitions

### 1. `traders` — Known Trader Profiles

```sql
CREATE TABLE traders (
    wallet              VARCHAR(42) PRIMARY KEY,  -- Ethereum address
    username            VARCHAR(100),
    profile_image       TEXT,
    x_username          VARCHAR(50),
    
    -- Computed scores (updated by analysis engine)
    composite_score     DECIMAL(10,4) DEFAULT 0,
    best_pnl_all_time   DECIMAL(18,2) DEFAULT 0,
    best_pnl_monthly    DECIMAL(18,2) DEFAULT 0,
    best_pnl_weekly     DECIMAL(18,2) DEFAULT 0,
    best_pnl_daily      DECIMAL(18,2) DEFAULT 0,
    win_rate            DECIMAL(5,4),             -- 0.0000 to 1.0000
    total_trades        INTEGER DEFAULT 0,
    
    -- Tracking
    is_watched          BOOLEAN DEFAULT FALSE,    -- Are we actively copying?
    watch_started_at    TIMESTAMPTZ,
    specializations     JSONB DEFAULT '[]',        -- e.g., ["POLITICS", "CRYPTO"]
    
    -- Metadata
    first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_scored_at      TIMESTAMPTZ,
    
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_traders_composite_score ON traders(composite_score DESC);
CREATE INDEX idx_traders_is_watched ON traders(is_watched) WHERE is_watched = TRUE;
CREATE INDEX idx_traders_last_seen ON traders(last_seen_at);
```

### 2. `leaderboard_snapshots` — Historical Leaderboard Data

```sql
CREATE TABLE leaderboard_snapshots (
    id                  BIGSERIAL PRIMARY KEY,
    trader_wallet       VARCHAR(42) NOT NULL REFERENCES traders(wallet),
    
    -- Leaderboard dimensions
    period              VARCHAR(10) NOT NULL,      -- DAY, WEEK, MONTH, ALL
    category            VARCHAR(20) NOT NULL,      -- OVERALL, POLITICS, SPORTS, etc.
    
    -- Ranking data
    rank                INTEGER NOT NULL,
    pnl                 DECIMAL(18,2) NOT NULL,
    volume              DECIMAL(18,2) NOT NULL,
    
    -- Snapshot time
    captured_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    CONSTRAINT uq_leaderboard_snapshot 
        UNIQUE(trader_wallet, period, category, captured_at)
);

CREATE INDEX idx_lb_trader_period ON leaderboard_snapshots(trader_wallet, period, category);
CREATE INDEX idx_lb_captured_at ON leaderboard_snapshots(captured_at);
CREATE INDEX idx_lb_pnl ON leaderboard_snapshots(pnl DESC);
```

### 3. `markets` — Polymarket Market Metadata

```sql
CREATE TABLE markets (
    condition_id        VARCHAR(66) PRIMARY KEY,   -- On-chain condition ID
    question            TEXT NOT NULL,
    slug                VARCHAR(200),
    category            VARCHAR(50),
    
    -- Market structure
    outcomes            JSONB NOT NULL,            -- ["Yes", "No"] or more
    token_ids           JSONB NOT NULL,            -- {"Yes": "abc...", "No": "def..."}
    
    -- Current state
    current_prices      JSONB,                     -- {"Yes": 0.65, "No": 0.35}
    volume              DECIMAL(18,2) DEFAULT 0,
    liquidity           DECIMAL(18,2) DEFAULT 0,
    
    -- Status
    active              BOOLEAN DEFAULT TRUE,
    settled             BOOLEAN DEFAULT FALSE,
    winning_outcome     VARCHAR(50),
    
    -- Dates
    start_date          TIMESTAMPTZ,
    end_date            TIMESTAMPTZ,
    
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_markets_category ON markets(category);
CREATE INDEX idx_markets_active ON markets(active) WHERE active = TRUE;
CREATE INDEX idx_markets_liquidity ON markets(liquidity DESC);
```

### 4. `trader_positions` — Current & Historical Positions

```sql
CREATE TABLE trader_positions (
    id                  BIGSERIAL PRIMARY KEY,
    trader_wallet       VARCHAR(42) NOT NULL REFERENCES traders(wallet),
    condition_id        VARCHAR(66) NOT NULL REFERENCES markets(condition_id),
    token_id            VARCHAR(66) NOT NULL,
    outcome             VARCHAR(50) NOT NULL,      -- "Yes" or "No"
    
    -- Position data
    size                DECIMAL(18,6) NOT NULL,    -- Number of shares
    avg_entry_price     DECIMAL(10,6),
    current_value       DECIMAL(18,2),
    unrealized_pnl      DECIMAL(18,2),
    
    -- Status
    status              VARCHAR(20) NOT NULL DEFAULT 'OPEN',  -- OPEN, CLOSED, SETTLED
    
    -- Tracking
    first_detected_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at           TIMESTAMPTZ,
    
    CONSTRAINT uq_trader_position 
        UNIQUE(trader_wallet, token_id, status)
);

CREATE INDEX idx_positions_trader ON trader_positions(trader_wallet);
CREATE INDEX idx_positions_status ON trader_positions(status);
CREATE INDEX idx_positions_market ON trader_positions(condition_id);
CREATE INDEX idx_positions_detected ON trader_positions(first_detected_at);
```

### 5. `position_snapshots` — Position History for Analysis

```sql
CREATE TABLE position_snapshots (
    id                  BIGSERIAL PRIMARY KEY,
    position_id         BIGINT NOT NULL REFERENCES trader_positions(id),
    trader_wallet       VARCHAR(42) NOT NULL,
    token_id            VARCHAR(66) NOT NULL,
    
    size                DECIMAL(18,6) NOT NULL,
    current_price       DECIMAL(10,6),
    current_value       DECIMAL(18,2),
    
    captured_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_pos_snap_position ON position_snapshots(position_id);
CREATE INDEX idx_pos_snap_time ON position_snapshots(captured_at);
```

### 6. `copy_signals` — Detected Trading Signals

```sql
CREATE TABLE copy_signals (
    id                  BIGSERIAL PRIMARY KEY,
    trader_wallet       VARCHAR(42) NOT NULL REFERENCES traders(wallet),
    
    -- Signal details
    signal_type         VARCHAR(20) NOT NULL,      -- NEW_POSITION, INCREASE, DECREASE, CLOSE
    condition_id        VARCHAR(66) NOT NULL,
    token_id            VARCHAR(66) NOT NULL,
    outcome             VARCHAR(50) NOT NULL,
    
    -- Change details
    previous_size       DECIMAL(18,6) DEFAULT 0,
    new_size            DECIMAL(18,6) NOT NULL,
    size_change         DECIMAL(18,6) NOT NULL,    -- positive = buy, negative = sell
    
    -- Market context at signal time
    market_price        DECIMAL(10,6),
    market_liquidity    DECIMAL(18,2),
    
    -- Processing
    status              VARCHAR(20) NOT NULL DEFAULT 'PENDING',  -- PENDING, APPROVED, REJECTED, EXECUTED, FAILED
    reject_reason       TEXT,
    
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at        TIMESTAMPTZ
);

CREATE INDEX idx_signals_status ON copy_signals(status);
CREATE INDEX idx_signals_trader ON copy_signals(trader_wallet);
CREATE INDEX idx_signals_created ON copy_signals(created_at);
```

### 7. `copy_orders` — Executed Copy Orders

```sql
CREATE TABLE copy_orders (
    id                  BIGSERIAL PRIMARY KEY,
    signal_id           BIGINT NOT NULL REFERENCES copy_signals(id),
    
    -- Order details
    order_type          VARCHAR(10) NOT NULL,      -- MARKET, LIMIT
    token_id            VARCHAR(66) NOT NULL,
    side                VARCHAR(4) NOT NULL,       -- BUY, SELL
    requested_size      DECIMAL(18,6) NOT NULL,
    requested_price     DECIMAL(10,6),
    
    -- Execution results
    polymarket_order_id VARCHAR(100),
    fill_price          DECIMAL(10,6),
    fill_size           DECIMAL(18,6),
    slippage_bps        DECIMAL(8,2),              -- Basis points of slippage
    usdc_spent          DECIMAL(18,2),
    
    -- Status
    status              VARCHAR(20) NOT NULL DEFAULT 'PENDING',  -- PENDING, SUBMITTED, FILLED, PARTIAL, FAILED, CANCELLED
    error_message       TEXT,
    
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    submitted_at        TIMESTAMPTZ,
    executed_at         TIMESTAMPTZ
);

CREATE INDEX idx_orders_signal ON copy_orders(signal_id);
CREATE INDEX idx_orders_status ON copy_orders(status);
CREATE INDEX idx_orders_created ON copy_orders(created_at);
```

### 8. `portfolio_snapshots` — Our Portfolio Over Time

```sql
CREATE TABLE portfolio_snapshots (
    id                  BIGSERIAL PRIMARY KEY,
    
    -- Portfolio state
    total_value_usdc    DECIMAL(18,2) NOT NULL,
    total_invested      DECIMAL(18,2) NOT NULL,
    total_pnl           DECIMAL(18,2) NOT NULL,
    unrealized_pnl      DECIMAL(18,2) NOT NULL,
    realized_pnl        DECIMAL(18,2) NOT NULL,
    
    -- Positions
    num_open_positions  INTEGER NOT NULL,
    num_traders_copied  INTEGER NOT NULL,
    
    -- Risk metrics
    max_single_exposure DECIMAL(18,2),
    portfolio_diversity DECIMAL(5,4),              -- 0-1, higher = more diverse
    
    captured_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_portfolio_time ON portfolio_snapshots(captured_at);
```

### 9. `app_config` — Runtime Configuration

```sql
CREATE TABLE app_config (
    key                 VARCHAR(100) PRIMARY KEY,
    value               JSONB NOT NULL,
    description         TEXT,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Seed with defaults
INSERT INTO app_config (key, value, description) VALUES
    -- Trader Filtering
    ('min_trader_win_rate', '0.55', 'Minimum win rate for trader eligibility'),
    ('min_trader_trades', '50', 'Minimum total trades for eligibility'),
    ('min_trader_pnl', '0', 'Minimum PnL for eligibility'),
    ('active_recency_days', '7', 'Trader must have been active within N days'),
    ('max_concentration_pct', '0.60', 'Max % of PnL from a single market'),
    ('min_market_liquidity_usdc', '5000', 'Minimum market liquidity to trade'),
    
    -- Scoring
    ('scorer_weights', '{"pnl": 0.3, "win_rate": 0.25, "consistency": 0.2, "volume": 0.15, "roi": 0.1}', 'Weights for composite trader scoring'),
    ('max_traders_to_watch', '10', 'Maximum number of traders to actively copy'),
    
    -- Position Sizing
    ('position_sizing', '{"cash_reserve_pct": 0.20, "max_per_trader_allocation": 0.25, "max_per_market_allocation": 0.15, "max_single_position_usdc": 200, "max_market_impact_pct": 0.02, "min_consensus_threshold": 0.30, "min_trade_size_usdc": 5.0}', 'Position sizing configuration'),
    
    -- Risk Management
    ('max_total_exposure_usdc', '1000', 'Maximum total portfolio exposure'),
    ('slippage_tolerance_bps', '200', 'Max slippage in basis points (2%)'),
    ('daily_loss_limit_usdc', '100', 'Stop copying if daily loss exceeds this'),
    
    -- Trading Mode
    ('trading_mode', '"paper"', 'Trading mode: "paper" or "live"'),
    
    -- Polling Intervals
    ('leaderboard_update_interval_minutes', '5', 'How often to fetch leaderboard data'),
    ('position_check_interval_seconds', '30', 'How often to check watched trader positions'),
    ('market_sync_interval_minutes', '15', 'How often to refresh market metadata');
```

---

## Key Queries (Examples)

### Top 10 Traders by Composite Score
```sql
SELECT wallet, username, composite_score, best_pnl_all_time,
       win_rate, total_trades, specializations
FROM traders
WHERE composite_score > 0
  AND total_trades >= 50
  AND last_seen_at > NOW() - INTERVAL '7 days'
ORDER BY composite_score DESC
LIMIT 10;
```

### Trader Performance Trend (Last 30 Days)
```sql
SELECT DATE_TRUNC('day', captured_at) AS day,
       AVG(rank) AS avg_rank,
       MAX(pnl) AS peak_pnl,
       COUNT(*) AS observations
FROM leaderboard_snapshots
WHERE trader_wallet = '0x...'
  AND period = 'ALL'
  AND category = 'OVERALL'
  AND captured_at > NOW() - INTERVAL '30 days'
GROUP BY DATE_TRUNC('day', captured_at)
ORDER BY day;
```

### Recent Copy Signals with Outcomes
```sql
SELECT cs.signal_type, cs.outcome, cs.size_change,
       m.question, cs.market_price,
       co.fill_price, co.slippage_bps, co.status,
       t.username
FROM copy_signals cs
JOIN markets m ON cs.condition_id = m.condition_id
JOIN traders t ON cs.trader_wallet = t.wallet
LEFT JOIN copy_orders co ON co.signal_id = cs.id
ORDER BY cs.created_at DESC
LIMIT 20;
```

### Portfolio P&L Over Time
```sql
SELECT captured_at,
       total_value_usdc,
       total_pnl,
       realized_pnl,
       unrealized_pnl,
       num_open_positions
FROM portfolio_snapshots
ORDER BY captured_at
LIMIT 1000;
```

---

## Migration Strategy

We'll use **Alembic** for database migrations:

```bash
# Initialize (one-time)
alembic init src/copypoly/db/migrations

# Create migration
alembic revision --autogenerate -m "initial_schema"

# Apply migration
alembic upgrade head

# Rollback
alembic downgrade -1
```
