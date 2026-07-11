"""initial base

Revision ID: 52903a89f6e2
Revises: 
Create Date: 2026-07-11 10:43:38.796989

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '52903a89f6e2'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
