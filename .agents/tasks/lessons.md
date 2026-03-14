# CopyPoly — Lessons Learned

Log of corrections and patterns to prevent recurring mistakes.

---

## 2026-03-14: Hatchling build-backend typo
- **Mistake**: Used `hatchling.backends` instead of `hatchling.build` in pyproject.toml
- **Rule**: Always verify build-backend module paths — check official docs, not memory

## 2026-03-14: JSONB server_default double-quoting
- **Mistake**: Used `server_default="'[]'"` for JSONB columns, which SQLAlchemy double-quoted to `'''[]'''`
- **Rule**: For JSONB defaults, always use `server_default=text("'[]'::jsonb")` with explicit cast

## 2026-03-14: Missing psycopg2 for Alembic
- **Mistake**: Only included `asyncpg` but Alembic runs synchronously and needs `psycopg2`
- **Rule**: Always include both `asyncpg` (for app) AND `psycopg2-binary` (for Alembic) in dependencies

## 2026-03-14: Missing README.md for hatchling
- **Mistake**: pyproject.toml referenced `readme = "README.md"` but file didn't exist in Docker build
- **Rule**: If pyproject.toml references README.md, ensure it exists AND is copied in Dockerfile

## 2026-03-14: GPG signing blocks git commit
- **Mistake**: Git commit hung because global GPG signing was enabled
- **Rule**: Disable GPG signing per-repo with `git config --local commit.gpgsign false`

## 2026-03-14: Polymarket API uses `timePeriod` not `period`
- **Mistake**: Used `period=ALL` based on third-party docs; API silently ignored it and returned all-time data for every period
- **Rule**: Always verify API params against the actual website's network requests. The correct param is `timePeriod` with lowercase values: `day`, `week`, `month`, `all`
- **Impact**: This would have made our entire analysis engine worthless — it was comparing identical data across "different" periods

## 2026-03-14: Data API is unreliable for historical data
- **Mistake**: Used Polymarket Data API for historical trade crawling; got 80% error rate due to Cloudflare rate limiting
- **Rule**: For large-scale historical data crawling, always prefer on-chain data (subgraphs) over REST APIs
- **Solution**: Replaced with Polymarket's Goldsky subgraph (free, no auth, no rate limits)

## 2026-03-14: Never accumulate large datasets in memory before writing
- **Mistake**: Collected ALL events for a trader (~160K) in memory before writing to DB. Appeared "stuck" for 10+ minutes
- **Rule**: Store page-by-page as data arrives. Each page (1000 events) should be immediately persisted and logged
- **Impact**: Fixed the apparent hang, provided real-time progress visibility, and reduced memory usage

## 2026-03-14: Use full event ID for trade uniqueness, not just txHash
- **Mistake**: Extracted only `txHash` from subgraph event ID (`txHash_orderHash`). A single transaction can have multiple fills, causing uniqueness collisions
- **Rule**: Use the full event ID as the unique identifier. In The Graph, event IDs are already unique per fill

## 2026-03-14: Scheduled jobs can race with themselves
- **Mistake**: Position scanner job used plain INSERT for new positions. When two scheduler cycles overlapped, the same position was inserted twice → UniqueViolation error
- **Rule**: Always use INSERT...ON CONFLICT (upsert) for data that could be detected by concurrent job runs

