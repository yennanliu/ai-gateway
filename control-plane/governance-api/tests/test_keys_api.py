"""M2: virtual-key lifecycle — issue (plaintext once), rotate, revoke, hashing, audit."""

from __future__ import annotations

from collections.abc import Callable

from factories import bare, make_app, make_org, make_team, org_admin, team_member
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from governance_api.auth.principal import ROLE_DEVELOPER, Principal
from governance_api.db.models import AuditEvent, VirtualKey
from governance_api.security.keys import KEY_PREFIX, hash_key, verify_key

Setter = Callable[[Principal], None]


async def _issue(client: AsyncClient, team_id: str, **extra: object) -> dict:
    resp = await client.post("/api/v1/keys", json={"team_id": team_id, **extra})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_issue_returns_plaintext_and_stores_only_hash(
    client: AsyncClient, as_principal: Setter, db: Session
) -> None:
    org = make_org(db)
    team = make_team(db, org)
    db.commit()
    as_principal(org_admin(org.id))

    body = await _issue(client, team.id, allowed_models=["gpt-4o"])
    plaintext = body["key"]
    assert plaintext.startswith(KEY_PREFIX)
    assert body["prefix"] == plaintext[: len(body["prefix"])]
    assert body["status"] == "active"
    assert body["allowed_models"] == ["gpt-4o"]

    stored = db.get(VirtualKey, body["id"])
    assert stored is not None
    assert stored.hashed_key != plaintext  # never stored in plaintext
    assert stored.hashed_key == hash_key(plaintext)
    assert verify_key(plaintext, stored.hashed_key)


async def test_issue_denied_for_outsider(
    client: AsyncClient, as_principal: Setter, db: Session
) -> None:
    org = make_org(db)
    team = make_team(db, org)
    db.commit()
    as_principal(bare(org_id=org.id))
    resp = await client.post("/api/v1/keys", json={"team_id": team.id})
    assert resp.status_code == 403


async def test_developer_can_issue(client: AsyncClient, as_principal: Setter, db: Session) -> None:
    org = make_org(db)
    team = make_team(db, org)
    db.commit()
    as_principal(team_member(org.id, team.id, ROLE_DEVELOPER))
    body = await _issue(client, team.id)
    assert body["key"]


async def test_app_from_another_team_rejected(
    client: AsyncClient, as_principal: Setter, db: Session
) -> None:
    org = make_org(db)
    team = make_team(db, org, "A")
    other = make_team(db, org, "B")
    foreign_app = make_app(db, other)
    db.commit()
    as_principal(org_admin(org.id))
    resp = await client.post("/api/v1/keys", json={"team_id": team.id, "app_id": foreign_app.id})
    assert resp.status_code == 400


async def test_get_and_list_never_expose_secret(
    client: AsyncClient, as_principal: Setter, db: Session
) -> None:
    org = make_org(db)
    team = make_team(db, org)
    db.commit()
    as_principal(org_admin(org.id))
    issued = await _issue(client, team.id)

    got = await client.get(f"/api/v1/keys/{issued['id']}")
    assert got.status_code == 200 and "key" not in got.json()

    listed = await client.get(f"/api/v1/keys?team_id={team.id}")
    assert listed.status_code == 200
    assert all("key" not in k for k in listed.json())


async def test_rotate_changes_hash_and_invalidates_old(
    client: AsyncClient, as_principal: Setter, db: Session
) -> None:
    org = make_org(db)
    team = make_team(db, org)
    db.commit()
    as_principal(org_admin(org.id))
    issued = await _issue(client, team.id)
    old_plaintext = issued["key"]

    resp = await client.post(f"/api/v1/keys/{issued['id']}/rotate")
    assert resp.status_code == 200
    new_plaintext = resp.json()["key"]
    assert new_plaintext != old_plaintext

    db.expire_all()
    stored = db.get(VirtualKey, issued["id"])
    assert stored is not None
    assert verify_key(new_plaintext, stored.hashed_key)
    assert not verify_key(old_plaintext, stored.hashed_key)


async def test_revoke_sets_status(client: AsyncClient, as_principal: Setter, db: Session) -> None:
    org = make_org(db)
    team = make_team(db, org)
    db.commit()
    as_principal(org_admin(org.id))
    issued = await _issue(client, team.id)

    resp = await client.post(f"/api/v1/keys/{issued['id']}/revoke")
    assert resp.status_code == 200 and resp.json()["status"] == "revoked"


async def test_key_lifecycle_is_audited(
    client: AsyncClient, as_principal: Setter, db: Session
) -> None:
    org = make_org(db)
    team = make_team(db, org)
    db.commit()
    as_principal(org_admin(org.id, user_id="boss"))
    issued = await _issue(client, team.id)
    await client.post(f"/api/v1/keys/{issued['id']}/rotate")
    await client.post(f"/api/v1/keys/{issued['id']}/revoke")

    actions = [
        e.action
        for e in db.execute(
            select(AuditEvent).where(AuditEvent.action.like("key.%")).order_by(AuditEvent.ts)
        ).scalars()
    ]
    assert actions == ["key.issue", "key.rotate", "key.revoke"]
