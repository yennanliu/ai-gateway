"""M1: generic repository CRUD."""

from __future__ import annotations

from sqlalchemy.orm import Session

from governance_api.db.models import Org
from governance_api.db.repository import Repository


def test_repository_crud(db: Session) -> None:
    repo: Repository[Org] = Repository(db, Org)

    org = repo.add(Org(name="Repo Co"))
    assert repo.get(org.id) is org
    assert list(repo.list()) == [org]

    repo.delete(org)
    assert repo.get(org.id) is None
    assert list(repo.list()) == []
