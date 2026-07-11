"""Shared pytest fixtures.

Local-first: tests run against in-memory SQLite with no external services.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session, sessionmaker

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
async def client(db: Session) -> Iterator[AsyncClient]:
    """AsyncClient bound to the app, with the DB session overridden to the test DB."""
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
