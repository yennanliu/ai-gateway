"""M3: custom-auth — key validation (valid/invalid/revoked/expired/model scope)
and the LiteLLM adapter's success/reject mapping.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from hooks import auth as authmod
from hooks.auth import AuthContext, AuthError, _expired, authenticate
from sqlalchemy.orm import Session, sessionmaker

from governance_api.db.models import Org, Team, VirtualKey
from governance_api.security.keys import generate_key


def _seed_key(
    db: Session,
    *,
    allowed: list[str] | None = None,
    status: str = "active",
    expires_at: datetime | None = None,
) -> tuple[str, VirtualKey, Team]:
    org = Org(name="o")
    db.add(org)
    db.flush()
    team = Team(org_id=org.id, name="t")
    db.add(team)
    db.flush()
    plaintext, prefix, hashed = generate_key()
    key = VirtualKey(
        hashed_key=hashed,
        prefix=prefix,
        team_id=team.id,
        allowed_models=allowed or [],
        status=status,
        expires_at=expires_at,
    )
    db.add(key)
    db.commit()
    return plaintext, key, team


def test_expired_helper_handles_aware_naive_and_none() -> None:
    assert _expired(None) is False
    assert _expired(datetime.now(UTC) - timedelta(hours=1)) is True  # aware, past
    assert _expired(datetime.now(UTC) + timedelta(hours=1)) is False  # aware, future
    assert _expired(datetime(2000, 1, 1)) is True  # naive, past


def test_authenticate_valid(db: Session) -> None:
    plaintext, key, team = _seed_key(db)
    ctx = authenticate(db, plaintext)
    assert isinstance(ctx, AuthContext)
    assert ctx.key_id == key.id and ctx.team_id == team.id and ctx.org_id == team.org_id


def test_invalid_key_rejected(db: Session) -> None:
    with pytest.raises(AuthError):
        authenticate(db, "sk-ag-does-not-exist")


def test_revoked_key_rejected(db: Session) -> None:
    plaintext, _, _ = _seed_key(db, status="revoked")
    with pytest.raises(AuthError, match="revoked"):
        authenticate(db, plaintext)


def test_expired_key_rejected(db: Session) -> None:
    plaintext, _, _ = _seed_key(db, expires_at=datetime.now(UTC) - timedelta(days=1))
    with pytest.raises(AuthError, match="expired"):
        authenticate(db, plaintext)


def test_future_expiry_allowed(db: Session) -> None:
    plaintext, _, _ = _seed_key(db, expires_at=datetime.now(UTC) + timedelta(days=1))
    assert authenticate(db, plaintext) is not None


def test_model_not_allowed(db: Session) -> None:
    plaintext, _, _ = _seed_key(db, allowed=["gpt-4o"])
    with pytest.raises(AuthError, match="not allowed"):
        authenticate(db, plaintext, requested_model="claude-sonnet-5")


def test_model_allowed(db: Session) -> None:
    plaintext, _, _ = _seed_key(db, allowed=["gpt-4o"])
    assert authenticate(db, plaintext, requested_model="gpt-4o") is not None


def test_empty_allowlist_permits_any_model(db: Session) -> None:
    plaintext, _, _ = _seed_key(db, allowed=[])
    assert authenticate(db, plaintext, requested_model="anything") is not None


async def test_adapter_returns_user_api_key_auth(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    plaintext, _, team = _seed_key(db)
    monkeypatch.setattr(authmod, "open_session", lambda: sessionmaker(bind=db.get_bind())())
    result = await authmod.user_api_key_auth(None, plaintext)
    assert result.team_id == team.id


async def test_adapter_rejects_bad_key_with_401(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(authmod, "open_session", lambda: sessionmaker(bind=db.get_bind())())
    with pytest.raises(HTTPException) as exc:
        await authmod.user_api_key_auth(None, "sk-ag-nope")
    assert exc.value.status_code == 401
