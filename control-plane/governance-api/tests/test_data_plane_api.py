"""Data-plane status endpoint: surfaces the effective compiled config, RBAC-gated."""

from __future__ import annotations

from collections.abc import Callable

from factories import bare, make_deployment, make_org, org_admin
from httpx import AsyncClient
from sqlalchemy.orm import Session

from governance_api.auth.principal import Principal
from governance_api.config import COMPATIBLE_LITELLM

Setter = Callable[[Principal], None]


async def test_status_requires_org_context(client: AsyncClient, as_principal: Setter) -> None:
    as_principal(bare(org_id=None))
    assert (await client.get("/api/v1/data-plane/status")).status_code == 400


async def test_status_reports_effective_models_and_routing(
    client: AsyncClient, as_principal: Setter, db: Session
) -> None:
    org = make_org(db)
    make_deployment(db, org, public_name="gpt", provider="openai", model="gpt-4o")
    db.commit()
    as_principal(org_admin(org.id))

    resp = await client.get("/api/v1/data-plane/status")
    assert resp.status_code == 200
    body = resp.json()

    assert body["litellm_version"] == COMPATIBLE_LITELLM
    assert body["model_count"] == 1
    assert body["routing"]["routing_strategy"]  # default strategy present

    model = body["models"][0]
    assert model == {
        "model_name": "gpt",
        "provider": "openai",
        "model": "gpt-4o",
        "tags": [],
    }
    # Never surface credential material, even as an os.environ reference.
    assert "litellm_params" not in model
    assert "api_key" not in model


async def test_status_empty_registry_is_healthy(
    client: AsyncClient, as_principal: Setter, db: Session
) -> None:
    org = make_org(db)
    db.commit()
    as_principal(org_admin(org.id))

    resp = await client.get("/api/v1/data-plane/status")
    assert resp.status_code == 200
    assert resp.json()["model_count"] == 0
    assert resp.json()["models"] == []
