"""Compile a LiteLLM config from the control-plane DB into a local file.

Used by the data plane at startup on deployments where there is no shared
filesystem (e.g. AWS/ECS): the proxy self-generates its config from the shared
source-of-truth DB into container-local storage, then loads it. The registry
(DB) stays the source of truth; the YAML is a derived artifact (system-design
§9). Because each task recompiles at boot, rolling the data plane
(`--force-new-deployment`) is all that's needed to pick up registry changes.

Compiles across ALL active model deployments (every org), so one proxy fleet
serves every tenant. Set ``AIGW_ORG_ID`` to restrict to a single org.

Writes to ``settings.litellm_config_path`` (``AIGW_LITELLM_CONFIG_PATH``).
"""

from __future__ import annotations

import os
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from governance_api.config import settings
from governance_api.db.models import ModelDeployment, ProviderCredential
from governance_api.db.session import SessionLocal
from governance_api.services.config_compiler import compile_config, compile_for_org, write_config

# On a cold deploy the data plane can start before the DB accepts connections
# OR before the control plane has finished migrating (so the tables the compile
# reads don't exist yet). Both surface as DBAPIError subclasses — OperationalError
# for connection refusal, ProgrammingError for a missing relation — so retry a few
# times (exponential backoff) before giving up to the template.
_MAX_ATTEMPTS = 5


def _compile() -> dict[str, Any]:
    org_id = os.environ.get("AIGW_ORG_ID")
    with SessionLocal() as session:
        session.execute(select(1))  # readiness probe — raises if the DB isn't accepting connections
        if org_id:
            return compile_for_org(session, org_id)
        # Whole-fleet config: every active deployment across every org, with all
        # provider secret refs. Routing uses the compiler defaults (per-org
        # fallback policies are a multi-tenant concern — see
        # doc/aws-cdk-deployment.md §"Running this as a SaaS product").
        deployments = list(session.execute(select(ModelDeployment)).scalars())
        secret_refs = {
            cred.id: cred.secret_ref
            for cred in session.execute(select(ProviderCredential)).scalars()
        }
        return compile_config(deployments, secret_refs=secret_refs)


def main() -> None:
    for attempt in range(_MAX_ATTEMPTS):
        try:
            config = _compile()
            break
        except DBAPIError:
            if attempt == _MAX_ATTEMPTS - 1:
                raise
            delay = 2**attempt
            print(f"database not ready, retrying in {delay}s ...")
            time.sleep(delay)
    write_config(config, settings.litellm_config_path)
    print(f"compiled {len(config['model_list'])} model(s) -> {settings.litellm_config_path}")


if __name__ == "__main__":
    main()
