# CopyPoly

Polymarket copy-trading system — discover, score, and copy the best traders.

## Quick Start

```bash
# Clone and start
git clone <repo-url>
cd copypoly
cp .env.example .env

# Start everything (PostgreSQL + migrations + app)
docker compose up --build -d

# Check logs
docker compose logs -f app

# Destroy and recreate from scratch
docker compose down -v
docker compose up --build -d
```

## Architecture

See `docs/` for full documentation:

- `01-project-overview.md` — Mission and features
- `02-polymarket-api-research.md` — API research
- `03-technology-decisions.md` — Tech stack
- `04-architecture.md` — System design
- `05-database-schema.md` — Database tables
- `06-implementation-plan.md` — Phased plan
- `07-trader-scoring-algorithm.md` — Scoring formula
- `08-position-sizing.md` — Position allocation

## License

MIT
