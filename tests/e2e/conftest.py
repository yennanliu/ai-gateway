"""E2E fixture: run migrations, then boot the real uvicorn server on a temp DB."""

from __future__ import annotations

import os
import socket
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port: int = s.getsockname()[1]
    s.close()
    return port


def _wait_healthy(url: str, timeout: float = 40.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(f"{url}/healthz", timeout=1.0).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.3)
    raise RuntimeError(f"server did not become healthy at {url}")


@pytest.fixture(scope="session")
def base_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    db_path = tmp_path_factory.mktemp("e2e") / "e2e.db"
    env = {**os.environ, "AIGW_DATABASE_URL": f"sqlite:///{db_path}"}

    subprocess.run(
        [
            "uv",
            "run",
            "alembic",
            "-c",
            "control-plane/governance-api/alembic.ini",
            "upgrade",
            "head",
        ],
        cwd=REPO_ROOT,
        env=env,
        check=True,
    )

    port = _free_port()
    proc = subprocess.Popen(
        ["uv", "run", "uvicorn", "governance_api.main:app", "--port", str(port)],
        cwd=REPO_ROOT,
        env=env,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        _wait_healthy(url)
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture(scope="session")
def client(base_url: str) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=base_url, timeout=10.0) as c:
        yield c
