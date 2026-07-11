"""M5: billing endpoints — RBAC, usage/invoice/csv/alerts, rate-card & budget upsert."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

from factories import bare, make_org, make_team, org_admin
from httpx import AsyncClient
from sqlalchemy.orm import Session

from governance_api.auth.principal import ROLE_BILLING_VIEWER, Principal
from governance_api.db.models import Budget, RateCard, UsageRecord

Setter = Callable[[Principal], None]


def _billing_viewer(org_id: str) -> Principal:
    return Principal(user_id="v", org_id=org_id, roles=frozenset({ROLE_BILLING_VIEWER}))


async def test_usage_requires_billing_role(
    client: AsyncClient, as_principal: Setter, db: Session
) -> None:
    org = make_org(db)
    db.commit()
    as_principal(bare(org_id=org.id))
    assert (await client.get("/api/v1/usage")).status_code == 403


async def test_usage_aggregation_endpoint(
    client: AsyncClient, as_principal: Setter, db: Session
) -> None:
    org = make_org(db)
    team = make_team(db, org)
    db.add(
        UsageRecord(
            org_id=org.id,
            team_id=team.id,
            model="gpt-4o",
            prompt_tokens=10,
            completion_tokens=0,
            cost=Decimal("2.0"),
        )
    )
    db.commit()
    as_principal(_billing_viewer(org.id))
    resp = await client.get("/api/v1/usage?group_by=model")
    assert resp.status_code == 200
    assert resp.json() == [
        {
            "group": "gpt-4o",
            "prompt_tokens": 10,
            "completion_tokens": 0,
            "cost": "2.000000",
            "requests": 1,
        }
    ]


async def test_usage_invalid_group_by_422(
    client: AsyncClient, as_principal: Setter, db: Session
) -> None:
    org = make_org(db)
    db.commit()
    as_principal(_billing_viewer(org.id))
    assert (await client.get("/api/v1/usage?group_by=bogus")).status_code == 422


async def test_csv_export(client: AsyncClient, as_principal: Setter, db: Session) -> None:
    org = make_org(db)
    team = make_team(db, org)
    db.add(
        UsageRecord(
            org_id=org.id,
            team_id=team.id,
            model="gpt-4o",
            prompt_tokens=10,
            completion_tokens=0,
            cost=Decimal("2.0"),
        )
    )
    db.commit()
    as_principal(_billing_viewer(org.id))
    resp = await client.get("/api/v1/exports/usage.csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "group,prompt_tokens" in resp.text


async def test_rate_card_upsert_requires_admin(
    client: AsyncClient, as_principal: Setter, db: Session
) -> None:
    org = make_org(db)
    db.commit()

    as_principal(_billing_viewer(org.id))  # read-only role
    denied = await client.put("/api/v1/rate-cards", json={"model": "gpt-4o", "price": "2"})
    assert denied.status_code == 403

    as_principal(org_admin(org.id))
    ok = await client.put("/api/v1/rate-cards", json={"model": "gpt-4o", "price": "2"})
    assert ok.status_code == 200 and ok.json()["model"] == "gpt-4o"
    assert db.query(RateCard).count() == 1


async def test_budget_upsert_and_alerts(
    client: AsyncClient, as_principal: Setter, db: Session
) -> None:
    org = make_org(db)
    db.commit()
    as_principal(org_admin(org.id))

    put = await client.put(
        "/api/v1/budgets",
        json={"scope_type": "org", "scope_id": org.id, "limit": "100"},
    )
    assert put.status_code == 200

    # Push spent over soft threshold and check alerts.
    budget = db.query(Budget).one()
    budget.spent = Decimal("90")
    db.commit()

    alerts = await client.get("/api/v1/budgets/alerts")
    assert alerts.status_code == 200
    assert alerts.json()[0]["scope_id"] == org.id
