# Governance API (control plane). Built from the repo root context.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY . /app
# Install only the governance-api package subset (no LiteLLM, no dev deps).
RUN uv sync --package governance-api --frozen --no-dev

EXPOSE 8080

# Apply migrations, then serve. DATABASE_URL selects SQLite (default) or Postgres.
CMD ["sh", "-c", "uv run --package governance-api alembic -c control-plane/governance-api/alembic.ini upgrade head && uv run --package governance-api uvicorn governance_api.main:app --host 0.0.0.0 --port 8080"]
