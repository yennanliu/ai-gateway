"""Data-plane status: surface the LiteLLM proxy's effective config up to the UI.

A read-only view of what the data plane runs — the ``model_list`` + routing the
config compiler derives from THIS org's registry (the control plane is the source
of truth; system-design §9). This is the design-aligned way to expose LiteLLM's
operational surface: we push its effective config *up* into our own console
rather than exposing LiteLLM's native admin UI (which fronts LiteLLM's own key
store, the layer we deliberately replace — see §4.1).

Live proxy liveness/readiness is polled by the UI directly from the proxy's
public ``/health/*`` endpoints through the edge, so this endpoint stays DB-only
and needs no network path to the proxy.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status

from governance_api.api.deps import PrincipalDep, SessionDep
from governance_api.config import COMPATIBLE_LITELLM
from governance_api.services.config_compiler import compile_for_org

router = APIRouter(prefix="/api/v1/data-plane", tags=["data-plane"])


def _sanitized_models(model_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Project the compiled model_list to a UI-safe shape.

    Drops ``litellm_params`` (which carries the ``os.environ/<ref>`` credential
    reference) and surfaces just what the console shows: the public name, the
    resolved provider/model, and routing tags.
    """
    models: list[dict[str, Any]] = []
    for entry in model_list:
        params = entry.get("litellm_params", {})
        target = str(params.get("model", ""))
        provider, _, model = target.partition("/")
        info = entry.get("model_info", {})
        models.append(
            {
                "model_name": entry.get("model_name"),
                "provider": provider,
                "model": model or target,
                "tags": info.get("tags", []),
            }
        )
    return models


@router.get("/status")
def data_plane_status(db: SessionDep, principal: PrincipalDep) -> dict[str, Any]:
    """The effective model_list + routing the data plane serves for this org.

    Live proxy health is polled by the UI from the proxy's own ``/health/*``
    endpoints; here we report what the registry compiles to (the config the
    proxy self-compiles at boot). Scoped to the caller's own org, so org context
    is the only gate — every org member may view their data plane's config.
    """
    if principal.org_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="no org context")
    config = compile_for_org(db, principal.org_id)
    return {
        "litellm_version": COMPATIBLE_LITELLM,
        "routing": config["router_settings"],
        "models": _sanitized_models(config["model_list"]),
        "model_count": len(config["model_list"]),
    }
