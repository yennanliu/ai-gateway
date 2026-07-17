"""Custom-auth: validate a virtual key against our own store.

The pure ``authenticate`` function holds all the logic and is unit-tested; the
``user_api_key_auth`` coroutine is the thin adapter LiteLLM's proxy calls (one
of the four integration seams in system-design §4.2), kept minimal so an
upstream signature change touches only this file.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from governance_api.db.models import Team, VirtualKey
from governance_api.security.keys import hash_key


class AuthError(Exception):
    """Raised when a virtual key is missing, revoked, expired, or out of scope."""


class ModelNotAllowedError(AuthError):
    """Key authenticates but is not scoped to the requested model (maps to 403)."""


@dataclass(frozen=True)
class AuthContext:
    key_id: str
    team_id: str
    org_id: str
    allowed_models: list[str]
    rpm_limit: int | None = None


def _expired(expires_at: datetime | None) -> bool:
    if expires_at is None:
        return False
    exp = expires_at
    if exp.tzinfo is not None:
        exp = exp.astimezone(UTC).replace(tzinfo=None)
    return exp < datetime.now(UTC).replace(tzinfo=None)


def authenticate(
    session: Session, plaintext: str, requested_model: str | None = None
) -> AuthContext:
    # A fully-absent credential reaches us as None/"" (LiteLLM still calls
    # custom-auth when no Authorization header is present). Treat it as an auth
    # failure (401) rather than letting hash_key(None) raise AttributeError,
    # which LiteLLM would surface as a 500. See scripts/e2e_docker_qa.sh.
    if not plaintext:
        raise AuthError("no API key provided")
    key = session.execute(
        select(VirtualKey).where(VirtualKey.hashed_key == hash_key(plaintext))
    ).scalar_one_or_none()
    if key is None:
        raise AuthError("invalid API key")
    if key.status != "active":
        raise AuthError("API key is revoked")
    if _expired(key.expires_at):
        raise AuthError("API key has expired")
    if requested_model and key.allowed_models and requested_model not in key.allowed_models:
        raise ModelNotAllowedError(f"model '{requested_model}' is not allowed for this key")
    team = session.get(Team, key.team_id)
    return AuthContext(
        key_id=key.id,
        team_id=key.team_id,
        org_id=team.org_id if team else "",
        allowed_models=list(key.allowed_models),
        rpm_limit=key.rpm_limit,
    )


def _default_session_factory() -> Session:
    from governance_api.db.session import SessionLocal

    return SessionLocal()


# Overridable in tests.
open_session: Callable[[], Session] = _default_session_factory


async def _requested_model(request: object) -> str | None:
    """Best-effort extraction of the target model from the proxy request body.

    LiteLLM hands custom-auth the raw ``fastapi.Request``. Starlette caches the
    body on first read (``request._body``), so reading it here is idempotent --
    the proxy's own later read gets the cached bytes. Any failure (no request,
    non-JSON body, missing/blank ``model``) yields ``None``, which the pure
    ``authenticate`` treats as "model unknown -> allowlist not applicable".

    We gate on Content-Type first: custom-auth runs for *every* ``/v1/*`` route,
    including large multipart uploads (``/v1/audio/transcriptions``, ``/v1/files``).
    Calling ``.json()`` on those would make Starlette buffer the whole payload into
    memory only to fail parsing -- a needless DoS surface. JSON chat/completion
    requests (where the allowlist matters) are unaffected.
    """
    headers = getattr(request, "headers", None)
    if headers is not None and hasattr(headers, "get"):
        content_type = headers.get("content-type") or headers.get("Content-Type") or ""
        if "application/json" not in content_type.lower():
            return None

    json_method = getattr(request, "json", None)
    if json_method is None:
        return None
    try:
        body = await json_method()
    except Exception:  # noqa: BLE001 - never let body parsing turn auth into a 500
        return None
    model = body.get("model") if isinstance(body, dict) else None
    return model if isinstance(model, str) and model else None


async def user_api_key_auth(request: object, api_key: str):  # noqa: ANN201 - LiteLLM type
    """LiteLLM custom-auth entrypoint. Returns UserAPIKeyAuth or raises 401/403."""
    from fastapi import HTTPException
    from litellm.proxy._types import UserAPIKeyAuth

    requested_model = await _requested_model(request)
    session = open_session()
    try:
        ctx = authenticate(session, api_key, requested_model=requested_model)
    except ModelNotAllowedError as exc:
        # Authenticated but scoped away from the requested model -> 403 (forbidden).
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except AuthError as exc:
        # Missing / invalid / revoked / expired key -> 401 (unauthenticated).
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    finally:
        session.close()
    # Carry our scope onto the auth object so the success-callback can attribute
    # usage back to our org/team/key. LiteLLM surfaces org_id/team_id/key_alias in
    # the logging metadata (user_api_key_*); `key_alias` carries OUR internal key
    # id (not LiteLLM's hashed token). `metadata` is a belt-and-braces fallback.
    # See doc/metering-writeback.md.
    # `rpm_limit` must ride on the auth object too: the pre-call hook reads it
    # from here to enforce per-key rate limits (429). Without it the rate-limit
    # leg is silently dead. See doc/metering-writeback.md / enforcement.py.
    return UserAPIKeyAuth(
        api_key=api_key,
        team_id=ctx.team_id,
        org_id=ctx.org_id,
        key_alias=ctx.key_id,
        rpm_limit=ctx.rpm_limit,
        metadata={
            "aigw_key_id": ctx.key_id,
            "aigw_org_id": ctx.org_id,
            "aigw_team_id": ctx.team_id,
        },
    )
