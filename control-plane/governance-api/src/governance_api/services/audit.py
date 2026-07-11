"""Append-only audit trail. Every mutating governance action calls record()."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from governance_api.auth.principal import Principal
from governance_api.db.models import AuditEvent


def record(
    db: Session,
    principal: Principal,
    action: str,
    target: str | None = None,
    *,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    ip: str | None = None,
) -> AuditEvent:
    event = AuditEvent(
        actor=principal.user_id,
        action=action,
        target=target,
        before=before,
        after=after,
        ip=ip,
    )
    db.add(event)
    db.flush()
    return event
