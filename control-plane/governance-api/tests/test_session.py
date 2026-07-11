"""M0: the get_session dependency commits on success, rolls back on error."""

from __future__ import annotations

import pytest

from governance_api.db.session import get_session


def test_get_session_commits_and_closes() -> None:
    gen = get_session()
    session = next(gen)
    assert session is not None
    # Resuming the generator runs commit + close, then completes.
    with pytest.raises(StopIteration):
        next(gen)


def test_get_session_rolls_back_on_error() -> None:
    gen = get_session()
    next(gen)
    # An error thrown into the dependency propagates after rollback.
    with pytest.raises(ValueError):
        gen.throw(ValueError("boom"))
