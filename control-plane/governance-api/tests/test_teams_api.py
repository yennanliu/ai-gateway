"""M2: team endpoints — CRUD, RBAC, audit."""

from __future__ import annotations

from collections.abc import Callable

from factories import bare, make_org, make_team, org_admin, team_member
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from governance_api.auth.principal import ROLE_DEVELOPER, ROLE_TEAM_ADMIN, Principal
from governance_api.db.models import AuditEvent

Setter = Callable[[Principal], None]


async def test_create_team_requires_org_admin(
    client: AsyncClient, as_principal: Setter, db: Session
) -> None:
    org = make_org(db)
    db.commit()

    as_principal(bare(org_id=org.id))
    denied = await client.post("/api/v1/teams", json={"org_id": org.id, "name": "Platform"})
    assert denied.status_code == 403

    as_principal(org_admin(org.id))
    created = await client.post("/api/v1/teams", json={"org_id": org.id, "name": "Platform"})
    assert created.status_code == 201
    assert created.json()["org_id"] == org.id

    events = (
        db.execute(select(AuditEvent).where(AuditEvent.action == "team.create")).scalars().all()
    )
    assert len(events) == 1


async def test_create_team_missing_org_404(client: AsyncClient, as_principal: Setter) -> None:
    as_principal(org_admin("ghost"))
    resp = await client.post("/api/v1/teams", json={"org_id": "ghost", "name": "X"})
    assert resp.status_code == 404


async def test_team_admin_can_update_developer_cannot(
    client: AsyncClient, as_principal: Setter, db: Session
) -> None:
    org = make_org(db)
    team = make_team(db, org)
    db.commit()

    as_principal(team_member(org.id, team.id, ROLE_DEVELOPER))
    assert (await client.patch(f"/api/v1/teams/{team.id}", json={"name": "New"})).status_code == 403

    as_principal(team_member(org.id, team.id, ROLE_TEAM_ADMIN))
    ok = await client.patch(f"/api/v1/teams/{team.id}", json={"name": "New"})
    assert ok.status_code == 200 and ok.json()["name"] == "New"


async def test_delete_team_requires_org_admin(
    client: AsyncClient, as_principal: Setter, db: Session
) -> None:
    org = make_org(db)
    team = make_team(db, org)
    db.commit()

    as_principal(team_member(org.id, team.id, ROLE_TEAM_ADMIN))
    assert (await client.delete(f"/api/v1/teams/{team.id}")).status_code == 403

    as_principal(org_admin(org.id))
    assert (await client.delete(f"/api/v1/teams/{team.id}")).status_code == 204


async def test_get_team_by_member(client: AsyncClient, as_principal: Setter, db: Session) -> None:
    org = make_org(db)
    team = make_team(db, org)
    db.commit()
    as_principal(org_admin(org.id))
    ok = await client.get(f"/api/v1/teams/{team.id}")
    assert ok.status_code == 200 and ok.json()["id"] == team.id


async def test_list_teams_scoped_to_org_member(
    client: AsyncClient, as_principal: Setter, db: Session
) -> None:
    org = make_org(db)
    make_team(db, org, "A")
    make_team(db, org, "B")
    db.commit()

    as_principal(bare(org_id="elsewhere"))
    assert (await client.get(f"/api/v1/teams?org_id={org.id}")).status_code == 403

    as_principal(org_admin(org.id))
    ok = await client.get(f"/api/v1/teams?org_id={org.id}")
    assert ok.status_code == 200 and len(ok.json()) == 2
