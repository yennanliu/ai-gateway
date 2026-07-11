"""Shared pytest fixtures.

Local-first: tests run against in-memory SQLite with no external services.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session, sessionmaker

from governance_api.auth.dependencies import get_principal
from governance_api.auth.principal import Principal
from governance_api.db.models import Base  # aggregator: registers all models
from governance_api.db.session import get_session, make_engine
from governance_api.main import create_app


@pytest.fixture
def db() -> Iterator[Session]:
    """Fresh in-memory SQLite schema per test."""
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = session_local()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def app(db: Session) -> Iterator[FastAPI]:
    """App wired to the test DB. Principal defaults to unauthenticated (header shim)."""
    application = create_app()
    application.dependency_overrides[get_session] = lambda: db
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
def as_principal(app: FastAPI) -> Callable[[Principal], None]:
    """Set the current authenticated principal for subsequent requests."""

    def _set(principal: Principal) -> None:
        app.dependency_overrides[get_principal] = lambda: principal

    return _set


@pytest.fixture
async def client(app: FastAPI) -> Iterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
