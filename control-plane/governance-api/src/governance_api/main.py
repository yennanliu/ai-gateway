"""FastAPI application entrypoint for the governance API."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from governance_api import __version__
from governance_api.api import (
    apps,
    billing,
    config,
    keys,
    memberships,
    models,
    orgs,
    teams,
    users,
)
from governance_api.banner import show_banner
from governance_api.config import COMPATIBLE_LITELLM, settings

API_DESCRIPTION = """
Control-plane API for **AI Gateway** — governance, virtual keys, model registry,
budgets, usage/billing, and LiteLLM config compilation.

**Auth (dev):** send `X-User-Id`, `X-Org-Id`, and `X-Org-Roles` headers
(e.g. `org-admin`). OIDC/SAML replaces this in a later milestone.

Interactive docs: **Swagger UI** at `/docs`, **ReDoc** at `/redoc`,
raw schema at `/openapi.json`.
"""

OPENAPI_TAGS = [
    {"name": "system", "description": "Health, readiness, and version."},
    {"name": "orgs", "description": "Organizations."},
    {"name": "teams", "description": "Teams within an org."},
    {"name": "users", "description": "Users and memberships (RBAC)."},
    {"name": "memberships", "description": "Team role assignments."},
    {"name": "apps", "description": "Agent / service consumers."},
    {"name": "keys", "description": "Virtual key lifecycle (issue/rotate/revoke)."},
    {"name": "registry", "description": "Provider credentials + model deployments."},
    {"name": "config", "description": "Compile & reload the LiteLLM proxy config."},
    {"name": "billing", "description": "Usage aggregation, invoices, budgets, rate cards."},
]


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    show_banner(
        version=__version__,
        litellm_version=COMPATIBLE_LITELLM,
        environment=settings.environment,
    )
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Gateway — Governance API",
        version=__version__,
        description=API_DESCRIPTION,
        openapi_tags=OPENAPI_TAGS,
        docs_url="/docs",
        redoc_url="/redoc",
        contact={"name": "AI Gateway", "url": "https://github.com/yennanliu/ai-gateway"},
        lifespan=_lifespan,
    )

    for module in (orgs, teams, users, memberships, apps, keys, models, config, billing):
        app.include_router(module.router)

    @app.get("/healthz", tags=["system"])
    def healthz() -> dict[str, str]:
        """Liveness probe."""
        return {"status": "ok"}

    @app.get("/readyz", tags=["system"])
    def readyz() -> dict[str, str]:
        """Readiness probe (extended in later milestones to check DB/cache)."""
        return {"status": "ready"}

    @app.get("/api/v1/version", tags=["system"])
    def version() -> dict[str, str]:
        """AI Gateway version + the LiteLLM version this build is tested against."""
        return {"version": __version__, "litellm": COMPATIBLE_LITELLM}

    return app


app = create_app()
