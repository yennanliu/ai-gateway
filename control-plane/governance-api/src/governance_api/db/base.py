"""Declarative base for all ORM models.

`jsonb` and array columns are expressed via portable SQLAlchemy types so the
same models run unchanged on SQLite (default) and Postgres (scale).
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
