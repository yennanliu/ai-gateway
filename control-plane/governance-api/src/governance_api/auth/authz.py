"""RBAC checks. Each raises 403 on failure; org-admin of the owning org is a
superset of every team-level permission within that org.
"""

from __future__ import annotations

from fastapi import HTTPException, status

from governance_api.auth.principal import ROLE_ORG_ADMIN, Principal
from governance_api.db.models import Team


def _forbid() -> None:
    raise HTTPException(status.HTTP_403_FORBIDDEN, detail="insufficient permissions")


def is_org_admin_of(principal: Principal, org_id: str) -> bool:
    return principal.org_id == org_id and principal.has_org_role(ROLE_ORG_ADMIN)


def require_can_create_org(principal: Principal) -> None:
    """Creating a brand-new org is a platform-level org-admin action."""
    if not principal.has_org_role(ROLE_ORG_ADMIN):
        _forbid()


def require_org_role(principal: Principal, org_id: str, *allowed: str) -> None:
    if principal.org_id == org_id and principal.has_org_role(*allowed):
        return
    _forbid()


def require_org_member(principal: Principal, org_id: str) -> None:
    if principal.org_id == org_id:
        return
    _forbid()


def require_team_role(principal: Principal, team: Team, *allowed: str) -> None:
    if is_org_admin_of(principal, team.org_id):
        return
    if principal.team_role(team.id) in allowed:
        return
    _forbid()
