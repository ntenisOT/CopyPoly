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
