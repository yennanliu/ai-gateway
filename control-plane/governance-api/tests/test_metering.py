"""M4: record_usage prices requests and updates applicable budgets."""

from __future__ import annotations

from decimal import Decimal

from factories import make_org, make_team
from sqlalchemy import select
from sqlalchemy.orm import Session

from governance_api.db.models import Budget, RateCard, UsageRecord
from governance_api.services.metering import record_usage


def test_record_usage_prices_and_persists(db: Session) -> None:
    org = make_org(db)
    team = make_team(db, org)
    db.add(RateCard(org_id=org.id, model="gpt-4o", unit="1k_tokens", price=Decimal("2")))
    db.flush()

    rec = record_usage(
        db,
        key_id="k1",
        team_id=team.id,
        org_id=org.id,
        model="gpt-4o",
        prompt_tokens=1000,
        completion_tokens=500,
    )
    assert rec.cost == Decimal("3.000000")  # 1500/1000 * 2
    assert db.execute(select(UsageRecord)).scalar_one().cost == Decimal("3.000000")


def test_record_usage_updates_org_and_team_budgets(db: Session) -> None:
    org = make_org(db)
    team = make_team(db, org)
    db.add(RateCard(org_id=org.id, model="gpt-4o", unit="1k_tokens", price=Decimal("2")))
    db.add(Budget(scope_type="org", scope_id=org.id, limit=Decimal("100"), spent=Decimal("0")))
    db.add(Budget(scope_type="team", scope_id=team.id, limit=Decimal("50"), spent=Decimal("1")))
    db.flush()

    record_usage(
        db,
        key_id="k1",
        team_id=team.id,
        org_id=org.id,
        model="gpt-4o",
        prompt_tokens=1000,
        completion_tokens=0,
    )
    budgets = {b.scope_type: b.spent for b in db.execute(select(Budget)).scalars()}
    assert budgets["org"] == Decimal("2.000000")
    assert budgets["team"] == Decimal("3.000000")  # 1 + 2


def test_record_usage_no_ratecard_is_free(db: Session) -> None:
    org = make_org(db)
    rec = record_usage(
        db,
        key_id=None,
        team_id=None,
        org_id=org.id,
        model="unpriced",
        prompt_tokens=100,
        completion_tokens=100,
    )
    assert rec.cost == Decimal("0")
