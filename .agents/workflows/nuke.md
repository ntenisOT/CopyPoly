---
description: How to nuke and rebuild the entire Docker stack from scratch
---

# Nuke & Rebuild

Destroys all containers, volumes (database data), and rebuilds everything from scratch.
Alembic migrations re-run automatically, seeding the database with default config.

// turbo-all

1. Destroy everything:
```bash
docker compose down -v --remove-orphans
```

2. Rebuild and start:
```bash
docker compose up --build -d
```

3. Verify migrations ran:
```bash
docker compose logs migrations
```
Expected: `Running upgrade -> 001_initial_schema, Initial schema — all 9 tables.`

4. Verify app started:
```bash
docker compose logs --tail 5 app
```
Expected: `copypoly_ready` event in logs with `mode: paper`.

5. Verify database tables:
```bash
docker compose exec -e PAGER=cat db psql -U copypoly -d copypoly -c "\dt"
```
Expected: 10 tables (9 app + alembic_version).
