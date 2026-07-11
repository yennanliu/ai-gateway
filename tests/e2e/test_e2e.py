"""End-to-end: drive the full governance lifecycle against a running server
over real HTTP (create org -> team -> credential -> model -> key -> budget ->
rate card -> compile config -> usage). Proves the app works, not just units.
"""

from __future__ import annotations

import httpx

PLATFORM = {"X-User-Id": "e2e", "X-Org-Roles": "org-admin"}


def _admin(org_id: str) -> dict[str, str]:
    return {"X-User-Id": "e2e", "X-Org-Id": org_id, "X-Org-Roles": "org-admin"}


def test_system_health_and_docs(client: httpx.Client) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").status_code == 200
    version = client.get("/api/v1/version").json()
    assert version["version"] and version["litellm"]
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_requires_auth(client: httpx.Client) -> None:
    assert client.get("/api/v1/orgs").status_code == 401


def test_full_governance_lifecycle(client: httpx.Client) -> None:
    # 1. platform admin creates an org
    org = client.post("/api/v1/orgs", headers=PLATFORM, json={"name": "E2E Corp"})
    assert org.status_code == 201, org.text
    org_id = org.json()["id"]
    admin = _admin(org_id)

    # 2. team
    team = client.post("/api/v1/teams", headers=admin, json={"org_id": org_id, "name": "Core"})
    assert team.status_code == 201
    team_id = team.json()["id"]

    # 3. provider credential + model deployment
    cred = client.post(
        "/api/v1/provider-credentials",
        headers=admin,
        json={"provider": "openai", "secret_ref": "OPENAI_API_KEY"},
    )
    assert cred.status_code == 201
    model = client.post(
        "/api/v1/models",
        headers=admin,
        json={"public_name": "gpt", "provider": "openai", "model": "gpt-4o"},
    )
    assert model.status_code == 201
    assert any(
        m["public_name"] == "gpt" for m in client.get("/api/v1/models", headers=admin).json()
    )

    # 4. virtual key lifecycle
    issued = client.post("/api/v1/keys", headers=admin, json={"team_id": team_id})
    assert issued.status_code == 201
    key = issued.json()
    assert key["key"].startswith("sk-ag-")
    key_id = key["id"]

    listed = client.get(f"/api/v1/keys?team_id={team_id}", headers=admin).json()
    assert any(k["id"] == key_id and "key" not in k for k in listed)

    rotated = client.post(f"/api/v1/keys/{key_id}/rotate", headers=admin)
    assert rotated.status_code == 200 and rotated.json()["key"] != key["key"]

    revoked = client.post(f"/api/v1/keys/{key_id}/revoke", headers=admin)
    assert revoked.status_code == 200 and revoked.json()["status"] == "revoked"

    # 5. billing config: rate card + budget
    assert (
        client.put(
            "/api/v1/rate-cards", headers=admin, json={"model": "gpt-4o", "price": "2"}
        ).status_code
        == 200
    )
    assert (
        client.put(
            "/api/v1/budgets",
            headers=admin,
            json={"scope_type": "team", "scope_id": team_id, "limit": "100"},
        ).status_code
        == 200
    )

    # 6. compile the LiteLLM config from the registry
    compiled = client.post("/api/v1/config/compile", headers=admin)
    assert compiled.status_code == 200
    assert any(m["model_name"] == "gpt" for m in compiled.json()["model_list"])

    # 7. usage endpoint responds (empty until inference flows through the proxy)
    assert client.get("/api/v1/usage", headers=admin).status_code == 200


def test_rbac_denies_non_admin(client: httpx.Client) -> None:
    org = client.post("/api/v1/orgs", headers=PLATFORM, json={"name": "RBAC Corp"})
    org_id = org.json()["id"]
    outsider = {"X-User-Id": "nobody", "X-Org-Id": org_id, "X-Org-Roles": ""}
    resp = client.post(
        "/api/v1/models",
        headers=outsider,
        json={"public_name": "x", "provider": "openai", "model": "gpt-4o"},
    )
    assert resp.status_code == 403
