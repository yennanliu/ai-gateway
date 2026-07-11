"""User endpoints."""

from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy import select

from governance_api.api.deps import (
    PrincipalDep,
    SessionDep,
    flush_or_409,
    get_or_404,
)
from governance_api.api.schemas import UserCreate, UserOut
from governance_api.auth import authz
from governance_api.auth.principal import ROLE_ORG_ADMIN
from governance_api.db.models import Org, User
from governance_api.services import audit

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(body: UserCreate, db: SessionDep, principal: PrincipalDep) -> User:
    authz.require_org_role(principal, body.org_id, ROLE_ORG_ADMIN)
    get_or_404(db, Org, body.org_id)
    user = User(org_id=body.org_id, email=str(body.email), sso_subject=body.sso_subject)
    db.add(user)
    flush_or_409(db, "user with this email already exists in org")
    audit.record(db, principal, "user.create", target=user.id, after={"email": str(body.email)})
    return user


@router.get("", response_model=list[UserOut])
def list_users(org_id: str, db: SessionDep, principal: PrincipalDep) -> list[User]:
    authz.require_org_member(principal, org_id)
    return list(db.execute(select(User).where(User.org_id == org_id)).scalars())


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: str, db: SessionDep, principal: PrincipalDep) -> User:
    user = get_or_404(db, User, user_id)
    authz.require_org_member(principal, user.org_id)
    return user
