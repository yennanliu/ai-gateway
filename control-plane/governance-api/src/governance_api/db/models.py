"""Aggregates all ORM models so Alembic autogenerate sees the full metadata.

Import new model modules here as they are added (M1+).
"""

from __future__ import annotations

from governance_api.db.base import Base

__all__ = ["Base"]
