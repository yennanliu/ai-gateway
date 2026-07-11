"""Shared FastAPI dependency aliases."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from governance_api.auth.dependencies import get_principal
from governance_api.auth.principal import Principal
from governance_api.db.base import Base
from governance_api.db.session import get_session

SessionDep = Annotated[Session, Depends(get_session)]
PrincipalDep = Annotated[Principal, Depends(get_principal)]


def get_or_404[M: Base](db: Session, model: type[M], obj_id: str) -> M:
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"{model.__name__} not found")
    return obj


def flush_or_409(db: Session, detail: str = "resource already exists") -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail=detail) from exc
