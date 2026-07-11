"""Token → cost rating. Money logic: Decimal throughout, exact to the cent.

A model's price comes from RateCard rows. ``unit`` encodes both which tokens it
prices and the per-unit size:
  "1k_tokens"        -> total tokens, per 1,000
  "input_1k_tokens"  -> prompt tokens, per 1,000
  "output_1m_tokens" -> completion tokens, per 1,000,000
markup_pct is applied on top of each line.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

_UNIT_SIZES = {"1k": 1000, "1m": 1_000_000}
_KINDS = ("input", "output", "total")
_QUANTUM = Decimal("0.000001")


class RateLike(Protocol):
    unit: str
    price: Decimal
    markup_pct: Decimal


def parse_unit(unit: str) -> tuple[str, int]:
    """Return (kind, per_unit_size) for a rate-card unit string."""
    parts = unit.split("_")
    if len(parts) < 2 or parts[-1] != "tokens":
        raise ValueError(f"invalid rate-card unit: {unit!r}")
    if len(parts) == 2:
        kind, size_token = "total", parts[0]
    elif len(parts) == 3:
        kind, size_token = parts[0], parts[1]
    else:
        raise ValueError(f"invalid rate-card unit: {unit!r}")
    if kind not in _KINDS or size_token not in _UNIT_SIZES:
        raise ValueError(f"invalid rate-card unit: {unit!r}")
    return kind, _UNIT_SIZES[size_token]


def price_request(
    prompt_tokens: int, completion_tokens: int, rate_cards: Sequence[RateLike]
) -> Decimal:
    """Cost for one request given the rate cards for its model."""
    total = Decimal("0")
    for card in rate_cards:
        kind, size = parse_unit(card.unit)
        qty = {
            "input": prompt_tokens,
            "output": completion_tokens,
            "total": prompt_tokens + completion_tokens,
        }[kind]
        line = (Decimal(qty) / Decimal(size)) * Decimal(card.price)
        line *= Decimal(1) + Decimal(card.markup_pct) / Decimal(100)
        total += line
    return total.quantize(_QUANTUM, rounding=ROUND_HALF_UP)
