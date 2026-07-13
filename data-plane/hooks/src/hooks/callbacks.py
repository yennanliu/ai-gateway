"""LiteLLM CustomLogger adapter wiring our enforcement + metering into the proxy.

The LiteLLM-specific glue is kept thin; the testable logic lives in the helpers
and in enforcement/metering (unit-tested separately). Full proxy assembly is
exercised in the deploy work (M8), matching the M3 approach.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from litellm.integrations.custom_logger import CustomLogger

from governance_api.services.metering import record_usage
from hooks.auth import open_session
from hooks.enforcement import Blocked, enforce_pre_call
from hooks.ratelimit import InProcessCounter, RateCounter


def messages_text(messages: list[dict[str, Any]]) -> str:
    """Flatten chat messages to a single string for input guardrails."""
    return "\n".join(str(m.get("content", "")) for m in messages if isinstance(m, dict))


def scope_from(user_api_key_dict: Any) -> dict[str, str | None]:
    """Extract our scope fields from LiteLLM's auth object (pre-call path)."""
    return {
        "team_id": getattr(user_api_key_dict, "team_id", None),
        "org_id": getattr(user_api_key_dict, "org_id", None),
        "key_id": getattr(user_api_key_dict, "api_key", None),
    }


def scope_from_logging_metadata(meta: dict[str, Any]) -> dict[str, str | None]:
    """Extract our scope from the LiteLLM success-event logging metadata.

    LiteLLM flattens the auth object into ``user_api_key_*`` keys; we set
    ``key_alias`` to OUR internal key id in the custom-auth adapter, and stash a
    fallback copy under the auth object's own ``metadata`` (surfaced here as
    ``user_api_key_metadata`` / ``user_api_key_auth_metadata``). See
    doc/metering-writeback.md.
    """
    if not isinstance(meta, dict):
        meta = {}
    fallback = meta.get("user_api_key_metadata") or meta.get("user_api_key_auth_metadata") or {}
    if not isinstance(fallback, dict):
        fallback = {}
    return {
        "org_id": meta.get("user_api_key_org_id") or fallback.get("aigw_org_id"),
        "team_id": meta.get("user_api_key_team_id") or fallback.get("aigw_team_id"),
        "key_id": meta.get("user_api_key_alias") or fallback.get("aigw_key_id"),
    }


class AIGatewayLogger(CustomLogger):
    def __init__(self, counter: RateCounter | None = None) -> None:
        self.counter: RateCounter = counter or InProcessCounter()

    async def async_pre_call_hook(
        self, user_api_key_dict: Any, cache: Any, data: dict[str, Any], call_type: str
    ) -> dict[str, Any]:
        from fastapi import HTTPException

        from governance_api.domain.scoping import ScopeContext

        scope = scope_from(user_api_key_dict)
        ctx = ScopeContext(org_id=scope["org_id"], team_id=scope["team_id"], key_id=scope["key_id"])
        session = open_session()
        try:
            redacted = enforce_pre_call(
                session,
                self.counter,
                ctx,
                input_text=messages_text(data.get("messages", [])),
                now=datetime.now(UTC),
                rpm_limit=getattr(user_api_key_dict, "rpm_limit", None),
            )
        except Blocked as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
        finally:
            session.close()
        # Redacted input is advisory in v1; return data unmodified in shape.
        data.setdefault("metadata", {})["aigw_input"] = redacted
        return data

    async def async_log_success_event(
        self, kwargs: dict[str, Any], response_obj: Any, start_time: Any, end_time: Any
    ) -> None:
        usage = getattr(response_obj, "usage", None)
        meta = (kwargs.get("litellm_params") or {}).get("metadata")
        if not isinstance(meta, dict):
            meta = {}
        scope = scope_from_logging_metadata(meta)
        # `model_group` is the public registry name the client asked for
        # (e.g. "demo-gpt"); `kwargs["model"]` is the resolved upstream deployment
        # ("gpt-4o-mini"). Attribute usage/cost to the public name. Chain `or` so a
        # present-but-None model value still falls back to "unknown".
        model = meta.get("model_group") or kwargs.get("model") or "unknown"
        session = open_session()
        try:
            record_usage(
                session,
                key_id=scope["key_id"],
                team_id=scope["team_id"],
                org_id=scope["org_id"],
                model=model,
                prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            )
            session.commit()
        finally:
            session.close()


# Module-level CustomLogger instance the LiteLLM proxy loads via
# ``litellm_settings.callbacks`` (see services/config_compiler.py and
# doc/metering-writeback.md). This is what wires live per-request metering.
aigw_logger = AIGatewayLogger()
