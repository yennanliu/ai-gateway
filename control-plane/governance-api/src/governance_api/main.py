"""FastAPI application entrypoint for the governance API."""

from __future__ import annotations

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
from governance_api.config import COMPATIBLE_LITELLM


def create_app() -> FastAPI:
    app = FastAPI(title="AI Gateway — Governance API", version=__version__)

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
