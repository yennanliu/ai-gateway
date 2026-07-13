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


@dataclass(frozen=True)
class AuthContext:
    key_id: str
    team_id: str
    org_id: str
    allowed_models: list[str]


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
        raise AuthError(f"model '{requested_model}' is not allowed for this key")
    team = session.get(Team, key.team_id)
    return AuthContext(
        key_id=key.id,
        team_id=key.team_id,
        org_id=team.org_id if team else "",
        allowed_models=list(key.allowed_models),
    )


def _default_session_factory() -> Session:
    from governance_api.db.session import SessionLocal

    return SessionLocal()


# Overridable in tests.
open_session: Callable[[], Session] = _default_session_factory


async def user_api_key_auth(request: object, api_key: str):  # noqa: ANN201 - LiteLLM type
    """LiteLLM custom-auth entrypoint. Returns UserAPIKeyAuth or raises 401."""
    from fastapi import HTTPException
    from litellm.proxy._types import UserAPIKeyAuth

    session = open_session()
    try:
        ctx = authenticate(session, api_key)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    finally:
        session.close()
    # Carry our scope onto the auth object so the success-callback can attribute
    # usage back to our org/team/key. LiteLLM surfaces org_id/team_id/key_alias in
    # the logging metadata (user_api_key_*); `key_alias` carries OUR internal key
    # id (not LiteLLM's hashed token). `metadata` is a belt-and-braces fallback.
    # See doc/metering-writeback.md.
    return UserAPIKeyAuth(
        api_key=api_key,
        team_id=ctx.team_id,
        org_id=ctx.org_id,
        key_alias=ctx.key_id,
        metadata={
            "aigw_key_id": ctx.key_id,
            "aigw_org_id": ctx.org_id,
            "aigw_team_id": ctx.team_id,
        },
    )
