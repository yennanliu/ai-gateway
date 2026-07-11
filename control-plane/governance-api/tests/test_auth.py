"""M2: principal resolution (dev header shim) and RBAC helpers."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from httpx import AsyncClient

from governance_api.auth import authz
from governance_api.auth.dependencies import _parse_team_roles
from governance_api.auth.principal import (
    ROLE_ORG_ADMIN,
    ROLE_TEAM_ADMIN,
    Principal,
)
from governance_api.db.models import Team


def test_parse_team_roles() -> None:
    assert _parse_team_roles("t1:team-admin, t2:developer") == {
        "t1": "team-admin",
        "t2": "developer",
    }
    assert _parse_team_roles("") == {}
    assert _parse_team_roles("garbage,norole:") == {}


async def test_missing_auth_header_is_401(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/orgs")
    assert resp.status_code == 401


async def test_header_shim_builds_principal(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/orgs", headers={"X-User-Id": "u1", "X-Org-Id": "o1"})
    assert resp.status_code == 200
    assert resp.json() == []  # org o1 does not exist -> empty


def test_is_org_admin_of() -> None:
    p = Principal(user_id="u", org_id="o1", roles=frozenset({ROLE_ORG_ADMIN}))
    assert authz.is_org_admin_of(p, "o1") is True
    assert authz.is_org_admin_of(p, "o2") is False


def test_require_team_role_grants_org_admin() -> None:
    p = Principal(user_id="u", org_id="o1", roles=frozenset({ROLE_ORG_ADMIN}))
    team = Team(id="t1", org_id="o1", name="T")
    authz.require_team_role(p, team, ROLE_TEAM_ADMIN)  # no raise


def test_require_team_role_denies_outsider() -> None:
    p = Principal(user_id="u", org_id="o1", team_roles={"t2": ROLE_TEAM_ADMIN})
    team = Team(id="t1", org_id="o1", name="T")
    with pytest.raises(HTTPException) as exc:
        authz.require_team_role(p, team, ROLE_TEAM_ADMIN)
    assert exc.value.status_code == 403
