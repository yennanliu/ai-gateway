"""A thin generic repository over a SQLAlchemy session.

Deliberately minimal for M1; the service layer (M2) builds domain operations
on top of this.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from governance_api.db.base import Base


class Repository[M: Base]:
    def __init__(self, session: Session, model: type[M]) -> None:
        self.session = session
        self.model = model

    def add(self, obj: M) -> M:
        self.session.add(obj)
        self.session.flush()
        return obj

    def get(self, obj_id: str) -> M | None:
        return self.session.get(self.model, obj_id)

    def list(self) -> Sequence[M]:
        return self.session.execute(select(self.model)).scalars().all()

    def delete(self, obj: M) -> None:
        self.session.delete(obj)
        self.session.flush()
