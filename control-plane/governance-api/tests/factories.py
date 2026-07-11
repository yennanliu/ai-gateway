"""Terse factory helpers for arranging test data."""

from __future__ import annotations

from sqlalchemy.orm import Session

from governance_api.auth.principal import ROLE_ORG_ADMIN, Principal
from governance_api.db.models import (
    App,
    ModelDeployment,
    Org,
    ProviderCredential,
    Team,
    User,
    VirtualKey,
)


def org_admin(org_id: str, user_id: str = "admin") -> Principal:
    return Principal(user_id=user_id, org_id=org_id, roles=frozenset({ROLE_ORG_ADMIN}))


def platform_admin(user_id: str = "platform") -> Principal:
    """Org-admin role held without a bound org — can create new orgs."""
    return Principal(user_id=user_id, org_id=None, roles=frozenset({ROLE_ORG_ADMIN}))


def team_member(org_id: str, team_id: str, role: str, user_id: str = "member") -> Principal:
    return Principal(user_id=user_id, org_id=org_id, team_roles={team_id: role})


def bare(user_id: str = "nobody", org_id: str | None = None) -> Principal:
    return Principal(user_id=user_id, org_id=org_id)


def make_org(db: Session, name: str = "Acme") -> Org:
    org = Org(name=name)
    db.add(org)
    db.flush()
    return org


def make_team(db: Session, org: Org, name: str = "Platform") -> Team:
    team = Team(org_id=org.id, name=name)
    db.add(team)
    db.flush()
    return team


def make_user(db: Session, org: Org, email: str = "dev@acme.test") -> User:
    user = User(org_id=org.id, email=email)
    db.add(user)
    db.flush()
    return user


def make_app(db: Session, team: Team, name: str = "chatbot") -> App:
    app = App(team_id=team.id, name=name)
    db.add(app)
    db.flush()
    return app


def make_credential(
    db: Session, org: Org, *, provider: str = "openai", secret_ref: str = "OPENAI_API_KEY"
) -> ProviderCredential:
    cred = ProviderCredential(org_id=org.id, provider=provider, secret_ref=secret_ref)
    db.add(cred)
    db.flush()
    return cred


def make_deployment(
    db: Session,
    org: Org,
    *,
    public_name: str = "gpt",
    provider: str = "openai",
    model: str = "gpt-4o",
    api_base: str | None = None,
    credential: ProviderCredential | None = None,
    routing_tags: list[str] | None = None,
) -> ModelDeployment:
    dep = ModelDeployment(
        org_id=org.id,
        public_name=public_name,
        provider=provider,
        model=model,
        api_base=api_base,
        credential_id=credential.id if credential else None,
        routing_tags=routing_tags or [],
    )
    db.add(dep)
    db.flush()
    return dep


def make_key(
    db: Session,
    team: Team,
    *,
    app: App | None = None,
    hashed_key: str = "hash-1",
    prefix: str = "sk-ag-abcd",
    allowed_models: list[str] | None = None,
) -> VirtualKey:
    key = VirtualKey(
        team_id=team.id,
        app_id=app.id if app else None,
        hashed_key=hashed_key,
        prefix=prefix,
        allowed_models=allowed_models or [],
    )
    db.add(key)
    db.flush()
    return key
