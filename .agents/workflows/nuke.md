---
description: How to nuke and rebuild the entire Docker stack from scratch
---

# Nuke & Rebuild

> ⚠️ **WARNING**: This destroys ALL database data including historical trade data.
> If historical data has been crawled, run `/backup` first!

Destroys all containers, volumes (database data), and rebuilds everything from scratch.
Alembic migrations re-run automatically, seeding the database with default config.

// turbo-all

1. Optional — backup first (skip if DB is empty/throwaway):
```bash
docker compose exec db pg_dump -U copypoly copypoly | Set-Content -Path "backup_$(Get-Date -Format 'yyyyMMdd_HHmm').sql"
```

2. Destroy everything:
```bash
docker compose down -v --remove-orphans
```

3. Rebuild and start:
```bash
docker compose up --build -d
```

4. Verify migrations ran:
```bash
docker compose logs migrations
```
Expected: `Running upgrade -> 001_initial_schema, Initial schema — all 9 tables.`

5. Verify app started:
```bash
docker compose logs --tail 5 app
```
Expected: `copypoly_ready` event in logs with `mode: paper`.

6. Verify database tables:
```bash
docker compose exec -e PAGER=cat db psql -U copypoly -d copypoly -c "\dt"
```
Expected: 10+ tables (app + alembic_version).
