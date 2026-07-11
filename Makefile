ALEMBIC = uv run alembic -c control-plane/governance-api/alembic.ini
UI_DIR = admin-ui

.PHONY: help install dev api ui test test-py test-ui lint format migrate revision seed clean

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Install all deps (Python + UI)
	uv sync --all-packages
	@if [ -d "$(UI_DIR)" ]; then cd $(UI_DIR) && (pnpm install || npm install); fi

dev: ## Run governance-api + Vue UI (proxy added in M3), hot-reloading
	./scripts/dev.sh

api: ## Run only the governance API
	uv run uvicorn governance_api.main:app --reload --port 8080

ui: ## Run only the Vue dev server
	cd $(UI_DIR) && (pnpm dev || npm run dev)

test: test-py test-ui ## Run all tests

test-py: ## Run Python tests with coverage
	uv run pytest --cov --cov-report=term-missing

test-ui: ## Run UI tests (if present)
	@if [ -d "$(UI_DIR)" ]; then cd $(UI_DIR) && (pnpm test:unit || npm run test:unit); else echo "no UI yet"; fi

lint: ## Lint + type-check
	uv run ruff check .
	uv run mypy

format: ## Auto-format
	uv run ruff format .
	uv run ruff check --fix .

migrate: ## Apply DB migrations
	$(ALEMBIC) upgrade head

revision: ## Autogenerate a migration: make revision m="message"
	$(ALEMBIC) revision --autogenerate -m "$(m)"

seed: ## Seed demo data
	uv run python scripts/seed.py

clean: ## Remove local SQLite db and caches
	rm -f ai-gateway.db
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
