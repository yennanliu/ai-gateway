"""M1: schema behavior — constraints, cascades, FK enforcement, JSON round-trips."""

from __future__ import annotations

from decimal import Decimal

import pytest
from factories import make_app, make_key, make_org, make_team, make_user
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from governance_api.db.models import (
    ModelDeployment,
    Org,
    Policy,
    Team,
    User,
    VirtualKey,
)


def test_defaults_are_populated(db: Session) -> None:
    org = make_org(db)
    assert len(org.id) == 32  # uuid4 hex
    assert org.plan == "free"
    assert org.created_at is not None


def test_unique_user_email_per_org(db: Session) -> None:
    org = make_org(db)
    make_user(db, org, email="dup@acme.test")
    with pytest.raises(IntegrityError):
        make_user(db, org, email="dup@acme.test")


def test_same_email_allowed_in_different_orgs(db: Session) -> None:
    o1, o2 = make_org(db, "One"), make_org(db, "Two")
    make_user(db, o1, email="shared@x.test")
    make_user(db, o2, email="shared@x.test")  # no error
    assert len(db.execute(select(User)).scalars().all()) == 2


def test_unique_model_public_name_per_org(db: Session) -> None:
    org = make_org(db)
    db.add(ModelDeployment(org_id=org.id, public_name="gpt", provider="openai", model="gpt-4o"))
    db.flush()
    db.add(ModelDeployment(org_id=org.id, public_name="gpt", provider="azure", model="gpt-4o"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_unique_policy_scope(db: Session) -> None:
    db.add(Policy(scope_type="team", scope_id="t1"))
    db.flush()
    db.add(Policy(scope_type="team", scope_id="t1"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_fk_enforcement_rejects_orphan_team(db: Session) -> None:
    db.add(Team(org_id="does-not-exist", name="ghost"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_cascade_delete_org_removes_children(db: Session) -> None:
    org = make_org(db)
    team = make_team(db, org)
    make_key(db, team)
    make_user(db, org)
    db.commit()

    db.delete(org)
    db.commit()

    assert db.execute(select(Team)).scalars().all() == []
    assert db.execute(select(VirtualKey)).scalars().all() == []
    assert db.execute(select(User)).scalars().all() == []


def test_deleting_app_nulls_key_app_id(db: Session) -> None:
    org = make_org(db)
    team = make_team(db, org)
    app = make_app(db, team)
    key = make_key(db, team, app=app)
    db.commit()
    assert key.app_id == app.id

    db.delete(app)
    db.commit()
    db.refresh(key)
    assert key.app_id is None  # ON DELETE SET NULL, key survives


def test_json_columns_round_trip(db: Session) -> None:
    org = make_org(db)
    team = make_team(db, org)
    key = make_key(db, team, allowed_models=["gpt-4o", "claude-sonnet-5"])
    dep = ModelDeployment(
        org_id=org.id,
        public_name="fast",
        provider="openai",
        model="gpt-4o-mini",
        routing_tags=["cheap", "vision"],
        cost_overrides={"input": "0.15", "output": "0.6"},
    )
    db.add(dep)
    db.commit()
    db.expire_all()

    reloaded_key = db.get(VirtualKey, key.id)
    reloaded_dep = db.get(ModelDeployment, dep.id)
    assert reloaded_key is not None and reloaded_key.allowed_models == ["gpt-4o", "claude-sonnet-5"]
    assert reloaded_dep is not None
    assert reloaded_dep.routing_tags == ["cheap", "vision"]
    assert reloaded_dep.cost_overrides == {"input": "0.15", "output": "0.6"}


def test_numeric_money_round_trip(db: Session) -> None:
    org = make_org(db)
    team = Team(org_id=org.id, name="Money", default_budget=Decimal("123.456789"))
    db.add(team)
    db.commit()
    db.expire_all()
    reloaded = db.get(Team, team.id)
    assert reloaded is not None
    assert Decimal(str(reloaded.default_budget)) == Decimal("123.456789")


def test_relationship_navigation(db: Session) -> None:
    org = make_org(db)
    team = make_team(db, org)
    make_key(db, team, hashed_key="h1", prefix="p1")
    make_key(db, team, hashed_key="h2", prefix="p2")
    db.commit()
    reloaded = db.get(Org, org.id)
    assert reloaded is not None
    assert len(reloaded.teams) == 1
    assert len(reloaded.teams[0].virtual_keys) == 2
