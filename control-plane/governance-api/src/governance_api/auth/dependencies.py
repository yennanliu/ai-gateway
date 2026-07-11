"""Principal resolution.

M2 ships a dev header shim so the API is usable via curl and fully testable;
OIDC/SAML replaces this in M6 without touching route code (same Principal).

Headers:
  X-User-Id     required
  X-Org-Id      optional
  X-Org-Roles   comma-separated org roles (e.g. "org-admin")
  X-Team-Roles  comma-separated "team_id:role" pairs (e.g. "t1:team-admin,t2:developer")
"""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from governance_api.auth.principal import Principal


def _parse_team_roles(raw: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for pair in filter(None, (p.strip() for p in raw.split(","))):
        team_id, _, role = pair.partition(":")
        if team_id and role:
            result[team_id] = role
    return result


def get_principal(request: Request) -> Principal:
    user_id = request.headers.get("X-User-Id")
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="unauthenticated")
    roles = frozenset(
        filter(None, (r.strip() for r in request.headers.get("X-Org-Roles", "").split(",")))
    )
    return Principal(
        user_id=user_id,
        org_id=request.headers.get("X-Org-Id"),
        roles=roles,
        team_roles=_parse_team_roles(request.headers.get("X-Team-Roles", "")),
    )
