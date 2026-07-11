"""M2: user + membership endpoints."""

from __future__ import annotations

from collections.abc import Callable

from factories import make_org, make_team, make_user, org_admin, team_member
from httpx import AsyncClient
from sqlalchemy.orm import Session

from governance_api.auth.principal import ROLE_DEVELOPER, ROLE_TEAM_ADMIN, Principal

Setter = Callable[[Principal], None]


async def test_create_user_and_duplicate_conflict(
    client: AsyncClient, as_principal: Setter, db: Session
) -> None:
    org = make_org(db)
    db.commit()
    as_principal(org_admin(org.id))

    first = await client.post("/api/v1/users", json={"org_id": org.id, "email": "a@acme.io"})
    assert first.status_code == 201

    dup = await client.post("/api/v1/users", json={"org_id": org.id, "email": "a@acme.io"})
    assert dup.status_code == 409


async def test_create_user_bad_email_422(
    client: AsyncClient, as_principal: Setter, db: Session
) -> None:
    org = make_org(db)
    db.commit()
    as_principal(org_admin(org.id))
    resp = await client.post("/api/v1/users", json={"org_id": org.id, "email": "not-an-email"})
    assert resp.status_code == 422


async def test_list_and_get_users(client: AsyncClient, as_principal: Setter, db: Session) -> None:
    org = make_org(db)
    user = make_user(db, org, email="member@acme.io")
    db.commit()
    as_principal(org_admin(org.id))

    listed = await client.get(f"/api/v1/users?org_id={org.id}")
    assert listed.status_code == 200 and len(listed.json()) == 1

    got = await client.get(f"/api/v1/users/{user.id}")
    assert got.status_code == 200 and got.json()["email"] == "member@acme.io"


async def test_membership_create_by_team_admin(
    client: AsyncClient, as_principal: Setter, db: Session
) -> None:
    org = make_org(db)
    team = make_team(db, org)
    user = make_user(db, org)
    db.commit()

    as_principal(team_member(org.id, team.id, ROLE_TEAM_ADMIN))
    resp = await client.post(
        "/api/v1/memberships",
        json={"user_id": user.id, "team_id": team.id, "role": ROLE_DEVELOPER},
    )
    assert resp.status_code == 201
    assert resp.json() == {"user_id": user.id, "team_id": team.id, "role": ROLE_DEVELOPER}


async def test_membership_cross_org_rejected(
    client: AsyncClient, as_principal: Setter, db: Session
) -> None:
    org_a = make_org(db, "A")
    org_b = make_org(db, "B")
    team = make_team(db, org_a)
    outsider = make_user(db, org_b)
    db.commit()

    as_principal(org_admin(org_a.id))
    resp = await client.post(
        "/api/v1/memberships",
        json={"user_id": outsider.id, "team_id": team.id, "role": ROLE_DEVELOPER},
    )
    assert resp.status_code == 400


async def test_membership_delete(client: AsyncClient, as_principal: Setter, db: Session) -> None:
    org = make_org(db)
    team = make_team(db, org)
    user = make_user(db, org)
    db.commit()
    as_principal(org_admin(org.id))
    await client.post(
        "/api/v1/memberships",
        json={"user_id": user.id, "team_id": team.id, "role": ROLE_DEVELOPER},
    )
    deleted = await client.delete(f"/api/v1/memberships/{user.id}/{team.id}")
    assert deleted.status_code == 204
    again = await client.delete(f"/api/v1/memberships/{user.id}/{team.id}")
    assert again.status_code == 404
