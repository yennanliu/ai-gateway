"""Post-call metering: price a request, write a UsageRecord, update budgets.

Shared by the data-plane post-call hook (write per request) and billing (M5).
"""

from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from governance_api.db.models import Budget, RateCard, UsageRecord
from governance_api.domain.rating import price_request

logger = logging.getLogger("governance_api.metering")


def _applicable_budgets(db: Session, scopes: dict[str, str | None]) -> list[Budget]:
    wanted = {(stype, sid) for stype, sid in scopes.items() if sid}
    if not wanted:
        return []
    ids = [sid for _, sid in wanted]
    rows = db.execute(select(Budget).where(Budget.scope_id.in_(ids))).scalars().all()
    return [b for b in rows if (b.scope_type, b.scope_id) in wanted]


def record_usage(
    db: Session,
    *,
    key_id: str | None,
    team_id: str | None,
    org_id: str | None,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cached: bool = False,
    latency_ms: int | None = None,
    status: str = "ok",
    request_id: str | None = None,
) -> UsageRecord:
    rate_cards = (
        list(
            db.execute(
                select(RateCard).where(RateCard.org_id == org_id, RateCard.model == model)
            ).scalars()
        )
        if org_id
        else []
    )
    if rate_cards:
        cost = price_request(prompt_tokens, completion_tokens, rate_cards)
    else:
        # No RateCard for this org+model: the row is still written so usage is
        # counted, but at cost=0. Warn so silent zero-cost billing is visible
        # (a request that looks free until someone adds the rate card).
        cost = Decimal("0")
        if org_id:
            logger.warning(
                "no RateCard for org=%s model=%s; metering %s at cost=0",
                org_id,
                model,
                request_id or "<no-request-id>",
            )

    record = UsageRecord(
        key_id=key_id,
        team_id=team_id,
        org_id=org_id,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost=cost,
        cached=cached,
        latency_ms=latency_ms,
        status=status,
        request_id=request_id,
    )
    db.add(record)

    for budget in _applicable_budgets(db, {"org": org_id, "team": team_id, "key": key_id}):
        budget.spent = budget.spent + cost

    db.flush()
    return record
