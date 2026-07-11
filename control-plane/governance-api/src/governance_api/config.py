"""Application settings.

Local-first: every value has a sensible default so the app runs on a laptop
with no external services (SQLite file, in-process cache, stubbed providers).
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AIGW_", env_file=".env", extra="ignore")

    # Datastore: SQLite by default; swap the URL for Postgres at scale.
    database_url: str = "sqlite:///./ai-gateway.db"

    # Cache: empty => in-process fallback; set a redis:// URL in production.
    redis_url: str = ""

    # Secrets provider: "env" (local dev) or "vault" (production).
    secrets_provider: str = "env"

    # Where the compiled LiteLLM config is written for the proxy to load.
    litellm_config_path: str = "./litellm.config.yaml"

    environment: str = "local"


# The LiteLLM version this build is tested against (see system-design §11).
COMPATIBLE_LITELLM = "1.91.1"


settings = Settings()
