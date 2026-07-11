"""Seed demo data for local dev: an org/team/user, a stub-backed model, a rate
card, a budget, and a freshly issued virtual key.

Idempotent for the fixed entities (find-or-create); always issues a new key.
The demo model points at a local stub provider so no real API key is needed.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from governance_api.db.base import Base
from governance_api.db.models import (
    Budget,
    Membership,
    ModelDeployment,
    Org,
    ProviderCredential,
    RateCard,
    Team,
    User,
    VirtualKey,
)
from governance_api.security.keys import generate_key

DEFAULT_STUB_URL = "http://localhost:9099"


def _get_or_create[M: Base](
    session: Session, entity: type[M], defaults: dict[str, Any], **filters: Any
) -> M:
    stmt = select(entity)
    for key, value in filters.items():
        stmt = stmt.where(getattr(entity, key) == value)
    existing = session.execute(stmt).scalar_one_or_none()
    if existing is not None:
        return existing
    obj = entity(**filters, **defaults)
    session.add(obj)
    session.flush()
    return obj


def seed(session: Session, *, stub_url: str = DEFAULT_STUB_URL) -> dict[str, Any]:
    org = _get_or_create(session, Org, {"plan": "enterprise"}, name="Demo Org")
    team = _get_or_create(session, Team, {}, org_id=org.id, name="Demo Team")
    user = _get_or_create(session, User, {}, org_id=org.id, email="demo@demo.local")
    _get_or_create(session, Membership, {"role": "team-admin"}, user_id=user.id, team_id=team.id)
    cred = _get_or_create(
        session, ProviderCredential, {"secret_ref": "STUB_KEY"}, org_id=org.id, provider="openai"
    )
    model = _get_or_create(
        session,
        ModelDeployment,
        {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "api_base": stub_url,
            "credential_id": cred.id,
        },
        org_id=org.id,
        public_name="demo-gpt",
    )
    _get_or_create(
        session,
        RateCard,
        {"price": Decimal("0.5"), "markup_pct": Decimal("0")},
        org_id=org.id,
        model="gpt-4o-mini",
        unit="1k_tokens",
    )
    _get_or_create(
        session,
        Budget,
        {"limit": Decimal("100"), "period": "monthly"},
        scope_type="team",
        scope_id=team.id,
    )

    plaintext, prefix, hashed = generate_key()
    key = VirtualKey(
        hashed_key=hashed,
        prefix=prefix,
        team_id=team.id,
        allowed_models=[model.public_name],
    )
    session.add(key)
    session.flush()

    return {
        "org_id": org.id,
        "team_id": team.id,
        "user_id": user.id,
        "model": model.public_name,
        "key_id": key.id,
        "key": plaintext,
    }
