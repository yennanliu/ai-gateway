"""M3: custom-auth — key validation (valid/invalid/revoked/expired/model scope)
and the LiteLLM adapter's success/reject mapping.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from hooks import auth as authmod
from hooks.auth import AuthContext, AuthError, ModelNotAllowedError, _expired, authenticate
from sqlalchemy.orm import Session, sessionmaker

from governance_api.db.models import Org, Team, VirtualKey
from governance_api.security.keys import generate_key


def _seed_key(
    db: Session,
    *,
    allowed: list[str] | None = None,
    status: str = "active",
    expires_at: datetime | None = None,
    rpm_limit: int | None = None,
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
        rpm_limit=rpm_limit,
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


def test_missing_key_raises_autherror_not_crash(db: Session) -> None:
    # Absent credential (None/"") must be an AuthError -> 401, not an
    # AttributeError from hash_key(None) that LiteLLM would surface as 500.
    for missing in ("", None):
        with pytest.raises(AuthError):
            authenticate(db, missing)  # type: ignore[arg-type]


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
    # A scoped-away model raises the typed subclass (mapped to 403 by the adapter),
    # which is still an AuthError so generic handlers keep working.
    with pytest.raises(ModelNotAllowedError, match="not allowed"):
        authenticate(db, plaintext, requested_model="claude-sonnet-5")
    assert issubclass(ModelNotAllowedError, AuthError)


def test_model_allowed(db: Session) -> None:
    plaintext, _, _ = _seed_key(db, allowed=["gpt-4o"])
    assert authenticate(db, plaintext, requested_model="gpt-4o") is not None


def test_empty_allowlist_permits_any_model(db: Session) -> None:
    plaintext, _, _ = _seed_key(db, allowed=[])
    assert authenticate(db, plaintext, requested_model="anything") is not None


def test_authenticate_carries_rpm_limit(db: Session) -> None:
    plaintext, _, _ = _seed_key(db, rpm_limit=5)
    assert authenticate(db, plaintext).rpm_limit == 5


async def test_adapter_returns_user_api_key_auth(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    plaintext, key, team = _seed_key(db, rpm_limit=7)
    monkeypatch.setattr(authmod, "open_session", lambda: sessionmaker(bind=db.get_bind())())
    result = await authmod.user_api_key_auth(None, plaintext)
    assert result.team_id == team.id
    # our scope + rpm_limit must ride on the auth object for the pre-call hook.
    assert result.key_alias == key.id
    assert result.rpm_limit == 7


class _FakeRequest:
    """Minimal stand-in for the fastapi.Request LiteLLM hands custom-auth."""

    def __init__(self, body: object, content_type: str = "application/json") -> None:
        self._body = body
        self.headers = {"content-type": content_type}

    async def json(self) -> object:
        return self._body


async def test_adapter_enforces_allowlist_from_request_body(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The gap this closes: the entrypoint must read the requested model from the
    # request body and feed it to authenticate(), or per-key allowlists are dead.
    plaintext, _, _ = _seed_key(db, allowed=["demo-gpt"])
    monkeypatch.setattr(authmod, "open_session", lambda: sessionmaker(bind=db.get_bind())())
    req = _FakeRequest({"model": "demo-claude", "messages": []})
    with pytest.raises(HTTPException) as exc:
        await authmod.user_api_key_auth(req, plaintext)
    assert exc.value.status_code == 403  # authenticated but out of scope
    assert "not allowed" in str(exc.value.detail)


async def test_adapter_skips_allowlist_for_non_json_content_type(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # custom-auth runs for large multipart uploads (audio/files) too; we must NOT
    # buffer + parse those as JSON. A non-JSON request skips the allowlist (model
    # unknown) and authenticates rather than erroring.
    plaintext, key, _ = _seed_key(db, allowed=["demo-gpt"])
    monkeypatch.setattr(authmod, "open_session", lambda: sessionmaker(bind=db.get_bind())())
    req = _FakeRequest({"model": "demo-claude"}, content_type="multipart/form-data; boundary=x")
    result = await authmod.user_api_key_auth(req, plaintext)
    assert result.key_alias == key.id  # allowlist not applied -> not a 403


async def test_adapter_allows_model_in_allowlist(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    plaintext, key, _ = _seed_key(db, allowed=["demo-gpt"])
    monkeypatch.setattr(authmod, "open_session", lambda: sessionmaker(bind=db.get_bind())())
    req = _FakeRequest({"model": "demo-gpt", "messages": []})
    result = await authmod.user_api_key_auth(req, plaintext)
    assert result.key_alias == key.id


async def test_adapter_unparsable_body_skips_allowlist(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A body we can't parse must not turn auth into a 500; the request proceeds
    # (allowlist simply not applied) rather than crashing the proxy.
    plaintext, _, _ = _seed_key(db, allowed=["demo-gpt"])
    monkeypatch.setattr(authmod, "open_session", lambda: sessionmaker(bind=db.get_bind())())

    class _BadRequest:
        async def json(self) -> object:
            raise ValueError("not JSON")

    result = await authmod.user_api_key_auth(_BadRequest(), plaintext)
    assert result is not None


async def test_adapter_rejects_bad_key_with_401(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(authmod, "open_session", lambda: sessionmaker(bind=db.get_bind())())
    with pytest.raises(HTTPException) as exc:
        await authmod.user_api_key_auth(None, "sk-ag-nope")
    assert exc.value.status_code == 401


async def test_adapter_rejects_absent_key_with_401(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No Authorization header -> LiteLLM calls custom-auth with None/"".
    monkeypatch.setattr(authmod, "open_session", lambda: sessionmaker(bind=db.get_bind())())
    for missing in ("", None):
        with pytest.raises(HTTPException) as exc:
            await authmod.user_api_key_auth(None, missing)  # type: ignore[arg-type]
        assert exc.value.status_code == 401
