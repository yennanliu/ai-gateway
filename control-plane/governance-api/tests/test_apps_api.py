"""M2: app endpoints."""

from __future__ import annotations

from collections.abc import Callable

from factories import bare, make_org, make_team, org_admin, team_member
from httpx import AsyncClient
from sqlalchemy.orm import Session

from governance_api.auth.principal import ROLE_DEVELOPER, Principal

Setter = Callable[[Principal], None]


async def test_developer_can_create_app_outsider_cannot(
    client: AsyncClient, as_principal: Setter, db: Session
) -> None:
    org = make_org(db)
    team = make_team(db, org)
    db.commit()

    as_principal(bare(org_id=org.id))
    assert (
        await client.post("/api/v1/apps", json={"team_id": team.id, "name": "bot"})
    ).status_code == 403

    as_principal(team_member(org.id, team.id, ROLE_DEVELOPER))
    created = await client.post("/api/v1/apps", json={"team_id": team.id, "name": "bot"})
    assert created.status_code == 201 and created.json()["name"] == "bot"


async def test_list_apps_requires_membership(
    client: AsyncClient, as_principal: Setter, db: Session
) -> None:
    org = make_org(db)
    team = make_team(db, org)
    db.commit()
    as_principal(org_admin(org.id))
    await client.post("/api/v1/apps", json={"team_id": team.id, "name": "bot"})

    ok = await client.get(f"/api/v1/apps?team_id={team.id}")
    assert ok.status_code == 200 and len(ok.json()) == 1

    as_principal(bare(org_id="other"))
    assert (await client.get(f"/api/v1/apps?team_id={team.id}")).status_code == 403
