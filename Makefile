# ============================================
# CopyPoly Makefile
# ============================================

.PHONY: help up down nuke build logs migrate shell db-shell test lint

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

# --- Docker Commands ---

up: ## Start all services (build if needed)
	docker compose up --build -d
	@echo ""
	@echo "✅ CopyPoly is running!"
	@echo "   App:      http://localhost:8000"
	@echo "   Postgres: localhost:5433"
	@echo ""

down: ## Stop all services
	docker compose down

nuke: ## 🔥 Destroy EVERYTHING (containers, volumes, images) and rebuild
	docker compose down -v --remove-orphans
	docker compose up --build -d
	@echo ""
	@echo "🔥 Nuked and rebuilt from scratch!"

build: ## Rebuild containers without cache
	docker compose build --no-cache

logs: ## Tail all service logs
	docker compose logs -f

logs-app: ## Tail app logs only
	docker compose logs -f app

logs-db: ## Tail database logs only
	docker compose logs -f db

# --- Database Commands ---

migrate: ## Run Alembic migrations manually
	docker compose run --rm migrations

migrate-create: ## Create a new migration (usage: make migrate-create MSG="add_new_table")
	docker compose run --rm app python -m alembic revision --autogenerate -m "$(MSG)"

migrate-down: ## Rollback one migration
	docker compose run --rm app python -m alembic downgrade -1

migrate-history: ## Show migration history
	docker compose run --rm app python -m alembic history

db-shell: ## Open psql shell
	docker compose exec db psql -U copypoly -d copypoly

# --- Development Commands ---

shell: ## Open a Python shell in the app container
	docker compose exec app python

test: ## Run tests
	docker compose exec app python -m pytest -v

lint: ## Run Ruff linter
	docker compose exec app python -m ruff check src/

format: ## Auto-format code with Ruff
	docker compose exec app python -m ruff format src/
