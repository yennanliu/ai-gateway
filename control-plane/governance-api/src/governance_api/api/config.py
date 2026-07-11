"""Config endpoints: compile the LiteLLM config from the registry, request reload.

Registry -> config compiler -> file -> proxy hot-reload (system-design §9, §10).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status

from governance_api.api.deps import PrincipalDep, SessionDep
from governance_api.auth import authz
from governance_api.auth.principal import ROLE_ORG_ADMIN, Principal
from governance_api.config import settings
from governance_api.services import audit
from governance_api.services.config_compiler import compile_for_org, write_config

router = APIRouter(prefix="/api/v1/config", tags=["config"])


def _require_org_admin(principal: Principal) -> str:
    if principal.org_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="no org context")
    authz.require_org_role(principal, principal.org_id, ROLE_ORG_ADMIN)
    return principal.org_id


@router.post("/compile")
def compile_config(db: SessionDep, principal: PrincipalDep) -> dict[str, Any]:
    """Compile and write the LiteLLM config for the caller's org."""
    org_id = _require_org_admin(principal)
    config = compile_for_org(db, org_id)
    write_config(config, settings.litellm_config_path)
    audit.record(
        db,
        principal,
        "config.compile",
        target=org_id,
        after={"models": len(config["model_list"])},
    )
    return config


@router.post("/reload", status_code=status.HTTP_202_ACCEPTED)
def reload_config(db: SessionDep, principal: PrincipalDep) -> dict[str, str]:
    """Request a proxy hot-reload. The signal mechanism is deployment-specific
    (SIGHUP / rolling restart) and wired in M8; here we record the intent."""
    org_id = _require_org_admin(principal)
    audit.record(db, principal, "config.reload", target=org_id)
    return {"status": "reload requested"}
