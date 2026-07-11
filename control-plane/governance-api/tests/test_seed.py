"""M7: the seed produces a working demo — usable via the API + metering."""

from __future__ import annotations

from collections.abc import Callable

from factories import org_admin
from httpx import AsyncClient
from sqlalchemy.orm import Session

from governance_api.auth.principal import Principal
from governance_api.security.keys import verify_key
from governance_api.services.config_compiler import compile_for_org
from governance_api.services.metering import record_usage
from governance_api.services.seed import seed

Setter = Callable[[Principal], None]


def test_seed_is_idempotent_for_fixed_entities(db: Session) -> None:
    first = seed(db)
    second = seed(db)
    db.commit()
    assert first["org_id"] == second["org_id"]  # same demo org reused
    assert first["key"] != second["key"]  # but a fresh key each time


def test_seed_key_is_hashed_not_stored_plaintext(db: Session) -> None:
    from governance_api.db.models import VirtualKey

    result = seed(db)
    db.commit()
    stored = db.get(VirtualKey, result["key_id"])
    assert stored is not None
    assert stored.hashed_key != result["key"]
    assert verify_key(result["key"], stored.hashed_key)


def test_seed_compiles_a_config_with_the_demo_model(db: Session) -> None:
    result = seed(db)
    db.commit()
    config = compile_for_org(db, result["org_id"])
    names = [m["model_name"] for m in config["model_list"]]
    assert "demo-gpt" in config["model_list"][0]["model_name"] or "demo-gpt" in names


async def test_seed_data_is_usable_via_api(
    client: AsyncClient, as_principal: Setter, db: Session
) -> None:
    result = seed(db)
    # record a call so usage is non-empty
    record_usage(
        db,
        key_id=result["key_id"],
        team_id=result["team_id"],
        org_id=result["org_id"],
        model="gpt-4o-mini",
        prompt_tokens=1000,
        completion_tokens=0,
    )
    db.commit()

    as_principal(org_admin(result["org_id"]))
    models = await client.get("/api/v1/models")
    assert models.status_code == 200
    assert any(m["public_name"] == "demo-gpt" for m in models.json())

    usage = await client.get("/api/v1/usage")
    assert usage.status_code == 200
    assert usage.json()[0]["requests"] == 1
