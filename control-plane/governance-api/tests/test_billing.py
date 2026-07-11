"""M5: billing service — aggregation, invoice, CSV, alerts, rate-card upsert."""

from __future__ import annotations

from decimal import Decimal

import pytest
from factories import make_org, make_team
from sqlalchemy.orm import Session

from governance_api.db.models import Budget, UsageRecord
from governance_api.services import billing


def _usage(db: Session, org_id: str, team_id: str, model: str, cost: str, ptok: int = 10) -> None:
    db.add(
        UsageRecord(
            org_id=org_id,
            team_id=team_id,
            model=model,
            prompt_tokens=ptok,
            completion_tokens=0,
            cost=Decimal(cost),
        )
    )


def test_aggregate_by_model(db: Session) -> None:
    org = make_org(db)
    team = make_team(db, org)
    _usage(db, org.id, team.id, "gpt-4o", "2.0")
    _usage(db, org.id, team.id, "gpt-4o", "3.0")
    _usage(db, org.id, team.id, "claude", "1.0")
    db.flush()

    rows = {r.group: r for r in billing.aggregate_usage(db, org.id, group_by="model")}
    assert rows["gpt-4o"].cost == Decimal("5.0")
    assert rows["gpt-4o"].requests == 2
    assert rows["claude"].cost == Decimal("1.0")


def test_aggregate_by_team(db: Session) -> None:
    org = make_org(db)
    a = make_team(db, org, "A")
    b = make_team(db, org, "B")
    _usage(db, org.id, a.id, "gpt-4o", "4.0")
    _usage(db, org.id, b.id, "gpt-4o", "1.0")
    db.flush()
    rows = {r.group: r.cost for r in billing.aggregate_usage(db, org.id, group_by="team")}
    assert rows[a.id] == Decimal("4.0") and rows[b.id] == Decimal("1.0")


def test_aggregate_invalid_group_by(db: Session) -> None:
    org = make_org(db)
    with pytest.raises(ValueError):
        billing.aggregate_usage(db, org.id, group_by="nope")


def test_period_invoice_totals(db: Session) -> None:
    org = make_org(db)
    team = make_team(db, org)
    _usage(db, org.id, team.id, "gpt-4o", "2.5")
    _usage(db, org.id, team.id, "claude", "2.5")
    db.flush()
    inv = billing.period_invoice(db, org.id)
    assert inv["total_cost"] == Decimal("5.0")


def test_usage_csv_snapshot(db: Session) -> None:
    org = make_org(db)
    team = make_team(db, org)
    _usage(db, org.id, team.id, "gpt-4o", "2.0", ptok=10)
    db.flush()
    rows = billing.aggregate_usage(db, org.id, group_by="model")
    csv_text = billing.usage_csv(rows)
    assert csv_text.splitlines()[0] == "group,prompt_tokens,completion_tokens,cost,requests"
    assert "gpt-4o,10,0,2.000000,1" in csv_text


def test_budget_alerts(db: Session) -> None:
    org = make_org(db)
    team = make_team(db, org)
    db.add(Budget(scope_type="org", scope_id=org.id, limit=Decimal("100"), spent=Decimal("85")))
    db.add(Budget(scope_type="team", scope_id=team.id, limit=Decimal("100"), spent=Decimal("10")))
    db.flush()
    alerts = billing.budget_alerts(db, org.id)
    assert len(alerts) == 1  # only the org budget (85% >= soft 80%)
    assert alerts[0]["scope_type"] == "org" and alerts[0]["soft_exceeded"]


def test_upsert_rate_card_updates_in_place(db: Session) -> None:
    org = make_org(db)
    first = billing.upsert_rate_card(db, org.id, "gpt-4o", "1k_tokens", Decimal("2"), Decimal("0"))
    second = billing.upsert_rate_card(db, org.id, "gpt-4o", "1k_tokens", Decimal("3"), Decimal("5"))
    assert first.id == second.id and second.price == Decimal("3")
