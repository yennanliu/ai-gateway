"""End-to-end checks against a LIVE AWS deployment — both planes and the
optional isolated LiteLLM native Admin UI.

Opt-in: each group is skipped unless its base URL is set, so this never runs in
the hermetic local suite. Point it at the deployed ALB:

    AIGW_E2E_BASE_URL=http://<alb>            \\   # governed control + data plane (:80)
    AIGW_LITELLM_UI_URL=http://<alb>:4001     \\   # isolated LiteLLM native UI
    AIGW_LITELLM_UI_PASSWORD=<from secret>        # enables the UI login check
    uv run pytest tests/e2e/test_aws_deployment.py -v

These drive real HTTP against a running environment and create demo data
(orgs/keys on the governed plane; a short-lived key in the LiteLLM UI's own
store). They prove the deployment works, not just the code.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import httpx
import pytest

GOV_URL = os.environ.get("AIGW_E2E_BASE_URL", "").rstrip("/")
UI_URL = os.environ.get("AIGW_LITELLM_UI_URL", "").rstrip("/")
# The isolated dev instance's master key (also a valid UI login credential).
UI_MASTER_KEY = os.environ.get("AIGW_LITELLM_UI_MASTER_KEY", "sk-aigw-litellm-ui-dev")
UI_PASSWORD = os.environ.get("AIGW_LITELLM_UI_PASSWORD", "")

gov = pytest.mark.skipif(not GOV_URL, reason="set AIGW_E2E_BASE_URL to the governed ALB base")
ui = pytest.mark.skipif(not UI_URL, reason="set AIGW_LITELLM_UI_URL to the LiteLLM UI base")

PLATFORM = {"X-User-Id": "e2e-aws", "X-Org-Roles": "org-admin"}


def _admin(org_id: str) -> dict[str, str]:
    return {"X-User-Id": "e2e-aws", "X-Org-Id": org_id, "X-Org-Roles": "org-admin"}


# ---------------------------------------------------------------------------
# Governed control plane + data plane (behind the ALB on :80)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def gov_client() -> Iterator[httpx.Client]:
    with httpx.Client(base_url=GOV_URL, timeout=20.0) as c:
        yield c


@pytest.fixture(scope="module")
def virtual_key(gov_client: httpx.Client) -> str:
    """Issue a real virtual key via the control plane (org -> team -> key)."""
    org = gov_client.post("/api/v1/orgs", headers=PLATFORM, json={"name": "E2E AWS"})
    org_id = org.json()["id"]
    admin = _admin(org_id)
    team_id = gov_client.post(
        "/api/v1/teams", headers=admin, json={"org_id": org_id, "name": "e2e"}
    ).json()["id"]
    issued = gov_client.post("/api/v1/keys", headers=admin, json={"team_id": team_id})
    assert issued.status_code == 201, issued.text
    return str(issued.json()["key"])


@gov
def test_gov_control_plane_healthy(gov_client: httpx.Client) -> None:
    assert gov_client.get("/healthz").status_code == 200
    version = gov_client.get("/api/v1/version").json()
    assert version["version"] and version["litellm"]
    assert gov_client.get("/docs").status_code == 200


@gov
def test_gov_data_plane_health(gov_client: httpx.Client) -> None:
    assert gov_client.get("/health/liveliness").status_code == 200
    ready = gov_client.get("/health/readiness")
    assert ready.status_code == 200 and ready.json()["status"]


@gov
def test_gov_data_plane_status_endpoint(gov_client: httpx.Client) -> None:
    org_id = gov_client.post(
        "/api/v1/orgs", headers=PLATFORM, json={"name": "E2E AWS Status"}
    ).json()["id"]
    resp = gov_client.get("/api/v1/data-plane/status", headers=_admin(org_id))
    assert resp.status_code == 200
    body = resp.json()
    assert body["litellm_version"] and "models" in body and "routing" in body


@gov
def test_gov_data_plane_rejects_missing_and_bogus_keys(gov_client: httpx.Client) -> None:
    assert gov_client.get("/v1/models").status_code == 401
    bogus = {"Authorization": "Bearer sk-ag-bogus"}
    assert gov_client.get("/v1/models", headers=bogus).status_code == 401


@gov
def test_gov_data_plane_accepts_a_real_virtual_key(
    gov_client: httpx.Client, virtual_key: str
) -> None:
    # The core invariant, live: LiteLLM authenticates via our custom-auth hook
    # against our DB — a key issued by the control plane passes; nothing else does.
    assert virtual_key.startswith("sk-ag-")
    resp = gov_client.get("/v1/models", headers={"Authorization": f"Bearer {virtual_key}"})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Isolated LiteLLM native Admin UI (its OWN store; on :4001)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ui_client() -> Iterator[httpx.Client]:
    with httpx.Client(base_url=UI_URL, timeout=25.0) as c:
        yield c


@ui
def test_ui_health_has_its_own_db(ui_client: httpx.Client) -> None:
    assert ui_client.get("/health/liveliness").status_code == 200
    ready = ui_client.get("/health/readiness")
    assert ready.status_code == 200
    # Unlike the governed plane ("Not connected"), this instance runs its own DB.
    assert ready.json()["db"] == "connected"


@ui
def test_ui_pages_served(ui_client: httpx.Client) -> None:
    assert ui_client.get("/ui/").status_code == 200
    assert ui_client.get("/ui/policies/").status_code == 200


@ui
def test_ui_master_key_admin_api_and_own_key_store(ui_client: httpx.Client) -> None:
    headers = {"Authorization": f"Bearer {UI_MASTER_KEY}"}
    assert ui_client.get("/models", headers=headers).status_code == 200
    # Minting a key exercises LiteLLM's OWN key store (its Prisma DB) — separate
    # from the governed plane's virtual keys. No key_alias: LiteLLM enforces alias
    # uniqueness, and this test may run repeatedly against the same instance.
    created = ui_client.post("/key/generate", headers=headers, json={"duration": "10m"})
    assert created.status_code == 200
    assert str(created.json()["key"]).startswith("sk-")


@ui
@pytest.mark.skipif(not UI_PASSWORD, reason="set AIGW_LITELLM_UI_PASSWORD for the login check")
def test_ui_username_password_login(ui_client: httpx.Client) -> None:
    resp = ui_client.post(
        "/login",
        data={"username": "admin", "password": UI_PASSWORD},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)
    assert "login=success" in resp.headers.get("location", "")
    assert "token=" in resp.headers.get("set-cookie", "")
