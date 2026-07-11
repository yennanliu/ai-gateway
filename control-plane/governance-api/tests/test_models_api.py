"""M6 backend: model registry + provider credential endpoints."""

from __future__ import annotations

from collections.abc import Callable

from factories import bare, make_org, org_admin
from httpx import AsyncClient
from sqlalchemy.orm import Session

from governance_api.auth.principal import Principal

Setter = Callable[[Principal], None]


async def test_model_crud_lifecycle(client: AsyncClient, as_principal: Setter, db: Session) -> None:
    org = make_org(db)
    db.commit()
    as_principal(org_admin(org.id))

    cred = await client.post(
        "/api/v1/provider-credentials", json={"provider": "openai", "secret_ref": "OPENAI_API_KEY"}
    )
    assert cred.status_code == 201

    created = await client.post(
        "/api/v1/models",
        json={
            "public_name": "gpt",
            "provider": "openai",
            "model": "gpt-4o",
            "routing_tags": ["fast"],
        },
    )
    assert created.status_code == 201
    model_id = created.json()["id"]

    listed = await client.get("/api/v1/models")
    assert listed.status_code == 200 and len(listed.json()) == 1

    patched = await client.patch(f"/api/v1/models/{model_id}", json={"status": "disabled"})
    assert patched.status_code == 200 and patched.json()["status"] == "disabled"

    deleted = await client.delete(f"/api/v1/models/{model_id}")
    assert deleted.status_code == 204


async def test_model_create_requires_org_admin(
    client: AsyncClient, as_principal: Setter, db: Session
) -> None:
    org = make_org(db)
    db.commit()
    as_principal(bare(org_id=org.id))
    resp = await client.post(
        "/api/v1/models", json={"public_name": "x", "provider": "openai", "model": "gpt-4o"}
    )
    assert resp.status_code == 403


async def test_model_duplicate_public_name_409(
    client: AsyncClient, as_principal: Setter, db: Session
) -> None:
    org = make_org(db)
    db.commit()
    as_principal(org_admin(org.id))
    body = {"public_name": "dup", "provider": "openai", "model": "gpt-4o"}
    assert (await client.post("/api/v1/models", json=body)).status_code == 201
    assert (await client.post("/api/v1/models", json=body)).status_code == 409
