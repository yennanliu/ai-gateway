"""Fixed-window rate limiting.

One interface (RateCounter); in-process implementation for local/dev, a Redis
implementation for production (same interface) lands with the deploy work.
``now`` is passed in (epoch seconds) so the window math is deterministic in tests.
"""

from __future__ import annotations

from typing import Protocol

WINDOW_SECONDS = 60  # per-minute windows for RPM/TPM


class RateCounter(Protocol):
    def current(self, subject: str, now: float, window_s: int) -> int: ...
    def hit(self, subject: str, amount: int, now: float, window_s: int) -> int: ...


class InProcessCounter:
    """Non-distributed fixed-window counter. Fine for a single replica / tests."""

    def __init__(self) -> None:
        self._buckets: dict[str, tuple[int, int]] = {}

    @staticmethod
    def _window_start(now: float, window_s: int) -> int:
        return int(now // window_s) * window_s

    def current(self, subject: str, now: float, window_s: int = WINDOW_SECONDS) -> int:
        ws = self._window_start(now, window_s)
        start, count = self._buckets.get(subject, (ws, 0))
        return count if start == ws else 0

    def hit(self, subject: str, amount: int, now: float, window_s: int = WINDOW_SECONDS) -> int:
        ws = self._window_start(now, window_s)
        start, count = self._buckets.get(subject, (ws, 0))
        count = amount if start != ws else count + amount
        self._buckets[subject] = (ws, count)
        return count


def check_rate(
    counter: RateCounter,
    subject: str,
    limit: int | None,
    amount: int,
    now: float,
    window_s: int = WINDOW_SECONDS,
) -> bool:
    """Return True (and record the hit) if within limit; False if it would exceed."""
    if limit is None:
        return True
    if counter.current(subject, now, window_s) + amount > limit:
        return False
    counter.hit(subject, amount, now, window_s)
    return True
