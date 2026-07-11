"""Seed demo data for local dev / testing.

Creates a realistic org with multiple teams, models, keys, budgets (some over
threshold so alerts show), a guardrail/routing policy, and a spread of usage
records — so the dashboard, usage, and budgets views show real data WITHOUT
needing the LiteLLM proxy running.

Idempotent for the fixed entities (find-or-create); always issues one fresh
virtual key (returned) and seeds usage only once per org.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from governance_api.db.base import Base
from governance_api.db.models import (
    App,
    Budget,
    Membership,
    ModelDeployment,
    Org,
    Policy,
    ProviderCredential,
    RateCard,
    Team,
    UsageRecord,
    User,
    VirtualKey,
)
from governance_api.security.keys import generate_key

DEFAULT_STUB_URL = "http://localhost:9099"

# (public_name, provider, underlying model, routing tags)
_MODELS = [
    ("demo-gpt", "openai", "gpt-4o-mini", []),
    ("demo-gpt-4o", "openai", "gpt-4o", ["premium"]),
    ("demo-claude", "anthropic", "claude-sonnet-5", ["long-context", "vision"]),
]


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


def _seed_usage(session: Session, org_id: str, teams: list[Team]) -> int:
    """Deterministic spread of usage over the last 5 days (once per org)."""
    already = session.execute(
        select(UsageRecord).where(UsageRecord.org_id == org_id).limit(1)
    ).first()
    if already:
        return 0
    now = datetime.now(UTC)
    count = 0
    for day in range(5):
        for i, (public_name, _, _, _) in enumerate(_MODELS):
            team = teams[i % len(teams)]
            for rep in range(2):  # two calls per model per day
                factor = day + 1
                session.add(
                    UsageRecord(
                        ts=now - timedelta(days=day, hours=i, minutes=rep),
                        org_id=org_id,
                        team_id=team.id,
                        model=public_name,
                        prompt_tokens=800 * factor,
                        completion_tokens=200 * factor,
                        cost=Decimal("0.05") * factor,
                    )
                )
                count += 1
    session.flush()
    return count


def _set_budget(session: Session, scope_type: str, scope_id: str, limit: str, spent: str) -> None:
    budget = _get_or_create(
        session,
        Budget,
        {"limit": Decimal(limit), "period": "monthly"},
        scope_type=scope_type,
        scope_id=scope_id,
    )
    budget.limit = Decimal(limit)
    budget.spent = Decimal(spent)  # force demo state each run


def seed(session: Session, *, stub_url: str = DEFAULT_STUB_URL) -> dict[str, Any]:
    org = _get_or_create(session, Org, {"plan": "enterprise"}, name="Demo Org")

    # Users
    demo = _get_or_create(session, User, {}, org_id=org.id, email="demo@demo.local")
    alice = _get_or_create(session, User, {}, org_id=org.id, email="alice@demo.local")
    bob = _get_or_create(session, User, {}, org_id=org.id, email="bob@demo.local")

    # Teams
    platform = _get_or_create(session, Team, {}, org_id=org.id, name="Platform")
    research = _get_or_create(session, Team, {}, org_id=org.id, name="Research")
    support = _get_or_create(session, Team, {}, org_id=org.id, name="Support")
    teams = [platform, research, support]

    # Memberships (RBAC)
    _get_or_create(
        session, Membership, {"role": "team-admin"}, user_id=demo.id, team_id=platform.id
    )
    _get_or_create(session, Membership, {"role": "developer"}, user_id=bob.id, team_id=platform.id)
    _get_or_create(
        session, Membership, {"role": "team-admin"}, user_id=alice.id, team_id=research.id
    )

    # Apps
    _get_or_create(
        session, App, {"description": "customer chatbot"}, team_id=platform.id, name="chatbot"
    )
    _get_or_create(
        session, App, {"description": "doc summarizer"}, team_id=research.id, name="summarizer"
    )

    # Provider credentials (secret_ref points at an env var / Vault, never plaintext)
    openai_cred = _get_or_create(
        session, ProviderCredential, {"secret_ref": "STUB_KEY"}, org_id=org.id, provider="openai"
    )
    anthropic_cred = _get_or_create(
        session, ProviderCredential, {"secret_ref": "STUB_KEY"}, org_id=org.id, provider="anthropic"
    )
    cred_by_provider = {"openai": openai_cred.id, "anthropic": anthropic_cred.id}

    # Model deployments (all point at the local stub so no real key is needed)
    for public_name, provider, model, tags in _MODELS:
        _get_or_create(
            session,
            ModelDeployment,
            {
                "provider": provider,
                "model": model,
                "api_base": stub_url,
                "credential_id": cred_by_provider[provider],
                "routing_tags": tags,
            },
            org_id=org.id,
            public_name=public_name,
        )

    # Rate cards (keyed by public name so metered usage prices correctly)
    _get_or_create(
        session,
        RateCard,
        {"price": Decimal("0.5")},
        org_id=org.id,
        model="demo-gpt",
        unit="1k_tokens",
    )
    _get_or_create(
        session,
        RateCard,
        {"price": Decimal("2.5")},
        org_id=org.id,
        model="demo-gpt-4o",
        unit="input_1k_tokens",
    )
    _get_or_create(
        session,
        RateCard,
        {"price": Decimal("10")},
        org_id=org.id,
        model="demo-gpt-4o",
        unit="output_1k_tokens",
    )
    _get_or_create(
        session,
        RateCard,
        {"price": Decimal("3")},
        org_id=org.id,
        model="demo-claude",
        unit="1k_tokens",
    )

    # Org-scoped guardrail + routing policy
    _get_or_create(
        session,
        Policy,
        {
            "guardrails": {"input": {"pii": "redact", "injection": "block"}, "fail": "closed"},
            "routing": {"strategy": "simple-shuffle", "fallbacks": {"demo-gpt-4o": ["demo-gpt"]}},
        },
        scope_type="org",
        scope_id=org.id,
    )

    # Budgets — org under, Platform near soft (88/100), Research over (60/60 -> alert)
    _set_budget(session, "org", org.id, "1000", "420")
    _set_budget(session, "team", platform.id, "100", "88")
    _set_budget(session, "team", research.id, "60", "60")

    # Every team gets a persistent key (created once) so the Keys page has data
    for team in teams:
        has_key = session.execute(
            select(VirtualKey).where(VirtualKey.team_id == team.id).limit(1)
        ).first()
        if not has_key:
            _, prefix, hashed = generate_key()
            session.add(
                VirtualKey(hashed_key=hashed, prefix=prefix, team_id=team.id, allowed_models=[])
            )
    session.flush()

    usage_rows = _seed_usage(session, org.id, teams)

    # One fresh key for the primary team, returned in plaintext (shown once)
    plaintext, prefix, hashed = generate_key()
    key = VirtualKey(
        hashed_key=hashed,
        prefix=prefix,
        team_id=platform.id,
        allowed_models=["demo-gpt", "demo-gpt-4o"],
    )
    session.add(key)
    session.flush()

    return {
        "org_id": org.id,
        "team_id": platform.id,
        "user_id": demo.id,
        "model": "demo-gpt",
        "key_id": key.id,
        "key": plaintext,
        "counts": {
            "teams": len(teams),
            "models": len(_MODELS),
            "usage_rows_added": usage_rows,
        },
    }
