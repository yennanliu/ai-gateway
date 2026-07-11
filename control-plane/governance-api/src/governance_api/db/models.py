"""ORM models — the control-plane schema (system-design §8).

Single source of truth for keys and spend. Portable types only (String ids,
JSON columns, Numeric money) so the same models run on SQLite and Postgres.
Import order here defines the metadata Alembic autogenerate sees.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from governance_api.db.base import Base

__all__ = [
    "App",
    "AuditEvent",
    "Base",
    "Budget",
    "Membership",
    "ModelDeployment",
    "Org",
    "Policy",
    "ProviderCredential",
    "RateCard",
    "Team",
    "UsageRecord",
    "User",
    "VirtualKey",
]


def _uuid() -> str:
    return uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


# --- Org hierarchy ---------------------------------------------------------


class Org(Base):
    __tablename__ = "orgs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255))
    plan: Mapped[str] = mapped_column(String(32), default="free")
    data_region: Mapped[str | None] = mapped_column(String(64), default=None)
    created_at: Mapped[datetime] = mapped_column(default=_now)

    teams: Mapped[list[Team]] = relationship(
        back_populates="org", cascade="all, delete-orphan", passive_deletes=True
    )
    users: Mapped[list[User]] = relationship(
        back_populates="org", cascade="all, delete-orphan", passive_deletes=True
    )
    provider_credentials: Mapped[list[ProviderCredential]] = relationship(
        back_populates="org", cascade="all, delete-orphan", passive_deletes=True
    )
    model_deployments: Mapped[list[ModelDeployment]] = relationship(
        back_populates="org", cascade="all, delete-orphan", passive_deletes=True
    )
    rate_cards: Mapped[list[RateCard]] = relationship(
        back_populates="org", cascade="all, delete-orphan", passive_deletes=True
    )


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    default_budget: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), default=None)
    created_at: Mapped[datetime] = mapped_column(default=_now)

    org: Mapped[Org] = relationship(back_populates="teams")
    apps: Mapped[list[App]] = relationship(
        back_populates="team", cascade="all, delete-orphan", passive_deletes=True
    )
    virtual_keys: Mapped[list[VirtualKey]] = relationship(
        back_populates="team", cascade="all, delete-orphan", passive_deletes=True
    )
    memberships: Mapped[list[Membership]] = relationship(
        back_populates="team", cascade="all, delete-orphan", passive_deletes=True
    )


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("org_id", "email", name="uq_user_org_email"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(320))
    sso_subject: Mapped[str | None] = mapped_column(String(255), default=None)
    status: Mapped[str] = mapped_column(String(32), default="active")

    org: Mapped[Org] = relationship(back_populates="users")
    memberships: Mapped[list[Membership]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


class Membership(Base):
    """RBAC edge: a user's role within a team."""

    __tablename__ = "memberships"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    team_id: Mapped[str] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(32))

    user: Mapped[User] = relationship(back_populates="memberships")
    team: Mapped[Team] = relationship(back_populates="memberships")


class App(Base):
    """An agent / service consumer within a team."""

    __tablename__ = "apps"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String(1024), default=None)

    team: Mapped[Team] = relationship(back_populates="apps")
    virtual_keys: Mapped[list[VirtualKey]] = relationship(back_populates="app")


class VirtualKey(Base):
    __tablename__ = "virtual_keys"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    hashed_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    prefix: Mapped[str] = mapped_column(String(32))
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    app_id: Mapped[str | None] = mapped_column(
        ForeignKey("apps.id", ondelete="SET NULL"), default=None
    )
    allowed_models: Mapped[list[str]] = mapped_column(JSON, default=list)
    budget: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), default=None)
    tpm_limit: Mapped[int | None] = mapped_column(default=None)
    rpm_limit: Mapped[int | None] = mapped_column(default=None)
    expires_at: Mapped[datetime | None] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(default=_now)

    team: Mapped[Team] = relationship(back_populates="virtual_keys")
    app: Mapped[App | None] = relationship(back_populates="virtual_keys")


# --- Providers & model registry -------------------------------------------


class ProviderCredential(Base):
    __tablename__ = "provider_credentials"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(64))
    secret_ref: Mapped[str] = mapped_column(String(255))  # points at Vault/KMS, never plaintext
    status: Mapped[str] = mapped_column(String(32), default="active")

    org: Mapped[Org] = relationship(back_populates="provider_credentials")
    deployments: Mapped[list[ModelDeployment]] = relationship(back_populates="credential")


class ModelDeployment(Base):
    __tablename__ = "model_deployments"
    __table_args__ = (UniqueConstraint("org_id", "public_name", name="uq_model_org_publicname"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), index=True)
    public_name: Mapped[str] = mapped_column(String(255))
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(255))
    credential_id: Mapped[str | None] = mapped_column(
        ForeignKey("provider_credentials.id", ondelete="SET NULL"), default=None
    )
    routing_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    tpm_limit: Mapped[int | None] = mapped_column(default=None)
    rpm_limit: Mapped[int | None] = mapped_column(default=None)
    cost_overrides: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    status: Mapped[str] = mapped_column(String(32), default="active")

    org: Mapped[Org] = relationship(back_populates="model_deployments")
    credential: Mapped[ProviderCredential | None] = relationship(back_populates="deployments")


# --- Policies, budgets, rating --------------------------------------------


class Policy(Base):
    """Guardrail/routing/caching policy attached at any scope level."""

    __tablename__ = "policies"
    __table_args__ = (UniqueConstraint("scope_type", "scope_id", name="uq_policy_scope"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    scope_type: Mapped[str] = mapped_column(String(16))  # org|team|user|app|key
    scope_id: Mapped[str] = mapped_column(String(32), index=True)
    guardrails: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    routing: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    caching: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Budget(Base):
    __tablename__ = "budgets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    scope_type: Mapped[str] = mapped_column(String(16))
    scope_id: Mapped[str] = mapped_column(String(32), index=True)
    period: Mapped[str] = mapped_column(String(16), default="monthly")  # daily|monthly
    limit: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    soft_pct: Mapped[int] = mapped_column(default=80)
    hard_pct: Mapped[int] = mapped_column(default=100)
    spent: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    resets_at: Mapped[datetime | None] = mapped_column(default=None)


class RateCard(Base):
    __tablename__ = "rate_cards"
    __table_args__ = (UniqueConstraint("org_id", "model", "unit", name="uq_ratecard"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), index=True)
    model: Mapped[str] = mapped_column(String(255))
    unit: Mapped[str] = mapped_column(String(32), default="1k_tokens")
    price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    markup_pct: Mapped[Decimal] = mapped_column(Numeric(9, 4), default=Decimal("0"))

    org: Mapped[Org] = relationship(back_populates="rate_cards")


# --- Append-only records ---------------------------------------------------


class UsageRecord(Base):
    """One row per inference call. Denormalized org/team for fast aggregation.

    Not FK-linked to keys: usage is retained even after a key is deleted.
    """

    __tablename__ = "usage_records"
    __table_args__ = (
        Index("ix_usage_org_ts", "org_id", "ts"),
        Index("ix_usage_team_ts", "team_id", "ts"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    ts: Mapped[datetime] = mapped_column(default=_now)
    key_id: Mapped[str | None] = mapped_column(String(32), default=None)
    team_id: Mapped[str | None] = mapped_column(String(32), default=None)
    org_id: Mapped[str | None] = mapped_column(String(32), default=None)
    model: Mapped[str] = mapped_column(String(255))
    prompt_tokens: Mapped[int] = mapped_column(default=0)
    completion_tokens: Mapped[int] = mapped_column(default=0)
    cost: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    cached: Mapped[bool] = mapped_column(default=False)
    latency_ms: Mapped[int | None] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(String(32), default="ok")
    request_id: Mapped[str | None] = mapped_column(String(64), default=None)


class AuditEvent(Base):
    """Append-only audit trail for compliance (no update/delete path)."""

    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_actor_ts", "actor", "ts"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    ts: Mapped[datetime] = mapped_column(default=_now)
    actor: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(128))
    target: Mapped[str | None] = mapped_column(String(255), default=None)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    ip: Mapped[str | None] = mapped_column(String(64), default=None)
