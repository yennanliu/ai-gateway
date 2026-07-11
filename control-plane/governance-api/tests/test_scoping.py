"""M1: most-specific-wins scope resolution — exhaustive, 100% coverage target."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from governance_api.domain.scoping import (
    SCOPE_PRECEDENCE,
    ScopeContext,
    resolve_scoped,
)


@dataclass
class Item:
    scope_type: str
    scope_id: str
    tag: str = ""


FULL_CTX = ScopeContext(org_id="o1", team_id="t1", user_id="u1", app_id="a1", key_id="k1")


def test_precedence_order_is_most_specific_first() -> None:
    assert SCOPE_PRECEDENCE == ("key", "app", "user", "team", "org")


@pytest.mark.parametrize(
    ("scope_type", "scope_id"),
    [("key", "k1"), ("app", "a1"), ("user", "u1"), ("team", "t1"), ("org", "o1")],
)
def test_single_item_at_each_level_matches(scope_type: str, scope_id: str) -> None:
    item = Item(scope_type, scope_id)
    assert resolve_scoped([item], FULL_CTX) is item


def test_most_specific_wins_when_multiple_present() -> None:
    items = [
        Item("org", "o1", "org"),
        Item("team", "t1", "team"),
        Item("key", "k1", "key"),
        Item("user", "u1", "user"),
    ]
    winner = resolve_scoped(items, FULL_CTX)
    assert winner is not None and winner.tag == "key"


def test_falls_through_to_next_level_when_specific_absent() -> None:
    # No key/app/user-scoped item -> team wins over org.
    items = [Item("org", "o1", "org"), Item("team", "t1", "team")]
    winner = resolve_scoped(items, FULL_CTX)
    assert winner is not None and winner.tag == "team"


def test_no_match_returns_none() -> None:
    items = [Item("team", "other-team"), Item("org", "other-org")]
    assert resolve_scoped(items, FULL_CTX) is None


def test_empty_items_returns_none() -> None:
    assert resolve_scoped([], FULL_CTX) is None


def test_missing_context_levels_are_skipped() -> None:
    # Only org known in context; a team-scoped item cannot match.
    ctx = ScopeContext(org_id="o1")
    items = [Item("team", "t1", "team"), Item("org", "o1", "org")]
    winner = resolve_scoped(items, ctx)
    assert winner is not None and winner.tag == "org"


def test_id_mismatch_at_specific_level_falls_through() -> None:
    # A key-scoped item for a *different* key must not match; team wins.
    items = [Item("key", "other-key"), Item("team", "t1", "team")]
    winner = resolve_scoped(items, FULL_CTX)
    assert winner is not None and winner.tag == "team"


def test_first_match_wins_within_a_level() -> None:
    items = [Item("team", "t1", "first"), Item("team", "t1", "second")]
    winner = resolve_scoped(items, FULL_CTX)
    assert winner is not None and winner.tag == "first"


def test_id_for_helper() -> None:
    assert FULL_CTX.id_for("key") == "k1"
    assert FULL_CTX.id_for("org") == "o1"
    assert ScopeContext().id_for("team") is None
