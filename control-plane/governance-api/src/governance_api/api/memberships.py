"""Membership (RBAC edge) endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from governance_api.api.deps import (
    PrincipalDep,
    SessionDep,
    flush_or_409,
    get_or_404,
)
from governance_api.api.schemas import MembershipCreate, MembershipOut
from governance_api.auth import authz
from governance_api.auth.principal import ROLE_TEAM_ADMIN
from governance_api.db.models import Membership, Team, User
from governance_api.services import audit

router = APIRouter(prefix="/api/v1/memberships", tags=["memberships"])


@router.post("", response_model=MembershipOut, status_code=status.HTTP_201_CREATED)
def create_membership(
    body: MembershipCreate, db: SessionDep, principal: PrincipalDep
) -> Membership:
    team = get_or_404(db, Team, body.team_id)
    user = get_or_404(db, User, body.user_id)
    if user.org_id != team.org_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="user and team are in different orgs"
        )
    authz.require_team_role(principal, team, ROLE_TEAM_ADMIN)
    membership = Membership(user_id=body.user_id, team_id=body.team_id, role=body.role)
    db.add(membership)
    flush_or_409(db, "membership already exists")
    audit.record(
        db,
        principal,
        "membership.create",
        target=f"{body.user_id}:{body.team_id}",
        after={"role": body.role},
    )
    return membership


@router.delete("/{user_id}/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_membership(user_id: str, team_id: str, db: SessionDep, principal: PrincipalDep) -> None:
    team = get_or_404(db, Team, team_id)
    authz.require_team_role(principal, team, ROLE_TEAM_ADMIN)
    membership = db.get(Membership, (user_id, team_id))
    if membership is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Membership not found")
    db.delete(membership)
    db.flush()
    audit.record(db, principal, "membership.delete", target=f"{user_id}:{team_id}")
