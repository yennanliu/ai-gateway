"""M4: LiteLLM CustomLogger adapter — helpers, pre-call block/pass, metering."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pytest
from fastapi import HTTPException
from hooks import callbacks
from hooks.callbacks import AIGatewayLogger, messages_text, scope_from
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from governance_api.db.models import Budget, Org, RateCard, Team, UsageRecord


@dataclass
class FakeAuth:
    team_id: str | None = None
    org_id: str | None = None
    api_key: str | None = None
    rpm_limit: int | None = None


def _fresh_session_factory(db: Session):  # type: ignore[no-untyped-def]
    return lambda: sessionmaker(bind=db.get_bind())()


def _org_team(db: Session) -> tuple[Org, Team]:
    org = Org(name="o")
    db.add(org)
    db.flush()
    team = Team(org_id=org.id, name="t")
    db.add(team)
    db.commit()
    return org, team


def test_messages_text_flattens() -> None:
    text = messages_text([{"role": "user", "content": "a"}, {"role": "system", "content": "b"}])
    assert text == "a\nb"


def test_scope_from_reads_fields_and_handles_none() -> None:
    assert scope_from(FakeAuth(team_id="t", org_id="o", api_key="k")) == {
        "team_id": "t",
        "org_id": "o",
        "key_id": "k",
    }
    assert scope_from(None) == {"team_id": None, "org_id": None, "key_id": None}


async def test_pre_call_passes_clean_request(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    org, team = _org_team(db)
    monkeypatch.setattr(callbacks, "open_session", _fresh_session_factory(db))
    logger = AIGatewayLogger()
    data = {"messages": [{"role": "user", "content": "hello"}]}
    result = await logger.async_pre_call_hook(
        FakeAuth(team_id=team.id, org_id=org.id, api_key="k1"), None, data, "completion"
    )
    assert result["metadata"]["aigw_input"] == "hello"


async def test_pre_call_blocks_over_budget(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    org, team = _org_team(db)
    db.add(Budget(scope_type="team", scope_id=team.id, limit=Decimal("10"), spent=Decimal("10")))
    db.commit()
    monkeypatch.setattr(callbacks, "open_session", _fresh_session_factory(db))
    logger = AIGatewayLogger()
    with pytest.raises(HTTPException) as exc:
        await logger.async_pre_call_hook(
            FakeAuth(team_id=team.id, org_id=org.id, api_key="k1"),
            None,
            {"messages": [{"role": "user", "content": "hi"}]},
            "completion",
        )
    assert exc.value.status_code == 402


async def test_success_event_records_usage(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    org, team = _org_team(db)
    db.add(RateCard(org_id=org.id, model="gpt-4o", unit="1k_tokens", price=Decimal("2")))
    db.commit()
    monkeypatch.setattr(callbacks, "open_session", _fresh_session_factory(db))

    @dataclass
    class Usage:
        prompt_tokens: int = 1000
        completion_tokens: int = 500

    @dataclass
    class Resp:
        usage: Usage

    kwargs = {
        "model": "gpt-4o",
        "litellm_params": {
            "metadata": {
                "user_api_key_auth": FakeAuth(team_id=team.id, org_id=org.id, api_key="k1")
            }
        },
    }
    logger = AIGatewayLogger()
    await logger.async_log_success_event(kwargs, Resp(Usage()), None, None)

    rec = db.execute(select(UsageRecord)).scalar_one()
    assert rec.cost == Decimal("3.000000") and rec.org_id == org.id
