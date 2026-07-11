"""M4: budget evaluation, thresholds, and period reset."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from governance_api.domain.budgets import (
    evaluate,
    maybe_reset,
    next_reset,
    would_exceed_hard,
)


@dataclass
class B:
    limit: Decimal
    spent: Decimal
    soft_pct: int = 80
    hard_pct: int = 100
    period: str = "monthly"
    resets_at: datetime | None = None


def test_under_soft_is_clean() -> None:
    status = evaluate(B(Decimal("100"), Decimal("50")))
    assert status.allowed and not status.soft_exceeded and not status.hard_exceeded


def test_soft_threshold_alerts_but_allows() -> None:
    status = evaluate(B(Decimal("100"), Decimal("80")))
    assert status.allowed and status.soft_exceeded and not status.hard_exceeded


def test_hard_threshold_blocks() -> None:
    status = evaluate(B(Decimal("100"), Decimal("100")))
    assert not status.allowed and status.hard_exceeded and status.soft_exceeded


def test_would_exceed_hard() -> None:
    b = B(Decimal("100"), Decimal("99"))
    assert would_exceed_hard(b, Decimal("2")) is True
    assert would_exceed_hard(b, Decimal("1")) is False


def test_next_reset_daily() -> None:
    now = datetime(2026, 7, 11, 15, 30, tzinfo=UTC)
    assert next_reset(now, "daily") == datetime(2026, 7, 12, 0, 0, tzinfo=UTC)


def test_next_reset_monthly_and_year_rollover() -> None:
    assert next_reset(datetime(2026, 7, 11, tzinfo=UTC), "monthly") == datetime(
        2026, 8, 1, tzinfo=UTC
    )
    assert next_reset(datetime(2026, 12, 15, tzinfo=UTC), "monthly") == datetime(
        2027, 1, 1, tzinfo=UTC
    )


def test_next_reset_unknown_period() -> None:
    with pytest.raises(ValueError):
        next_reset(datetime(2026, 1, 1, tzinfo=UTC), "weekly")


def test_maybe_reset_initializes_when_unset() -> None:
    b = B(Decimal("100"), Decimal("40"), resets_at=None)
    assert maybe_reset(b, datetime(2026, 7, 11, tzinfo=UTC)) is False
    assert b.resets_at is not None and b.spent == Decimal("40")


def test_maybe_reset_rolls_over_and_zeroes_spent() -> None:
    b = B(Decimal("100"), Decimal("90"), resets_at=datetime(2026, 7, 1, tzinfo=UTC))
    now = datetime(2026, 7, 11, tzinfo=UTC)
    assert maybe_reset(b, now) is True
    assert b.spent == Decimal("0")
    assert b.resets_at == datetime(2026, 8, 1, tzinfo=UTC)


def test_maybe_reset_noop_before_period_end() -> None:
    b = B(Decimal("100"), Decimal("90"), resets_at=datetime(2026, 8, 1, tzinfo=UTC))
    assert maybe_reset(b, datetime(2026, 7, 11, tzinfo=UTC)) is False
    assert b.spent == Decimal("90")
