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
    """Extract our scope fields from LiteLLM's auth object."""
    return {
        "team_id": getattr(user_api_key_dict, "team_id", None),
        "org_id": getattr(user_api_key_dict, "org_id", None),
        "key_id": getattr(user_api_key_dict, "api_key", None),
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
        scope = scope_from(
            kwargs.get("litellm_params", {}).get("metadata", {}).get("user_api_key_auth")
        )
        session = open_session()
        try:
            record_usage(
                session,
                key_id=scope["key_id"],
                team_id=scope["team_id"],
                org_id=scope["org_id"],
                model=kwargs.get("model", "unknown"),
                prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            )
            session.commit()
        finally:
            session.close()
