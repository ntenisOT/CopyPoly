# Technology Decisions

## Architecture Overview

CopyPoly will be built as a **Python monolith with modular services**, designed to evolve into microservices if needed. Python was chosen because:

1. **Official SDK support** — Polymarket's `py-clob-client` is well-maintained
2. **Data analysis ecosystem** — pandas, numpy for trader scoring
3. **Async support** — asyncio + aiohttp for concurrent API calls and WebSocket streams
4. **Rapid development** — Fast iteration for a new project
5. **Existing expertise** — Aligns with the team's Python experience (see infra-python-automation framework)

---

## Technology Stack

### Core Runtime

| Component | Choice | Rationale |
|-----------|--------|-----------|
| **Language** | Python 3.13+ | Official SDK, async support, data analysis |
| **Package Manager** | `uv` | Fast, modern Python package manager (replaces pip/poetry) |
| **Task Runner** | `uv run` + Makefile | Simple, reproducible commands |
| **Config** | Pydantic Settings | Type-safe configuration with env var support |
| **Logging** | `structlog` | Structured JSON logging for production |

### Data Layer

| Component | Choice | Rationale |
|-----------|--------|-----------|
| **Primary Database** | PostgreSQL 18 (Dockerized) | Relational data fits trader/position model, JSONB support |
| **ORM** | SQLAlchemy 2.0 (async) | Type-safe, async support, migrations |
| **Migrations** | Alembic | Industry standard for SQLAlchemy |
| **Cache** | Redis (or PostgreSQL for simplicity) | Rate limit tracking, temporary data |

### API & Networking

| Component | Choice | Rationale |
|-----------|--------|-----------|
| **HTTP Client** | `httpx` | Modern async HTTP client, better than requests |
| **WebSocket Client** | `websockets` | Standard Python WebSocket library |
| **Polymarket SDK** | `py-clob-client` | Official Python SDK for CLOB operations |
| **Rate Limiting** | Custom + `tenacity` | Retry logic with exponential backoff |

### Scheduling & Background Jobs

| Component | Choice | Rationale |
|-----------|--------|-----------|
| **Scheduler** | APScheduler | Lightweight, supports cron-like scheduling |
| **Background Tasks** | asyncio tasks | Built-in, no external dependencies needed |

### Deployment & Infrastructure

| Component | Choice | Rationale |
|-----------|--------|-----------|
| **Containerization** | Docker + docker-compose | All services containerized, reproducible environments |
| **Database** | PostgreSQL container | Dockerized, with volume persistence |
| **Reverse Proxy** | Traefik or Nginx (optional) | For production TLS termination |

### Dashboard & Monitoring (Phase 5)

| Component | Choice | Rationale |
|-----------|--------|-----------|
| **Backend API** | FastAPI | Async, auto-docs, Pydantic integration — serves JSON API only |
| **Frontend** | React (Vite) | Modern SPA, component-based |
| **UI Library** | shadcn/ui | Premium, consistent component library |
| **Trading Charts** | TradingView Lightweight Charts | Professional trading-grade charts |
| **Data Charts** | Recharts | For non-trading visualizations (bar charts, pie charts) |
| **Notifications** | Telegram Bot API | Real-time alerts on mobile |

### Development & Quality

| Component | Choice | Rationale |
|-----------|--------|-----------|
| **Linting** | Ruff | Fast, comprehensive Python linter/formatter |
| **Type Checking** | mypy (strict) | Catch bugs early |
| **Testing** | pytest + pytest-asyncio | Standard Python testing |
| **Pre-commit** | pre-commit hooks | Enforce quality on every commit |

---

## Alternatives Considered

### Language Alternatives

| Option | Pro | Con | Decision |
|--------|-----|-----|----------|
| **TypeScript/Node.js** | Official SDK, good async | Less data analysis tooling | ❌ Secondary SDK available but Python ecosystem is richer for our use case |
| **Go** | Compiled performance, concurrency | No official SDK, more boilerplate | ❌ Overkill for this project; latency isn't our bottleneck |
| **Rust** | Official SDK, performance | Slow development, overkill | ❌ Development speed matters more than execution speed |

### Database Alternatives

| Option | Pro | Con | Decision |
|--------|-----|-----|----------|
| **SQLite** | Zero setup, embedded | No concurrent access, no remote connections | ❌ Too limited for background jobs + dashboard |
| **MySQL** | Widely available (have MCP access) | Less feature-rich for JSON, analytics | ❌ PostgreSQL is better fit |
| **MongoDB** | Flexible schema | Overkill, inconsistent querying | ❌ Data is structured, relational model fits |
| **ClickHouse** | Amazing for analytics | Too heavy for this project size | ❌ Future consideration if data volume grows |

### Framework Alternatives

| Option | Pro | Con | Decision |
|--------|-----|-----|----------|
| **Django** | Batteries included | Too heavy, not async-first | ❌ FastAPI is leaner and async-native |
| **Flask** | Simple, lightweight | No built-in async, validation, docs | ❌ FastAPI is a better modern choice |
| **Celery** | Advanced task queue | External dependency (Redis/RabbitMQ), complex | ❌ APScheduler + asyncio sufficient initially |

---

## Project Structure

```
copypoly/
├── docs/                          # Documentation (this folder)
│   ├── 01-project-overview.md
│   ├── 02-polymarket-api-research.md
│   ├── 03-technology-decisions.md
│   ├── 04-architecture.md
│   ├── 05-database-schema.md
│   ├── 06-implementation-plan.md
│   ├── 07-trader-scoring-algorithm.md
│   └── 08-position-sizing.md
│
├── src/
│   └── copypoly/                  # Python backend
│       ├── __init__.py
│       ├── main.py                # Entry point, scheduler setup
│       ├── config.py              # Pydantic settings, env var loading
│       │
│       ├── api/                   # Polymarket API clients
│       │   ├── __init__.py
│       │   ├── gamma.py           # Gamma API client (market data)
│       │   ├── data_api.py        # Data API client (leaderboard, positions)
│       │   ├── clob.py            # CLOB API client (trading)
│       │   └── websocket.py       # WebSocket stream manager
│       │
│       ├── collectors/            # Data collection jobs
│       │   ├── __init__.py
│       │   ├── leaderboard.py     # Periodic leaderboard fetching
│       │   ├── positions.py       # Position tracking for followed traders
│       │   └── markets.py         # Market metadata updates
│       │
│       ├── analysis/              # Trader analysis & scoring
│       │   ├── __init__.py
│       │   ├── scorer.py          # Composite trader scoring algorithm
│       │   ├── metrics.py         # Performance metrics calculations
│       │   ├── filters.py         # Trader filtering rules
│       │   └── conflict.py        # Opposite bet conflict resolution
│       │
│       ├── trading/               # Copy trading engine
│       │   ├── __init__.py
│       │   ├── copier.py          # Trade replication logic
│       │   ├── risk.py            # Risk management rules
│       │   ├── sizing.py          # Score-based position sizing
│       │   ├── portfolio.py       # Portfolio management
│       │   └── paper.py           # Paper trading mode
│       │
│       ├── backtesting/           # Backtesting engine (Phase 3)
│       │   ├── __init__.py
│       │   ├── runner.py          # Backtest simulation runner
│       │   ├── data_loader.py     # Historical data ingestion
│       │   └── reporter.py        # Performance report generation
│       │
│       ├── db/                    # Database layer
│       │   ├── __init__.py
│       │   ├── models.py          # SQLAlchemy models
│       │   ├── session.py         # Database session management
│       │   └── queries.py         # Common query helpers
│       │
│       ├── dashboard/             # FastAPI backend API (Phase 5)
│       │   ├── __init__.py
│       │   ├── app.py             # FastAPI app
│       │   └── routes.py          # API routes (JSON only)
│       │
│       └── notifications/         # Alert system
│           ├── __init__.py
│           └── telegram.py        # Telegram bot notifications
│
├── frontend/                      # React SPA (Phase 5)
│   ├── src/
│   │   ├── components/            # shadcn/ui components
│   │   ├── pages/                 # Route pages
│   │   ├── hooks/                 # Custom React hooks
│   │   ├── lib/                   # Utilities, API client
│   │   └── App.tsx
│   ├── package.json
│   ├── vite.config.ts
│   └── Dockerfile
│
├── tests/                         # Test suite
│   ├── conftest.py
│   ├── test_collectors/
│   ├── test_analysis/
│   ├── test_trading/
│   └── test_backtesting/
│
├── docker-compose.yml             # All services: app, db, frontend
├── Dockerfile                     # Python backend container
├── pyproject.toml                 # Project metadata, dependencies
├── .env.example                   # Environment variable template
├── .gitignore
├── Makefile                       # Common commands (docker shortcuts)
└── README.md
```

---

## Environment Variables

```env
# Polymarket
POLYMARKET_PRIVATE_KEY=           # Wallet private key (NEVER commit!)
POLYMARKET_FUNDER_ADDRESS=        # Address holding funds
POLYMARKET_CHAIN_ID=137           # Polygon mainnet
POLYMARKET_SIGNATURE_TYPE=0       # 0=EOA, 1=Email, 2=Proxy

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/copypoly

# Notifications
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# App Settings
LOG_LEVEL=INFO
LEADERBOARD_UPDATE_INTERVAL_MINUTES=5
POSITION_CHECK_INTERVAL_SECONDS=30
MAX_TRADERS_TO_FOLLOW=10
MAX_POSITION_SIZE_USDC=100
SLIPPAGE_TOLERANCE_PERCENT=2
```

---

## Dependency Summary

### Core Dependencies (Python Backend)
```toml
[project]
dependencies = [
    "py-clob-client>=0.18",    # Polymarket SDK
    "httpx>=0.27",              # Async HTTP
    "websockets>=12.0",         # WebSocket streams
    "sqlalchemy[asyncio]>=2.0", # ORM
    "asyncpg>=0.29",            # PostgreSQL async driver
    "alembic>=1.14",            # Migrations
    "pydantic-settings>=2.0",   # Configuration
    "apscheduler>=3.10",        # Job scheduling
    "structlog>=24.0",          # Structured logging
    "tenacity>=8.0",            # Retry logic
    "fastapi>=0.115",           # Web framework (JSON API)
    "uvicorn>=0.30",            # ASGI server
    "numpy>=1.26",              # Numerical operations for scoring
    "pandas>=2.2",              # Data analysis for backtesting
]

[project.optional-dependencies]
dev = [
    "ruff>=0.7",               # Linting + formatting
    "mypy>=1.11",              # Type checking
    "pytest>=8.0",             # Testing
    "pytest-asyncio>=0.24",    # Async test support
    "pre-commit>=4.0",         # Git hooks
]
```

### Frontend Dependencies (React Dashboard)
```json
{
  "dependencies": {
    "react": "^19",
    "react-dom": "^19",
    "react-router-dom": "^7",
    "lightweight-charts": "^4",
    "recharts": "^2",
    "@radix-ui/react-*": "latest",
    "class-variance-authority": "latest",
    "clsx": "latest",
    "tailwind-merge": "latest",
    "lucide-react": "latest"
  }
}
```
Note: shadcn/ui components are installed individually via `npx shadcn@latest add <component>`.
