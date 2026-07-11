"""Budget evaluation and period reset. Pure logic over a Budget-like object."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Protocol


class BudgetLike(Protocol):
    limit: Decimal
    spent: Decimal
    soft_pct: int
    hard_pct: int
    period: str
    resets_at: datetime | None


@dataclass(frozen=True)
class BudgetStatus:
    allowed: bool
    soft_exceeded: bool
    hard_exceeded: bool


def _threshold(limit: Decimal, pct: int) -> Decimal:
    return limit * Decimal(pct) / Decimal(100)


def evaluate(budget: BudgetLike) -> BudgetStatus:
    """Whether a request is allowed and which thresholds are crossed."""
    hard = budget.spent >= _threshold(budget.limit, budget.hard_pct)
    soft = budget.spent >= _threshold(budget.limit, budget.soft_pct)
    return BudgetStatus(allowed=not hard, soft_exceeded=soft, hard_exceeded=hard)


def would_exceed_hard(budget: BudgetLike, added: Decimal) -> bool:
    return budget.spent + added > _threshold(budget.limit, budget.hard_pct)


def next_reset(now: datetime, period: str) -> datetime:
    """Start of the next daily/monthly period (UTC)."""
    start = now.astimezone(UTC) if now.tzinfo else now.replace(tzinfo=UTC)
    if period == "daily":
        day = start.replace(hour=0, minute=0, second=0, microsecond=0)
        return day + timedelta(days=1)
    if period == "monthly":
        if start.month == 12:
            return start.replace(
                year=start.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0
            )
        return start.replace(
            month=start.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0
        )
    raise ValueError(f"unknown budget period: {period!r}")


def maybe_reset(budget: BudgetLike, now: datetime) -> bool:
    """Reset spent to 0 and advance resets_at if the period has rolled over."""
    if budget.resets_at is None:
        budget.resets_at = next_reset(now, budget.period)
        return False
    reset_at = budget.resets_at
    cmp_now = now
    if reset_at.tzinfo is None and now.tzinfo is not None:
        cmp_now = now.replace(tzinfo=None)
    if cmp_now >= reset_at:
        budget.spent = Decimal("0")
        budget.resets_at = next_reset(now, budget.period)
        return True
    return False
