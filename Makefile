.PHONY: dev test lint format migrate migrate-create migrate-downgrade test-cov help

# ============================================
# Aletheia - Development Commands
# ============================================

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# --- Backend ---
dev: ## Run FastAPI dev server with hot reload
	cd backend && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# --- Database Migrations ---
migrate: ## Run all pending Alembic migrations
	cd backend && uv run alembic upgrade head

migrate-create: ## Create new migration (usage: make migrate-create msg="add users table")
	cd backend && uv run alembic revision --autogenerate -m "$(msg)"

migrate-downgrade: ## Downgrade last migration
	cd backend && uv run alembic downgrade -1

# --- Testing ---
test: ## Run backend tests
	cd backend && uv run pytest -v

test-cov: ## Run tests with coverage
	cd backend && uv run pytest --cov=app --cov-report=html -v

# --- Linting & Formatting ---
lint: ## Run ruff linter
	cd backend && uv run ruff check .

format: ## Format code with ruff
	cd backend && uv run ruff format .
	cd backend && uv run ruff check --fix .
