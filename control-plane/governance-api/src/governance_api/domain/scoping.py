"""Scope resolution: budgets/policies attach at any level and resolve
most-specific-wins (key > app > user > team > org).

Pure logic, no DB — unit-tested to 100%.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

# Most-specific first. This ordering *is* the precedence rule.
SCOPE_PRECEDENCE: tuple[str, ...] = ("key", "app", "user", "team", "org")


class Scoped(Protocol):
    scope_type: str
    scope_id: str


@dataclass(frozen=True)
class ScopeContext:
    """The entities in play for a single request, most-specific first."""

    org_id: str | None = None
    team_id: str | None = None
    user_id: str | None = None
    app_id: str | None = None
    key_id: str | None = None

    def id_for(self, level: str) -> str | None:
        value: str | None = getattr(self, f"{level}_id")
        return value


def resolve_scoped[T: Scoped](items: list[T], ctx: ScopeContext) -> T | None:
    """Return the single most-specific item matching the context, or None.

    Ties within a level are broken by input order (first match wins).
    """
    for level in SCOPE_PRECEDENCE:
        target = ctx.id_for(level)
        if target is None:
            continue
        for item in items:
            if item.scope_type == level and item.scope_id == target:
                return item
    return None
