---
description: How to backup and restore the PostgreSQL database
---

# Database Backup & Restore

## Backup

Creates a SQL dump of the entire database. Use before any destructive operation.

1. Create backup:
```bash
docker compose exec db pg_dump -U copypoly copypoly | Set-Content -Path "backups/copypoly_$(Get-Date -Format 'yyyyMMdd_HHmm').sql"
```

2. Verify backup file exists:
```bash
Get-ChildItem backups/ | Sort-Object LastWriteTime -Descending | Select-Object -First 3
```

## Restore

Restores from a SQL backup file into a running (empty or existing) database.

1. Ensure DB is running:
```bash
docker compose up -d db
```

2. Restore from backup:
```bash
Get-Content backups/copypoly_YYYYMMDD_HHMM.sql | docker compose exec -T db psql -U copypoly copypoly
```

## Quick One-Liner: Backup → Nuke → Restore

```bash
# Backup, nuke, rebuild, then restore data
docker compose exec db pg_dump -U copypoly copypoly | Set-Content -Path "backups/pre_nuke.sql"
docker compose down -v --remove-orphans
docker compose up --build -d
Start-Sleep -Seconds 15
Get-Content backups/pre_nuke.sql | docker compose exec -T db psql -U copypoly copypoly
```
