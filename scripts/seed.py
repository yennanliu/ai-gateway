#!/usr/bin/env python
"""CLI wrapper: seed demo data and compile the LiteLLM config.

Run:  uv run python scripts/seed.py
"""

from __future__ import annotations

import os

from governance_api.config import settings
from governance_api.db.session import SessionLocal
from governance_api.services.config_compiler import compile_for_org, write_config
from governance_api.services.seed import DEFAULT_STUB_URL, seed


def main() -> None:
    stub_url = os.environ.get("AIGW_STUB_URL", DEFAULT_STUB_URL)
    with SessionLocal() as session:
        result = seed(session, stub_url=stub_url)
        config = compile_for_org(session, result["org_id"])
        write_config(config, settings.litellm_config_path)
        session.commit()

    print("Seeded demo data:")
    print(f"  org:   {result['org_id']}")
    print(f"  team:  {result['team_id']}")
    print(f"  model: {result['model']}  (via stub {stub_url})")
    print(f"  key:   {result['key']}   <-- shown once")
    print(f"  litellm config -> {settings.litellm_config_path}")
    print()
    print("Try it once the proxy is running:")
    print(
        "  curl -s localhost:4000/v1/chat/completions "
        f"-H 'Authorization: Bearer {result['key']}' "
        "-H 'Content-Type: application/json' "
        '-d \'{"model":"demo-gpt","messages":[{"role":"user","content":"hi"}]}\''
    )


if __name__ == "__main__":
    main()
