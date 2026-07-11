"""App (agent/service consumer) endpoints."""

from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy import select

from governance_api.api.deps import PrincipalDep, SessionDep, get_or_404
from governance_api.api.schemas import AppCreate, AppOut
from governance_api.auth import authz
from governance_api.auth.principal import ROLE_DEVELOPER, ROLE_TEAM_ADMIN
from governance_api.db.models import App, Team
from governance_api.services import audit

router = APIRouter(prefix="/api/v1/apps", tags=["apps"])


@router.post("", response_model=AppOut, status_code=status.HTTP_201_CREATED)
def create_app(body: AppCreate, db: SessionDep, principal: PrincipalDep) -> App:
    team = get_or_404(db, Team, body.team_id)
    authz.require_team_role(principal, team, ROLE_TEAM_ADMIN, ROLE_DEVELOPER)
    app = App(team_id=body.team_id, name=body.name, description=body.description)
    db.add(app)
    db.flush()
    audit.record(db, principal, "app.create", target=app.id, after={"name": body.name})
    return app


@router.get("", response_model=list[AppOut])
def list_apps(team_id: str, db: SessionDep, principal: PrincipalDep) -> list[App]:
    team = get_or_404(db, Team, team_id)
    authz.require_org_member(principal, team.org_id)
    return list(db.execute(select(App).where(App.team_id == team_id)).scalars())
