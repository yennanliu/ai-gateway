ALEMBIC = uv run alembic -c control-plane/governance-api/alembic.ini
UI_DIR = admin-ui

.PHONY: help install dev api ui proxy test test-py test-ui e2e e2e-docker e2e-docker-smoke docker-up docker-down docker-logs docker-ps smoke lint format migrate revision seed openapi clean

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

proxy: ## Run the LiteLLM data-plane proxy (installs the proxy extra; needs a compiled config)
	uv sync --all-packages --extra proxy
	AIGW_LITELLM_CONFIG=./litellm.config.yaml uv run --package aigw-hooks bash data-plane/litellm/entrypoint.sh

test: test-py test-ui ## Run all tests

test-py: ## Run Python tests with coverage
	uv run pytest --cov --cov-report=term-missing

test-ui: ## Run UI tests (if present)
	@if [ -d "$(UI_DIR)" ]; then cd $(UI_DIR) && (pnpm test:unit || npm run test:unit); else echo "no UI yet"; fi

e2e: ## Run end-to-end tests (boots the real server over HTTP)
	uv run pytest tests/e2e -v

e2e-docker: ## Full-system e2e QA: docker compose up + comprehensive assertions across both planes
	./scripts/e2e_docker_qa.sh

e2e-docker-smoke: ## Fast full-system smoke: docker compose up + one real request + a 401
	./scripts/e2e_docker.sh

docker-up: ## Run the whole stack in Docker and LEAVE IT RUNNING (control :8080, proxy :4000, UI :8081)
	./scripts/docker_up.sh

docker-down: ## Stop the Docker stack (removes containers + the data volume)
	docker compose -f deploy/docker-compose/docker-compose.yml down -v --remove-orphans

docker-logs: ## Tail logs from the running Docker stack (Ctrl-C to stop tailing)
	docker compose -f deploy/docker-compose/docker-compose.yml logs -f

docker-ps: ## Show container status of the running Docker stack
	docker compose -f deploy/docker-compose/docker-compose.yml ps

smoke: ## Run the shell smoke script (migrate -> seed -> API -> request)
	./scripts/smoke.sh

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

openapi: ## Export the OpenAPI schema to openapi.json
	uv run python scripts/export_openapi.py

clean: ## Remove local SQLite db and caches
	rm -f ai-gateway.db
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
