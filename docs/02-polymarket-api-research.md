# Polymarket API Research

## API Architecture Overview

Polymarket exposes **three main APIs** plus **WebSocket streams** for real-time data:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Polymarket API Ecosystem                      │
├─────────────────┬──────────────────┬────────────────────────────┤
│   Gamma API     │    Data API      │       CLOB API             │
│ (Market Data)   │ (User/Trader)    │ (Trading/Orderbook)        │
├─────────────────┼──────────────────┼────────────────────────────┤
│ gamma-api.      │ data-api.        │ clob.                      │
│ polymarket.com  │ polymarket.com   │ polymarket.com             │
├─────────────────┼──────────────────┼────────────────────────────┤
│ • Markets       │ • Leaderboard    │ • Order book               │
│ • Events        │ • Positions      │ • Prices/Midpoints         │
│ • Tags          │ • Trades         │ • Order placement          │
│ • Categories    │ • Activity       │ • Order management         │
│ • Volume        │ • Profiles       │ • Token allowances         │
│ • Liquidity     │ • Holdings       │ • Market/Limit orders      │
├─────────────────┼──────────────────┼────────────────────────────┤
│ Auth: NONE      │ Auth: MIXED      │ Auth: REQUIRED (trading)   │
│ (public/read)   │ (some public)    │ (read-only = no auth)      │
└─────────────────┴──────────────────┴────────────────────────────┘

                    WebSocket Streams
┌─────────────────────────────────────────────────────────────────┐
│ wss://ws-subscriptions-clob.polymarket.com/ws/                  │
│   → Market: order book changes, prices, best bid/ask            │
│   → User: order fills, cancellations (auth required)            │
│                                                                  │
│ wss://ws-live-data.polymarket.com                                │
│   → Live crypto prices, market comment streams                   │
│                                                                  │
│ wss://sports-api.polymarket.com/ws                               │
│   → Live game scores, periods, status                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## 1. Gamma API — Market Discovery

**Base URL:** `https://gamma-api.polymarket.com`  
**Auth:** None required (fully public)

### Key Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/markets` | GET | List/search all markets |
| `/events` | GET | List events (an event can have multiple markets) |
| `/markets/{id}` | GET | Get specific market details |
| `/public-search` | GET | Search across events, markets, and profiles |

### Market Object (Key Fields)
```json
{
  "id": "string",
  "question": "Will Bitcoin exceed $100K by June 2026?",
  "slug": "will-bitcoin-exceed-100k",
  "outcomes": ["Yes", "No"],
  "outcomePrices": ["0.65", "0.35"],
  "volume": "1500000",
  "liquidity": "250000",
  "startDate": "2026-01-01",
  "endDate": "2026-06-30",
  "active": true,
  "closed": false,
  "category": "CRYPTO",
  "conditionId": "0x...",
  "tokens": [
    { "token_id": "abc123", "outcome": "Yes" },
    { "token_id": "def456", "outcome": "No" }
  ]
}
```

### Use Cases for CopyPoly
- **Market discovery**: Find which markets top traders are active in
- **Market metadata**: Resolve token IDs to human-readable questions
- **Liquidity checks**: Filter markets by liquidity before copying trades
- **Category mapping**: Classify trader specializations

---

## 2. Data API — Trader & Leaderboard Data ⭐ (MOST CRITICAL)

**Base URL:** `https://data-api.polymarket.com`  
**Auth:** Mixed (leaderboard is public, some user-specific endpoints may require auth)

### Leaderboard Endpoint

```
GET /v1/leaderboard
```

**Query Parameters:**

| Parameter | Values | Description |
|-----------|--------|-------------|
| `period` | `DAY`, `WEEK`, `MONTH`, `ALL` | Time period filter |
| `category` | `OVERALL`, `POLITICS`, `SPORTS`, `CRYPTO`, `CULTURE`, `MENTIONS`, `WEATHER`, `ECONOMICS`, `TECH` | Category filter |
| `orderBy` | `PNL`, `VOL` | Sort order |
| `limit` | integer | Number of results (pagination) |
| `offset` | integer | Pagination offset |
| `user` | wallet address | Filter by specific wallet |
| `userName` | string | Filter by username |

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `rank` | int | Leaderboard position |
| `proxyWallet` | string | Wallet address |
| `userName` | string | Display name |
| `vol` | float | Trading volume |
| `pnl` | float | Profit & Loss |
| `profileImage` | string | Avatar URL |
| `xUsername` | string | Twitter/X handle |

### Positions Endpoint

```
GET /positions
```

Query by wallet address to get a user's current holdings across markets.

**Key fields returned:**
- Token ID held
- Number of shares (Yes/No)
- Current valuation
- Entry price

### Trades Endpoint

```
GET /trades
```

Returns historical trade data for a user or market.

### Activity Endpoint

```
GET /activity
```

On-chain activity: liquidity provision, redemptions, splits, merges.

### Closed Positions

```
GET /closed-positions
```

Historical positions that have been resolved.

### Use Cases for CopyPoly
- **Leaderboard scraping**: Primary source for identifying top traders
- **Position tracking**: Monitor what top traders currently hold
- **Trade history**: Analyze trading patterns, frequency, sizing
- **Performance calculation**: Derive win rate, ROI, consistency metrics

---

## 3. CLOB API — Trading & Order Execution

**Base URL:** `https://clob.polymarket.com`  
**Auth:** Required for trading operations; read-only endpoints are public

### Read-Only Endpoints (No Auth)

| Endpoint | Description |
|----------|-------------|
| `GET /midpoint` | Current midpoint price for a token |
| `GET /price` | Current price (buy/sell side) |
| `GET /order-book` | Full order book snapshot |
| `GET /order-books` | Batch order book queries |

### Trading Endpoints (Auth Required)

| Endpoint | Description |
|----------|-------------|
| `POST /order` | Submit a new order (market or limit) |
| `DELETE /order/{id}` | Cancel an order |
| `GET /orders` | List user's open orders |
| `POST /cancel-all` | Cancel all open orders |

### Order Types

| Type | Description |
|------|-------------|
| `GTC` | Good Till Cancel — stays in book until filled |
| `FOK` | Fill or Kill — fill immediately or cancel entire order |
| `GTD` | Good Till Date — expires at specified time |

### Authentication Flow
1. Generate API key from private key using `create_or_derive_api_creds()`
2. Sign orders with private key
3. Submit signed orders via REST API
4. All on Polygon chain (Chain ID: 137)

---

## 4. WebSocket Streams — Real-Time Data

### Market Channel (Public)
```
wss://ws-subscriptions-clob.polymarket.com/ws/
```

**Subscribe message:**
```json
{
  "type": "subscribe",
  "channel": "market",
  "markets": ["token_id_1", "token_id_2"]
}
```

**Events received:**
- `book` — Order book updates
- `price_change` — Price movements
- `last_trade_price` — Latest trade prices
- `tick_size_change` — Market parameter changes

### User Channel (Authenticated)
```
wss://ws-subscriptions-clob.polymarket.com/ws/user
```

**Events received:**
- `order_fill` — Your orders getting filled
- `order_cancel` — Order cancellations
- `trade_lifecycle` — Trade status updates (matched, confirmed)

### Connection Management
- Send `PING` every 5 seconds to keep connection alive
- Reconnect on disconnection with exponential backoff
- Max ~100ms latency for updates

---

## 5. Official SDKs

| Language | Package | Repository |
|----------|---------|------------|
| **Python** | `py-clob-client` | [Polymarket/py-clob-client](https://github.com/Polymarket/py-clob-client) |
| **TypeScript** | `@polymarket/clob-client` | [Polymarket/clob-client](https://github.com/Polymarket/clob-client) |
| **Rust** | `polymarket-rs` | [Polymarket/polymarket-rs](https://github.com/Polymarket/polymarket-rs) |

### Python SDK Quick Reference

```python
# Installation
pip install py-clob-client

# Read-only client (no auth needed)
from py_clob_client.client import ClobClient
client = ClobClient("https://clob.polymarket.com")

# Authenticated client (for trading)
client = ClobClient(
    "https://clob.polymarket.com",
    key=PRIVATE_KEY,       # Wallet private key
    chain_id=137,          # Polygon
    signature_type=1,      # 0=EOA, 1=Email/Magic, 2=Browser proxy
    funder=FUNDER_ADDRESS  # Address holding funds
)
client.set_api_creds(client.create_or_derive_api_creds())

# Get market data
mid = client.get_midpoint(token_id)
price = client.get_price(token_id, side="BUY")
book = client.get_order_book(token_id)

# Place a market order
from py_clob_client.clob_types import MarketOrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY

order = MarketOrderArgs(
    token_id="<token-id>",
    amount=25.0,
    side=BUY,
    order_type=OrderType.FOK
)
signed = client.create_market_order(order)
resp = client.post_order(signed, OrderType.FOK)
```

---

## 6. Third-Party Data Sources

| Source | URL | Description |
|--------|-----|-------------|
| **Polymarket Analytics** | polymarketanalytics.com | Public leaderboard with PnL, holdings, real-time stats (updated every 5 min) |
| **Predexon API** | predexon.com | Per-market performance breakdowns: realized PnL, volume, ROI, win rates |
| **Kaggle Datasets** | kaggle.com | Historical Polymarket data dumps (markets, events, trades) |

---

## 7. API Rate Limits & Best Practices

| Concern | Recommendation |
|---------|----------------|
| Rate limiting | Implement exponential backoff; cache responses |
| Data freshness | Leaderboard polling every 5 minutes is sufficient |
| WebSocket stability | Ping every 5 seconds; reconnect on drop |
| Error handling | Handle 429 (rate limit), 503 (maintenance), network errors |
| Pagination | Use limit/offset; fetch in batches of 50-100 |

---

## 8. Key Findings for CopyPoly

### What We Can Do Without Authentication
- ✅ Fetch leaderboard data (all timeframes, all categories)
- ✅ Get market metadata (questions, prices, liquidity)
- ✅ Read order books (prices, depth)
- ✅ Stream market data via WebSocket
- ✅ Search for events and markets
- ✅ View public profiles

### What Requires Authentication
- 🔐 Place/cancel orders (copy trading execution)
- 🔐 View own positions and trade history
- 🔐 Subscribe to user-specific WebSocket channel
- 🔐 Manage API keys

### Critical Insight
> **The leaderboard + positions endpoints are the backbone of CopyPoly.** We can identify top traders, monitor their positions, detect new trades, and then replicate them through the CLOB API — all programmatically.
