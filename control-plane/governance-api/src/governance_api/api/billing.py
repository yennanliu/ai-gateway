"""Billing & usage endpoints: aggregated usage, invoices, CSV export, budget
alerts, plus rate-card and budget management.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select

from governance_api.api.deps import PrincipalDep, SessionDep
from governance_api.api.schemas import (
    BudgetOut,
    BudgetUpsert,
    RateCardOut,
    RateCardUpsert,
)
from governance_api.auth import authz
from governance_api.auth.principal import ROLE_BILLING_VIEWER, ROLE_ORG_ADMIN, Principal
from governance_api.db.models import Budget, RateCard
from governance_api.services import audit, billing

router = APIRouter(prefix="/api/v1", tags=["billing"])

_READ_ROLES = (ROLE_ORG_ADMIN, ROLE_BILLING_VIEWER)


def _org_for(principal: Principal, *allowed: str) -> str:
    if principal.org_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="no org context")
    authz.require_org_role(principal, principal.org_id, *allowed)
    return principal.org_id


@router.get("/usage")
def get_usage(
    db: SessionDep,
    principal: PrincipalDep,
    group_by: str = "model",
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: datetime | None = None,
) -> list[dict[str, Any]]:
    org_id = _org_for(principal, *_READ_ROLES)
    try:
        rows = billing.aggregate_usage(db, org_id, group_by=group_by, start=from_, end=to)
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    return [
        {
            "group": r.group,
            "prompt_tokens": r.prompt_tokens,
            "completion_tokens": r.completion_tokens,
            "cost": str(r.cost),
            "requests": r.requests,
        }
        for r in rows
    ]


@router.get("/invoices")
def get_invoice(
    db: SessionDep,
    principal: PrincipalDep,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: datetime | None = None,
) -> dict[str, Any]:
    org_id = _org_for(principal, *_READ_ROLES)
    inv = billing.period_invoice(db, org_id, start=from_, end=to)
    return {
        "org_id": inv["org_id"],
        "total_cost": str(inv["total_cost"]),
        "line_items": [
            {"team_id": li["team_id"], "cost": str(li["cost"])} for li in inv["line_items"]
        ],
    }


@router.get("/exports/usage.csv")
def export_usage_csv(
    db: SessionDep,
    principal: PrincipalDep,
    group_by: str = "model",
) -> Response:
    org_id = _org_for(principal, *_READ_ROLES)
    rows = billing.aggregate_usage(db, org_id, group_by=group_by)
    return Response(content=billing.usage_csv(rows), media_type="text/csv")


@router.get("/budgets/alerts")
def get_budget_alerts(db: SessionDep, principal: PrincipalDep) -> list[dict[str, Any]]:
    org_id = _org_for(principal, *_READ_ROLES)
    return [
        {**a, "limit": str(a["limit"]), "spent": str(a["spent"])}
        for a in billing.budget_alerts(db, org_id)
    ]


@router.get("/rate-cards", response_model=list[RateCardOut])
def list_rate_cards(db: SessionDep, principal: PrincipalDep) -> list[RateCard]:
    org_id = _org_for(principal, *_READ_ROLES)
    return list(db.execute(select(RateCard).where(RateCard.org_id == org_id)).scalars())


@router.put("/rate-cards", response_model=RateCardOut)
def put_rate_card(body: RateCardUpsert, db: SessionDep, principal: PrincipalDep) -> RateCard:
    org_id = _org_for(principal, ROLE_ORG_ADMIN)
    card = billing.upsert_rate_card(db, org_id, body.model, body.unit, body.price, body.markup_pct)
    audit.record(db, principal, "ratecard.upsert", target=f"{body.model}:{body.unit}")
    return card


@router.get("/budgets", response_model=list[BudgetOut])
def list_budgets(
    db: SessionDep, principal: PrincipalDep, scope_id: str | None = None
) -> list[Budget]:
    _org_for(principal, *_READ_ROLES)
    stmt = select(Budget)
    if scope_id is not None:
        stmt = stmt.where(Budget.scope_id == scope_id)
    return list(db.execute(stmt).scalars())


@router.put("/budgets", response_model=BudgetOut)
def put_budget(body: BudgetUpsert, db: SessionDep, principal: PrincipalDep) -> Budget:
    _org_for(principal, ROLE_ORG_ADMIN)
    existing = db.execute(
        select(Budget).where(Budget.scope_type == body.scope_type, Budget.scope_id == body.scope_id)
    ).scalar_one_or_none()
    if existing is not None:
        existing.period = body.period
        existing.limit = body.limit
        existing.soft_pct = body.soft_pct
        existing.hard_pct = body.hard_pct
        db.flush()
        budget = existing
    else:
        budget = Budget(
            scope_type=body.scope_type,
            scope_id=body.scope_id,
            period=body.period,
            limit=body.limit,
            soft_pct=body.soft_pct,
            hard_pct=body.hard_pct,
        )
        db.add(budget)
        db.flush()
    audit.record(db, principal, "budget.upsert", target=f"{body.scope_type}:{body.scope_id}")
    return budget
