"""Request/response models. Response models never expose a key secret except
the one-time issue/rotate response (KeyIssued).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

Role = Literal["org-admin", "team-admin", "developer", "billing-viewer", "auditor"]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Org -------------------------------------------------------------------


class OrgCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    plan: str = "free"
    data_region: str | None = None


class OrgUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    plan: str | None = None
    data_region: str | None = None


class OrgOut(ORMModel):
    id: str
    name: str
    plan: str
    data_region: str | None
    created_at: datetime


# --- Team ------------------------------------------------------------------


class TeamCreate(BaseModel):
    org_id: str
    name: str = Field(min_length=1, max_length=255)
    default_budget: Decimal | None = None


class TeamUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    default_budget: Decimal | None = None


class TeamOut(ORMModel):
    id: str
    org_id: str
    name: str
    default_budget: Decimal | None
    created_at: datetime


# --- User & membership -----------------------------------------------------


class UserCreate(BaseModel):
    org_id: str
    email: EmailStr
    sso_subject: str | None = None


class UserOut(ORMModel):
    id: str
    org_id: str
    email: str
    sso_subject: str | None
    status: str


class MembershipCreate(BaseModel):
    user_id: str
    team_id: str
    role: Role


class MembershipOut(ORMModel):
    user_id: str
    team_id: str
    role: str


# --- App -------------------------------------------------------------------


class AppCreate(BaseModel):
    team_id: str
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class AppOut(ORMModel):
    id: str
    team_id: str
    name: str
    description: str | None


# --- Virtual keys ----------------------------------------------------------


class KeyCreate(BaseModel):
    team_id: str
    app_id: str | None = None
    allowed_models: list[str] = Field(default_factory=list)
    budget: Decimal | None = None
    tpm_limit: int | None = Field(default=None, ge=0)
    rpm_limit: int | None = Field(default=None, ge=0)
    expires_at: datetime | None = None


class KeyOut(ORMModel):
    id: str
    prefix: str
    team_id: str
    app_id: str | None
    allowed_models: list[str]
    budget: Decimal | None
    tpm_limit: int | None
    rpm_limit: int | None
    expires_at: datetime | None
    status: str
    created_at: datetime


class KeyIssued(KeyOut):
    """Returned once on issue/rotate; includes the plaintext secret."""

    key: str


# --- Rate cards & budgets --------------------------------------------------


class RateCardUpsert(BaseModel):
    model: str
    unit: str = "1k_tokens"
    price: Decimal
    markup_pct: Decimal = Decimal("0")


class RateCardOut(ORMModel):
    id: str
    org_id: str
    model: str
    unit: str
    price: Decimal
    markup_pct: Decimal


class BudgetUpsert(BaseModel):
    scope_type: Literal["org", "team", "user", "app", "key"]
    scope_id: str
    period: Literal["daily", "monthly"] = "monthly"
    limit: Decimal
    soft_pct: int = Field(default=80, ge=0, le=100)
    hard_pct: int = Field(default=100, ge=0, le=100)


class BudgetOut(ORMModel):
    id: str
    scope_type: str
    scope_id: str
    period: str
    limit: Decimal
    soft_pct: int
    hard_pct: int
    spent: Decimal


# --- Provider credentials & model registry ---------------------------------


class ProviderCredentialCreate(BaseModel):
    provider: str = Field(min_length=1)
    secret_ref: str = Field(min_length=1)


class ProviderCredentialOut(ORMModel):
    id: str
    org_id: str
    provider: str
    secret_ref: str
    status: str


class ModelDeploymentCreate(BaseModel):
    public_name: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    api_base: str | None = None
    credential_id: str | None = None
    routing_tags: list[str] = Field(default_factory=list)
    tpm_limit: int | None = Field(default=None, ge=0)
    rpm_limit: int | None = Field(default=None, ge=0)


class ModelDeploymentUpdate(BaseModel):
    public_name: str | None = Field(default=None, min_length=1)
    model: str | None = None
    api_base: str | None = None
    credential_id: str | None = None
    routing_tags: list[str] | None = None
    tpm_limit: int | None = Field(default=None, ge=0)
    rpm_limit: int | None = Field(default=None, ge=0)
    status: str | None = None


class ModelDeploymentOut(ORMModel):
    id: str
    org_id: str
    public_name: str
    provider: str
    model: str
    api_base: str | None
    credential_id: str | None
    routing_tags: list[str]
    tpm_limit: int | None
    rpm_limit: int | None
    status: str
