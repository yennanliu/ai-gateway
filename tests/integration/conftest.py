"""Integration fixtures: a real seeded control-plane DB + a stub upstream.

Shared by the control-plane <-> data-plane gateway integration tests. The DB is
in-memory SQLite on a StaticPool (one shared connection), so the many
short-lived sessions the data-plane hooks open all observe the same seeded data,
exactly as the two planes share one DB in production.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from governance_api.db.models import Base, Team
from governance_api.db.session import make_engine
from governance_api.services.seed import seed

STUB_REPLY = "Hello from the AI Gateway stub."


class _StubHandler(BaseHTTPRequestHandler):
    """A tiny OpenAI-compatible upstream: any POST returns one fixed completion."""

    def log_message(self, *args: object) -> None:  # silence access logs
        pass

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        body = {
            "id": "chatcmpl-stub",
            "object": "chat.completion",
            "created": 1700000000,
            "model": "gpt-4o-mini",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": STUB_REPLY},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 8, "completion_tokens": 7, "total_tokens": 15},
        }
        payload = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


@pytest.fixture
def stub_url() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


@dataclass
class Gateway:
    """Handle onto a seeded gateway: the shared engine, a session factory, and
    the seeded identifiers the tests act on."""

    engine: Engine
    new_session: Callable[[], Session]
    org_id: str
    platform_team_id: str  # under budget (88/100), primary team of the seeded key
    research_team_id: str  # over budget (60/60) -> pre-call enforcement blocks
    key: str  # seeded plaintext key; allowed_models = demo-gpt, demo-gpt-4o


@pytest.fixture
def gateway(stub_url: str) -> Iterator[Gateway]:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    new_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = new_session()
    result = seed(session, stub_url=stub_url)
    research_id = session.execute(select(Team).where(Team.name == "Research")).scalar_one().id
    session.commit()
    session.close()
    try:
        yield Gateway(
            engine=engine,
            new_session=new_session,
            org_id=result["org_id"],
            platform_team_id=result["team_id"],
            research_team_id=research_id,
            key=result["key"],
        )
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
