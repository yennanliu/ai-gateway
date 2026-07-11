"""M4: fixed-window rate limiting — 429 semantics and window rollover."""

from __future__ import annotations

from hooks.ratelimit import InProcessCounter, check_rate


def test_allows_up_to_limit_then_blocks() -> None:
    counter = InProcessCounter()
    now = 1000.0
    assert check_rate(counter, "rpm:k", 2, 1, now) is True
    assert check_rate(counter, "rpm:k", 2, 1, now) is True
    assert check_rate(counter, "rpm:k", 2, 1, now) is False  # 3rd exceeds


def test_none_limit_always_allows() -> None:
    counter = InProcessCounter()
    assert check_rate(counter, "rpm:k", None, 100, 0.0) is True


def test_window_rollover_resets_count() -> None:
    counter = InProcessCounter()
    assert check_rate(counter, "rpm:k", 1, 1, 0.0) is True
    assert check_rate(counter, "rpm:k", 1, 1, 30.0) is False  # same 60s window
    assert check_rate(counter, "rpm:k", 1, 1, 60.0) is True  # next window


def test_amount_greater_than_one() -> None:
    counter = InProcessCounter()
    now = 0.0
    assert check_rate(counter, "tpm:k", 1000, 800, now) is True
    assert check_rate(counter, "tpm:k", 1000, 300, now) is False  # 800+300 > 1000
    assert counter.current("tpm:k", now) == 800  # rejected hit not recorded


def test_separate_subjects_independent() -> None:
    counter = InProcessCounter()
    assert check_rate(counter, "rpm:a", 1, 1, 0.0) is True
    assert check_rate(counter, "rpm:b", 1, 1, 0.0) is True
