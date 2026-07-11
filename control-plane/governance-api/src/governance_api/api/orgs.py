"""Org endpoints."""

from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy import select

from governance_api.api.deps import PrincipalDep, SessionDep, get_or_404
from governance_api.api.schemas import OrgCreate, OrgOut, OrgUpdate
from governance_api.auth import authz
from governance_api.auth.principal import ROLE_ORG_ADMIN
from governance_api.db.models import Org
from governance_api.services import audit

router = APIRouter(prefix="/api/v1/orgs", tags=["orgs"])


@router.post("", response_model=OrgOut, status_code=status.HTTP_201_CREATED)
def create_org(body: OrgCreate, db: SessionDep, principal: PrincipalDep) -> Org:
    authz.require_can_create_org(principal)
    org = Org(name=body.name, plan=body.plan, data_region=body.data_region)
    db.add(org)
    db.flush()
    audit.record(db, principal, "org.create", target=org.id, after=body.model_dump())
    return org


@router.get("", response_model=list[OrgOut])
def list_orgs(db: SessionDep, principal: PrincipalDep) -> list[Org]:
    if principal.org_id is None:
        return []
    return list(db.execute(select(Org).where(Org.id == principal.org_id)).scalars())


@router.get("/{org_id}", response_model=OrgOut)
def get_org(org_id: str, db: SessionDep, principal: PrincipalDep) -> Org:
    org = get_or_404(db, Org, org_id)
    authz.require_org_member(principal, org.id)
    return org


@router.patch("/{org_id}", response_model=OrgOut)
def update_org(org_id: str, body: OrgUpdate, db: SessionDep, principal: PrincipalDep) -> Org:
    org = get_or_404(db, Org, org_id)
    authz.require_org_role(principal, org.id, ROLE_ORG_ADMIN)
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(org, field, value)
    db.flush()
    audit.record(db, principal, "org.update", target=org.id, after=changes)
    return org


@router.delete("/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_org(org_id: str, db: SessionDep, principal: PrincipalDep) -> None:
    org = get_or_404(db, Org, org_id)
    authz.require_org_role(principal, org.id, ROLE_ORG_ADMIN)
    db.delete(org)
    db.flush()
    audit.record(db, principal, "org.delete", target=org_id)
