"""M2: org endpoints — CRUD, RBAC, audit."""

from __future__ import annotations

from collections.abc import Callable

from factories import bare, make_org, org_admin, platform_admin
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from governance_api.auth.principal import Principal
from governance_api.db.models import AuditEvent

Setter = Callable[[Principal], None]


async def test_create_org_requires_org_admin(client: AsyncClient, as_principal: Setter) -> None:
    as_principal(bare())
    denied = await client.post("/api/v1/orgs", json={"name": "Acme"})
    assert denied.status_code == 403

    as_principal(platform_admin())
    created = await client.post("/api/v1/orgs", json={"name": "Acme"})
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "Acme" and body["plan"] == "free"


async def test_create_org_writes_audit(
    client: AsyncClient, as_principal: Setter, db: Session
) -> None:
    as_principal(platform_admin("op"))
    resp = await client.post("/api/v1/orgs", json={"name": "Audited"})
    org_id = resp.json()["id"]
    events = db.execute(select(AuditEvent)).scalars().all()
    assert [(e.actor, e.action, e.target) for e in events] == [("op", "org.create", org_id)]


async def test_create_org_validation_error(client: AsyncClient, as_principal: Setter) -> None:
    as_principal(platform_admin())
    resp = await client.post("/api/v1/orgs", json={"name": ""})
    assert resp.status_code == 422


async def test_get_org_requires_membership(
    client: AsyncClient, as_principal: Setter, db: Session
) -> None:
    org = make_org(db)
    db.commit()

    as_principal(bare(org_id="other"))
    assert (await client.get(f"/api/v1/orgs/{org.id}")).status_code == 403

    as_principal(org_admin(org.id))
    ok = await client.get(f"/api/v1/orgs/{org.id}")
    assert ok.status_code == 200 and ok.json()["id"] == org.id


async def test_get_missing_org_404(client: AsyncClient, as_principal: Setter) -> None:
    as_principal(org_admin("nope"))
    assert (await client.get("/api/v1/orgs/nope")).status_code == 404


async def test_update_and_delete_org(
    client: AsyncClient, as_principal: Setter, db: Session
) -> None:
    org = make_org(db)
    db.commit()
    as_principal(org_admin(org.id))

    patched = await client.patch(f"/api/v1/orgs/{org.id}", json={"plan": "enterprise"})
    assert patched.status_code == 200 and patched.json()["plan"] == "enterprise"

    deleted = await client.delete(f"/api/v1/orgs/{org.id}")
    assert deleted.status_code == 204
    assert (await client.get(f"/api/v1/orgs/{org.id}")).status_code == 404
