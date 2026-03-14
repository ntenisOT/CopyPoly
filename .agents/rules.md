# CopyPoly — AI Agent Rules

## Workflow Orchestration

### 1. Plan Before Building
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately — don't keep pushing
- Write detailed specs upfront to reduce ambiguity
- Reference existing docs in `docs/` before making architectural decisions

### 2. Self-Improvement Loop
- After ANY correction from the user: update `tasks/lessons.md` with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for relevant project

### 3. Verification Before Done
- Never mark a task complete without proving it works
- Run `docker compose up --build -d` and verify logs after changes
- Check that migrations run cleanly: `docker compose logs migrations`
- Check app starts: `docker compose logs app`
- Ask yourself: "Would a staff engineer approve this?"

### 4. Demand Elegance (Balanced)
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes — don't over-engineer
- Challenge your own work before presenting it

### 5. Autonomous Bug Fixing
- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests — then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

---

## Task Management

1. **Plan First**: Write plan to `tasks/todo.md` with checkable items
2. **Verify Plan**: Check in before starting implementation
3. **Track Progress**: Mark items complete as you go
4. **Explain Changes**: High-level summary at each step
5. **Document Results**: Add review section to `tasks/todo.md`
6. **Capture Lessons**: Update `tasks/lessons.md` after corrections

---

## Core Principles

- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs.
- **Latest Versions**: Always use latest stable/LTS versions of all dependencies.
- **Docker First**: Everything runs in Docker. `docker compose down -v && docker compose up --build -d` must always work.

---

## CopyPoly Specifics

### Technology Stack (Do Not Change Without Discussion)
- **Python 3.13+** — Runtime
- **PostgreSQL 18** — Database (Dockerized)
- **SQLAlchemy 2.0 async** — ORM
- **Alembic** — Migrations (our Liquibase)
- **Pydantic Settings** — Configuration
- **structlog** — Logging (JSON in Docker, pretty in TTY)
- **FastAPI** — Dashboard API
- **React + shadcn/ui + TradingView** — Dashboard frontend (Phase 5)

### Architecture Rules
- All configuration is runtime-tunable via `app_config` table — no hardcoded values
- All thresholds (min win rate, trade count, etc.) are configurable
- Trading mode defaults to `paper` — never default to `live`
- Use `SecretStr` for any private keys or tokens — never log secrets
- Every new table needs an Alembic migration — never raw SQL schema changes

### Git Workflow
- Commit after each implementation step with descriptive messages
- Format: `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`
- Push after each commit: `git add -A && git commit -m "msg" && git push`
- GPG signing is disabled for this repo

### Docker Commands
- Start: `docker compose up --build -d`
- Nuke & rebuild: `docker compose down -v && docker compose up --build -d`
- Logs: `docker compose logs -f app`
- DB shell: `docker compose exec -e PAGER=cat db psql -U copypoly -d copypoly`
- New migration: `docker compose run --rm app python -m alembic revision --autogenerate -m "description"`
