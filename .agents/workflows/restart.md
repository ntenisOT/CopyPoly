---
description: How to restart the stack safely (preserves database data)
---

# Restart (Safe — Preserves Data)

Rebuilds and restarts all containers while keeping the database volume intact.
Alembic migrations run automatically to apply any new schema changes.

// turbo-all

1. Stop and rebuild:
```bash
docker compose down --remove-orphans && docker compose up --build -d
```

2. Verify app started:
```bash
docker compose logs --tail 5 app
```
Expected: `copypoly_ready` event with `dashboard: http://0.0.0.0:8000`.

3. Check for migration changes (if schema was modified):
```bash
docker compose logs migrations
```
