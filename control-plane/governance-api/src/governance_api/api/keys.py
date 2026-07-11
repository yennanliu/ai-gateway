"""Virtual-key lifecycle: issue (plaintext once) -> rotate -> revoke.

Only the hash and a display prefix are ever stored; the secret is returned
exactly once on issue and rotate.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from governance_api.api.deps import (
    PrincipalDep,
    SessionDep,
    flush_or_409,
    get_or_404,
)
from governance_api.api.schemas import KeyCreate, KeyIssued, KeyOut
from governance_api.auth import authz
from governance_api.auth.principal import ROLE_DEVELOPER, ROLE_TEAM_ADMIN
from governance_api.db.models import App, Team, VirtualKey
from governance_api.security import keys as keylib
from governance_api.services import audit

router = APIRouter(prefix="/api/v1/keys", tags=["keys"])

_MANAGE_ROLES = (ROLE_TEAM_ADMIN, ROLE_DEVELOPER)


def _issued(key: VirtualKey, plaintext: str) -> KeyIssued:
    return KeyIssued(**KeyOut.model_validate(key).model_dump(), key=plaintext)


@router.post("", response_model=KeyIssued, status_code=status.HTTP_201_CREATED)
def issue_key(body: KeyCreate, db: SessionDep, principal: PrincipalDep) -> KeyIssued:
    team = get_or_404(db, Team, body.team_id)
    authz.require_team_role(principal, team, *_MANAGE_ROLES)
    if body.app_id is not None:
        app = get_or_404(db, App, body.app_id)
        if app.team_id != team.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="app belongs to another team")

    plaintext, prefix, hashed = keylib.generate_key()
    key = VirtualKey(
        hashed_key=hashed,
        prefix=prefix,
        team_id=body.team_id,
        app_id=body.app_id,
        allowed_models=body.allowed_models,
        budget=body.budget,
        tpm_limit=body.tpm_limit,
        rpm_limit=body.rpm_limit,
        expires_at=body.expires_at,
    )
    db.add(key)
    flush_or_409(db, "key collision, retry")
    audit.record(db, principal, "key.issue", target=key.id, after={"prefix": prefix})
    return _issued(key, plaintext)


@router.get("", response_model=list[KeyOut])
def list_keys(team_id: str, db: SessionDep, principal: PrincipalDep) -> list[VirtualKey]:
    team = get_or_404(db, Team, team_id)
    authz.require_org_member(principal, team.org_id)
    return list(db.execute(select(VirtualKey).where(VirtualKey.team_id == team_id)).scalars())


@router.get("/{key_id}", response_model=KeyOut)
def get_key(key_id: str, db: SessionDep, principal: PrincipalDep) -> VirtualKey:
    key = get_or_404(db, VirtualKey, key_id)
    team = get_or_404(db, Team, key.team_id)
    authz.require_org_member(principal, team.org_id)
    return key


@router.post("/{key_id}/rotate", response_model=KeyIssued)
def rotate_key(key_id: str, db: SessionDep, principal: PrincipalDep) -> KeyIssued:
    key = get_or_404(db, VirtualKey, key_id)
    team = get_or_404(db, Team, key.team_id)
    authz.require_team_role(principal, team, *_MANAGE_ROLES)
    plaintext, prefix, hashed = keylib.generate_key()
    key.hashed_key = hashed
    key.prefix = prefix
    db.flush()
    audit.record(db, principal, "key.rotate", target=key.id, after={"prefix": prefix})
    return _issued(key, plaintext)


@router.post("/{key_id}/revoke", response_model=KeyOut)
def revoke_key(key_id: str, db: SessionDep, principal: PrincipalDep) -> VirtualKey:
    key = get_or_404(db, VirtualKey, key_id)
    team = get_or_404(db, Team, key.team_id)
    authz.require_team_role(principal, team, *_MANAGE_ROLES)
    key.status = "revoked"
    db.flush()
    audit.record(db, principal, "key.revoke", target=key.id)
    return key
