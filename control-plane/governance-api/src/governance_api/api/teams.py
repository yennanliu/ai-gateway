"""Team endpoints."""

from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy import select

from governance_api.api.deps import PrincipalDep, SessionDep, get_or_404
from governance_api.api.schemas import TeamCreate, TeamOut, TeamUpdate
from governance_api.auth import authz
from governance_api.auth.principal import ROLE_ORG_ADMIN, ROLE_TEAM_ADMIN
from governance_api.db.models import Org, Team
from governance_api.services import audit

router = APIRouter(prefix="/api/v1/teams", tags=["teams"])


@router.post("", response_model=TeamOut, status_code=status.HTTP_201_CREATED)
def create_team(body: TeamCreate, db: SessionDep, principal: PrincipalDep) -> Team:
    authz.require_org_role(principal, body.org_id, ROLE_ORG_ADMIN)
    get_or_404(db, Org, body.org_id)
    team = Team(org_id=body.org_id, name=body.name, default_budget=body.default_budget)
    db.add(team)
    db.flush()
    audit.record(db, principal, "team.create", target=team.id, after=body.model_dump(mode="json"))
    return team


@router.get("", response_model=list[TeamOut])
def list_teams(org_id: str, db: SessionDep, principal: PrincipalDep) -> list[Team]:
    authz.require_org_member(principal, org_id)
    return list(db.execute(select(Team).where(Team.org_id == org_id)).scalars())


@router.get("/{team_id}", response_model=TeamOut)
def get_team(team_id: str, db: SessionDep, principal: PrincipalDep) -> Team:
    team = get_or_404(db, Team, team_id)
    authz.require_org_member(principal, team.org_id)
    return team


@router.patch("/{team_id}", response_model=TeamOut)
def update_team(team_id: str, body: TeamUpdate, db: SessionDep, principal: PrincipalDep) -> Team:
    team = get_or_404(db, Team, team_id)
    authz.require_team_role(principal, team, ROLE_TEAM_ADMIN)
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(team, field, value)
    db.flush()
    audit.record(
        db,
        principal,
        "team.update",
        target=team.id,
        after=body.model_dump(mode="json", exclude_unset=True),
    )
    return team


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_team(team_id: str, db: SessionDep, principal: PrincipalDep) -> None:
    team = get_or_404(db, Team, team_id)
    authz.require_org_role(principal, team.org_id, ROLE_ORG_ADMIN)
    db.delete(team)
    db.flush()
    audit.record(db, principal, "team.delete", target=team_id)
