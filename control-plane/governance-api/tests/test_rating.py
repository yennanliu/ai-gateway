"""M4: token->cost rating. Money logic — exact Decimal results."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

import pytest

from governance_api.domain.rating import parse_unit, price_request


@dataclass
class RC:
    unit: str
    price: Decimal
    markup_pct: Decimal = field(default_factory=lambda: Decimal("0"))


def test_parse_unit_variants() -> None:
    assert parse_unit("1k_tokens") == ("total", 1000)
    assert parse_unit("input_1k_tokens") == ("input", 1000)
    assert parse_unit("output_1m_tokens") == ("output", 1_000_000)


@pytest.mark.parametrize("bad", ["", "tokens", "weird_1k_tokens", "1g_tokens", "1k_words"])
def test_parse_unit_rejects_bad(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_unit(bad)


def test_price_total_tokens() -> None:
    cost = price_request(1000, 500, [RC("1k_tokens", Decimal("2"))])
    assert cost == Decimal("3.000000")  # 1500/1000 * 2


def test_price_separate_input_output() -> None:
    cards = [
        RC("input_1k_tokens", Decimal("0.005")),
        RC("output_1k_tokens", Decimal("0.015")),
    ]
    cost = price_request(1000, 500, cards)
    assert cost == Decimal("0.012500")  # 0.005 + 0.0075


def test_markup_applied() -> None:
    cost = price_request(1_000_000, 0, [RC("1m_tokens", Decimal("10"), Decimal("20"))])
    assert cost == Decimal("12.000000")  # 10 * 1.20


def test_no_cards_is_zero() -> None:
    assert price_request(100, 100, []) == Decimal("0")


def test_result_is_exact_not_float() -> None:
    cost = price_request(333, 0, [RC("1k_tokens", Decimal("1"))])
    assert cost == Decimal("0.333000")
