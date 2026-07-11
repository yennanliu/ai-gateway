"""M3: config compile/reload endpoints — RBAC, file write, audit."""

from __future__ import annotations

from collections.abc import Callable

import yaml
from factories import (
    bare,
    make_credential,
    make_deployment,
    make_org,
    org_admin,
    platform_admin,
)
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from governance_api.auth.principal import Principal
from governance_api.config import settings
from governance_api.db.models import AuditEvent

Setter = Callable[[Principal], None]


async def test_compile_requires_org_admin(
    client: AsyncClient, as_principal: Setter, db: Session
) -> None:
    org = make_org(db)
    db.commit()
    as_principal(bare(org_id=org.id))
    assert (await client.post("/api/v1/config/compile")).status_code == 403


async def test_compile_writes_file_and_audits(
    client: AsyncClient, as_principal: Setter, db: Session, tmp_path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    org = make_org(db)
    cred = make_credential(db, org)
    make_deployment(db, org, public_name="gpt", credential=cred)
    db.commit()

    path = tmp_path / "litellm.config.yaml"
    monkeypatch.setattr(settings, "litellm_config_path", str(path))

    as_principal(org_admin(org.id))
    resp = await client.post("/api/v1/config/compile")
    assert resp.status_code == 200
    assert resp.json()["model_list"][0]["model_name"] == "gpt"

    written = yaml.safe_load(path.read_text())
    assert written["general_settings"]["custom_auth"]

    events = (
        db.execute(select(AuditEvent).where(AuditEvent.action == "config.compile")).scalars().all()
    )
    assert len(events) == 1


async def test_compile_without_org_context_400(client: AsyncClient, as_principal: Setter) -> None:
    as_principal(platform_admin())  # org-admin role but no bound org
    assert (await client.post("/api/v1/config/compile")).status_code == 400


async def test_reload_requested(client: AsyncClient, as_principal: Setter, db: Session) -> None:
    org = make_org(db)
    db.commit()
    as_principal(org_admin(org.id))
    resp = await client.post("/api/v1/config/reload")
    assert resp.status_code == 202
    assert resp.json()["status"] == "reload requested"


async def test_version_reports_compatible_litellm(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/version")
    assert resp.status_code == 200
    assert resp.json()["litellm"]  # tested-against version string
