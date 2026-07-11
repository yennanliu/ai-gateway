"""Usage aggregation, invoicing, CSV export, and budget alerts.

Aggregation uses portable SQLAlchemy (func.date for day-bucketing works on
SQLite; swap for date_trunc on Postgres at scale). Costs are summed in SQL and
returned as Decimal.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from governance_api.db.models import Budget, RateCard, Team, UsageRecord
from governance_api.domain.budgets import evaluate

GROUP_COLUMNS: dict[str, Any] = {
    "model": UsageRecord.model,
    "team": UsageRecord.team_id,
    "key": UsageRecord.key_id,
    "day": func.date(UsageRecord.ts),
}


@dataclass(frozen=True)
class UsageRow:
    group: str | None
    prompt_tokens: int
    completion_tokens: int
    cost: Decimal
    requests: int


def _dec(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def _time_filter(stmt: Select[Any], start: datetime | None, end: datetime | None) -> Select[Any]:
    if start is not None:
        stmt = stmt.where(UsageRecord.ts >= start)
    if end is not None:
        stmt = stmt.where(UsageRecord.ts < end)
    return stmt


def aggregate_usage(
    db: Session,
    org_id: str,
    *,
    group_by: str = "model",
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[UsageRow]:
    if group_by not in GROUP_COLUMNS:
        raise ValueError(f"invalid group_by: {group_by!r}")
    col = GROUP_COLUMNS[group_by]
    stmt = (
        select(
            col.label("group"),
            func.coalesce(func.sum(UsageRecord.prompt_tokens), 0).label("prompt_tokens"),
            func.coalesce(func.sum(UsageRecord.completion_tokens), 0).label("completion_tokens"),
            func.coalesce(func.sum(UsageRecord.cost), 0).label("cost"),
            func.count().label("requests"),
        )
        .where(UsageRecord.org_id == org_id)
        .group_by(col)
        .order_by(col)
    )
    stmt = _time_filter(stmt, start, end)
    return [
        UsageRow(
            group=row.group,
            prompt_tokens=int(row.prompt_tokens),
            completion_tokens=int(row.completion_tokens),
            cost=_dec(row.cost),
            requests=int(row.requests),
        )
        for row in db.execute(stmt).all()
    ]


def period_invoice(
    db: Session, org_id: str, *, start: datetime | None = None, end: datetime | None = None
) -> dict[str, Any]:
    by_team = aggregate_usage(db, org_id, group_by="team", start=start, end=end)
    total = sum((row.cost for row in by_team), Decimal("0"))
    return {
        "org_id": org_id,
        "total_cost": total,
        "line_items": [{"team_id": row.group, "cost": row.cost} for row in by_team],
    }


def usage_csv(rows: list[UsageRow]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["group", "prompt_tokens", "completion_tokens", "cost", "requests"])
    for row in rows:
        writer.writerow(
            [row.group, row.prompt_tokens, row.completion_tokens, row.cost, row.requests]
        )
    return buf.getvalue()


def budget_alerts(db: Session, org_id: str) -> list[dict[str, Any]]:
    """Budgets (org + its teams) currently in a soft/hard-exceeded state."""
    team_ids = list(db.execute(select(Team.id).where(Team.org_id == org_id)).scalars())
    scope_ids = [org_id, *team_ids]
    budgets = db.execute(select(Budget).where(Budget.scope_id.in_(scope_ids))).scalars()
    alerts: list[dict[str, Any]] = []
    for budget in budgets:
        status = evaluate(budget)
        if status.soft_exceeded or status.hard_exceeded:
            alerts.append(
                {
                    "scope_type": budget.scope_type,
                    "scope_id": budget.scope_id,
                    "limit": budget.limit,
                    "spent": budget.spent,
                    "soft_exceeded": status.soft_exceeded,
                    "hard_exceeded": status.hard_exceeded,
                }
            )
    return alerts


def upsert_rate_card(
    db: Session, org_id: str, model: str, unit: str, price: Decimal, markup_pct: Decimal
) -> RateCard:
    existing = db.execute(
        select(RateCard).where(
            RateCard.org_id == org_id, RateCard.model == model, RateCard.unit == unit
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.price = price
        existing.markup_pct = markup_pct
        db.flush()
        return existing
    card = RateCard(org_id=org_id, model=model, unit=unit, price=price, markup_pct=markup_pct)
    db.add(card)
    db.flush()
    return card
