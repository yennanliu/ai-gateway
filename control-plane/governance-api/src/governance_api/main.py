"""FastAPI application entrypoint for the governance API."""

from __future__ import annotations

from fastapi import FastAPI

from governance_api import __version__


def create_app() -> FastAPI:
    app = FastAPI(title="AI Gateway — Governance API", version=__version__)

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
        """AI Gateway version (LiteLLM compatibility matrix added in M3)."""
        return {"version": __version__, "litellm": "unpinned-dev"}

    return app


app = create_app()
