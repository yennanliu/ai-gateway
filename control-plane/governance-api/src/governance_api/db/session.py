"""Engine + session factory.

Sync SQLAlchemy 2.0: the control plane is not the latency-critical hot path
(that is the LiteLLM proxy), so a simple sync session run in FastAPI's
threadpool keeps the code straightforward and portable across SQLite/Postgres.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from governance_api.config import settings


def make_engine(url: str) -> Engine:
    is_sqlite = url.startswith("sqlite")
    connect_args = {"check_same_thread": False} if is_sqlite else {}
    kwargs: dict[str, Any] = {}
    if url in ("sqlite://", "sqlite:///:memory:"):
        # A single shared connection so an in-memory DB is visible across threads
        # (sync endpoints run in FastAPI's threadpool).
        kwargs["poolclass"] = StaticPool
    engine = create_engine(url, connect_args=connect_args, future=True, **kwargs)
    if is_sqlite:
        # SQLite disables FK enforcement by default; turn it on so ON DELETE
        # CASCADE and FK constraints behave like Postgres.
        @event.listens_for(engine, "connect")
        def _fk_pragma(dbapi_conn, _record):  # type: ignore[no-untyped-def]
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


engine = make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a session, committed on success."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
