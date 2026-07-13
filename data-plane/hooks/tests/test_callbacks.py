"""M4: LiteLLM CustomLogger adapter — helpers, pre-call block/pass, metering."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pytest
from fastapi import HTTPException
from hooks import callbacks
from hooks.callbacks import (
    AIGatewayLogger,
    messages_text,
    scope_from,
    scope_from_logging_metadata,
)
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from governance_api.db.models import Budget, Org, Policy, RateCard, Team, UsageRecord


@dataclass
class FakeAuth:
    team_id: str | None = None
    org_id: str | None = None
    api_key: str | None = None
    key_alias: str | None = None
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


def test_scope_from_prefers_key_alias_for_key_id() -> None:
    # key_alias carries OUR internal key id; it must win over api_key (plaintext),
    # else key-scoped budgets never match. Falls back to api_key when alias absent.
    assert scope_from(FakeAuth(api_key="plaintext", key_alias="kid-1"))["key_id"] == "kid-1"
    assert scope_from(FakeAuth(api_key="plaintext", key_alias=None))["key_id"] == "plaintext"


def test_scope_from_logging_metadata_reads_flattened_keys() -> None:
    # LiteLLM flattens the auth object into user_api_key_* keys; key_alias is OUR id.
    meta = {
        "user_api_key_org_id": "o1",
        "user_api_key_team_id": "t1",
        "user_api_key_alias": "kid-123",
    }
    assert scope_from_logging_metadata(meta) == {
        "org_id": "o1",
        "team_id": "t1",
        "key_id": "kid-123",
    }


def test_scope_from_logging_metadata_falls_back_to_auth_metadata() -> None:
    # When the flattened keys are absent, fall back to the stashed auth metadata.
    meta = {
        "user_api_key_metadata": {
            "aigw_org_id": "o2",
            "aigw_team_id": "t2",
            "aigw_key_id": "kid-456",
        }
    }
    assert scope_from_logging_metadata(meta) == {
        "org_id": "o2",
        "team_id": "t2",
        "key_id": "kid-456",
    }


def test_scope_from_logging_metadata_tolerates_non_dict() -> None:
    # Defensive: a non-dict metadata must not raise, just yield empty scope.
    for bad in (None, "nope", ["x"], 3):
        assert scope_from_logging_metadata(bad) == {  # type: ignore[arg-type]
            "org_id": None,
            "team_id": None,
            "key_id": None,
        }


async def test_pre_call_passes_clean_request(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    org, team = _org_team(db)
    monkeypatch.setattr(callbacks, "open_session", _fresh_session_factory(db))
    logger = AIGatewayLogger()
    data = {"messages": [{"role": "user", "content": "hello"}]}
    result = await logger.async_pre_call_hook(
        FakeAuth(team_id=team.id, org_id=org.id, api_key="k1"), None, data, "completion"
    )
    assert result["messages"] == [{"role": "user", "content": "hello"}]


async def test_pre_call_redacts_outbound_messages(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A pii:redact policy must rewrite the OUTBOUND messages, not a metadata copy.
    org, team = _org_team(db)
    db.add(Policy(scope_type="team", scope_id=team.id, guardrails={"input": {"pii": "redact"}}))
    db.commit()
    monkeypatch.setattr(callbacks, "open_session", _fresh_session_factory(db))
    logger = AIGatewayLogger()
    data = {"messages": [{"role": "user", "content": "email me at a@b.com"}]}
    result = await logger.async_pre_call_hook(
        FakeAuth(team_id=team.id, org_id=org.id, api_key="k1"), None, data, "completion"
    )
    content = result["messages"][0]["content"]
    assert "a@b.com" not in content
    assert "[REDACTED:email]" in content


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


async def test_pre_call_blocks_over_key_budget(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A key-scoped budget must be enforced via key_alias (our id), not api_key.
    org, team = _org_team(db)
    db.add(Budget(scope_type="key", scope_id="kid-1", limit=Decimal("5"), spent=Decimal("5")))
    db.commit()
    monkeypatch.setattr(callbacks, "open_session", _fresh_session_factory(db))
    logger = AIGatewayLogger()
    with pytest.raises(HTTPException) as exc:
        await logger.async_pre_call_hook(
            FakeAuth(team_id=team.id, org_id=org.id, api_key="plaintext", key_alias="kid-1"),
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
        # Upstream deployment; metadata.model_group is the public registry name.
        "model": "gpt-4o-mini",
        "litellm_params": {
            "metadata": {
                "user_api_key_org_id": org.id,
                "user_api_key_team_id": team.id,
                "user_api_key_alias": "kid-1",
                "model_group": "gpt-4o",
            }
        },
    }
    logger = AIGatewayLogger()
    await logger.async_log_success_event(kwargs, Resp(Usage()), None, None)

    rec = db.execute(select(UsageRecord)).scalar_one()
    # Priced against the "gpt-4o" rate card (public name), attributed to our org/key.
    assert rec.cost == Decimal("3.000000")
    assert rec.org_id == org.id
    assert rec.model == "gpt-4o"
    assert rec.key_id == "kid-1"
