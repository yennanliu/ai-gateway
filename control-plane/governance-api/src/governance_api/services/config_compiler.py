"""Compile our model registry into a LiteLLM proxy config.

The control plane is the source of truth; the LiteLLM config file is a derived
artifact (system-design §9). Secrets are emitted as ``os.environ/<ref>``
references so the written file never contains plaintext credentials.
"""

from __future__ import annotations

from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from governance_api.db.models import ModelDeployment, Policy, ProviderCredential

# LiteLLM custom-auth entrypoint (dotted path) our proxy loads.
CUSTOM_AUTH_PATH = "hooks.auth.user_api_key_auth"
DEFAULT_ROUTING_STRATEGY = "simple-shuffle"
DEFAULT_NUM_RETRIES = 2


def _litellm_params(dep: ModelDeployment, secret_ref: str | None) -> dict[str, Any]:
    params: dict[str, Any] = {"model": f"{dep.provider}/{dep.model}"}
    if secret_ref:
        params["api_key"] = f"os.environ/{secret_ref}"
    if dep.api_base:
        params["api_base"] = dep.api_base
    if dep.rpm_limit is not None:
        params["rpm"] = dep.rpm_limit
    if dep.tpm_limit is not None:
        params["tpm"] = dep.tpm_limit
    return params


def compile_config(
    deployments: list[ModelDeployment],
    *,
    secret_refs: dict[str, str] | None = None,
    routing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a LiteLLM config dict from active model deployments.

    ``secret_refs`` maps credential_id -> secret env-var name; ``routing`` is an
    optional org routing policy ({"strategy": ..., "fallbacks": {name: [names]}}).
    """
    secret_refs = secret_refs or {}
    routing = routing or {}

    model_list: list[dict[str, Any]] = []
    for dep in deployments:
        if dep.status != "active":
            continue
        secret_ref = secret_refs.get(dep.credential_id) if dep.credential_id else None
        model_list.append(
            {
                "model_name": dep.public_name,
                "litellm_params": _litellm_params(dep, secret_ref),
                "model_info": {"id": dep.id, "tags": dep.routing_tags},
            }
        )

    router_settings: dict[str, Any] = {
        "routing_strategy": routing.get("strategy", DEFAULT_ROUTING_STRATEGY),
        "num_retries": routing.get("num_retries", DEFAULT_NUM_RETRIES),
    }
    fallbacks = routing.get("fallbacks")
    if fallbacks:
        router_settings["fallbacks"] = [{name: targets} for name, targets in fallbacks.items()]

    return {
        "model_list": model_list,
        "router_settings": router_settings,
        "general_settings": {"custom_auth": CUSTOM_AUTH_PATH},
    }


def compile_for_org(db: Session, org_id: str) -> dict[str, Any]:
    """Compile config from an org's active deployments + routing policy."""
    deployments = list(
        db.execute(select(ModelDeployment).where(ModelDeployment.org_id == org_id)).scalars()
    )
    secret_refs = {
        cred.id: cred.secret_ref
        for cred in db.execute(
            select(ProviderCredential).where(ProviderCredential.org_id == org_id)
        ).scalars()
    }
    org_policy = db.execute(
        select(Policy).where(Policy.scope_type == "org", Policy.scope_id == org_id)
    ).scalar_one_or_none()
    routing = org_policy.routing if org_policy else None
    return compile_config(deployments, secret_refs=secret_refs, routing=routing)


def write_config(config: dict[str, Any], path: str) -> None:
    with open(path, "w") as fh:
        yaml.safe_dump(config, fh, sort_keys=False)
