"""Pre-call enforcement: budgets, rate limits, and input guardrails.

Orchestrates the domain logic against our store + a rate counter and raises a
typed Blocked (mapped to an HTTP status by the LiteLLM adapter). Returns the
(possibly redacted) input text on success.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from governance_api.db.models import Budget, Policy
from governance_api.domain.budgets import evaluate, maybe_reset
from governance_api.domain.scoping import ScopeContext, resolve_scoped
from hooks.guardrails.runner import run as run_guardrails
from hooks.ratelimit import RateCounter, check_rate


class Blocked(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _scope_pairs(ctx: ScopeContext) -> dict[str, str | None]:
    return {
        "org": ctx.org_id,
        "team": ctx.team_id,
        "user": ctx.user_id,
        "app": ctx.app_id,
        "key": ctx.key_id,
    }


def applicable_budgets(db: Session, ctx: ScopeContext) -> list[Budget]:
    wanted = {(t, i) for t, i in _scope_pairs(ctx).items() if i}
    if not wanted:
        return []
    ids = [i for _, i in wanted]
    rows = db.execute(select(Budget).where(Budget.scope_id.in_(ids))).scalars().all()
    return [b for b in rows if (b.scope_type, b.scope_id) in wanted]


def resolve_policy(db: Session, ctx: ScopeContext) -> Policy | None:
    ids = [i for i in _scope_pairs(ctx).values() if i]
    if not ids:
        return None
    rows = list(db.execute(select(Policy).where(Policy.scope_id.in_(ids))).scalars())
    return resolve_scoped(rows, ctx)


def enforce_pre_call(
    db: Session,
    counter: RateCounter,
    ctx: ScopeContext,
    *,
    input_text: str,
    now: datetime,
    rpm_limit: int | None = None,
) -> str:
    """Raise Blocked if the request is over budget, rate-limited, or fails an
    input guardrail. Returns the (possibly redacted) input text otherwise."""
    for budget in applicable_budgets(db, ctx):
        maybe_reset(budget, now)
        if not evaluate(budget).allowed:
            raise Blocked(402, "budget exceeded")

    if (
        rpm_limit is not None
        and ctx.key_id is not None
        and not check_rate(counter, f"rpm:{ctx.key_id}", rpm_limit, 1, now.timestamp())
    ):
        raise Blocked(429, "rate limit exceeded")

    policy = resolve_policy(db, ctx)
    if policy is not None:
        outcome = run_guardrails("input", policy.guardrails, input_text)
        if not outcome.allowed:
            raise Blocked(400, f"blocked by guardrail: {', '.join(outcome.reasons)}")
        return outcome.text
    return input_text
