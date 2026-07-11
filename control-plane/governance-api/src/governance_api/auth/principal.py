"""The authenticated caller and its roles.

Org-level roles (e.g. org-admin) live in ``roles`` and apply within ``org_id``.
Team-level roles (team-admin, developer) live in ``team_roles`` keyed by team id.
How a Principal is *produced* is pluggable (dev header shim now, OIDC/SAML
later); RBAC enforcement below only depends on this shape.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

ROLE_ORG_ADMIN = "org-admin"
ROLE_TEAM_ADMIN = "team-admin"
ROLE_DEVELOPER = "developer"
ROLE_BILLING_VIEWER = "billing-viewer"
ROLE_AUDITOR = "auditor"

ALL_ROLES = frozenset(
    {ROLE_ORG_ADMIN, ROLE_TEAM_ADMIN, ROLE_DEVELOPER, ROLE_BILLING_VIEWER, ROLE_AUDITOR}
)


@dataclass(frozen=True)
class Principal:
    user_id: str
    org_id: str | None = None
    roles: frozenset[str] = frozenset()
    team_roles: Mapping[str, str] = field(default_factory=dict)

    def has_org_role(self, *allowed: str) -> bool:
        return bool(self.roles.intersection(allowed))

    def team_role(self, team_id: str) -> str | None:
        return self.team_roles.get(team_id)
