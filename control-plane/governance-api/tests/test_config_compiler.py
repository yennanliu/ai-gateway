"""M3: config compiler — model_list, routing/fallbacks, secret refs, org compile."""

from __future__ import annotations

import yaml
from factories import make_credential, make_deployment, make_org
from sqlalchemy.orm import Session

from governance_api.db.models import Policy
from governance_api.services.config_compiler import (
    CUSTOM_AUTH_PATH,
    compile_config,
    compile_for_org,
    write_config,
)


def test_compile_maps_provider_and_model(db: Session) -> None:
    org = make_org(db)
    cred = make_credential(db, org, secret_ref="OPENAI_API_KEY")
    dep = make_deployment(db, org, public_name="fast", model="gpt-4o-mini", credential=cred)

    config = compile_config([dep], secret_refs={cred.id: cred.secret_ref})
    entry = config["model_list"][0]
    assert entry["model_name"] == "fast"
    assert entry["litellm_params"]["model"] == "openai/gpt-4o-mini"
    # Secret is a reference, never plaintext.
    assert entry["litellm_params"]["api_key"] == "os.environ/OPENAI_API_KEY"
    assert config["general_settings"]["custom_auth"] == CUSTOM_AUTH_PATH


def test_compile_includes_api_base_and_limits(db: Session) -> None:
    org = make_org(db)
    dep = make_deployment(db, org, api_base="http://stub:9000")
    dep.tpm_limit = 1000
    dep.rpm_limit = 60
    config = compile_config([dep])
    params = config["model_list"][0]["litellm_params"]
    assert params["api_base"] == "http://stub:9000"
    assert params["tpm"] == 1000 and params["rpm"] == 60
    assert "api_key" not in params  # no credential


def test_compile_skips_inactive_deployments(db: Session) -> None:
    org = make_org(db)
    active = make_deployment(db, org, public_name="a")
    disabled = make_deployment(db, org, public_name="b")
    disabled.status = "disabled"
    config = compile_config([active, disabled])
    assert [m["model_name"] for m in config["model_list"]] == ["a"]


def test_compile_routing_fallbacks_and_strategy() -> None:
    config = compile_config(
        [],
        routing={"strategy": "latency-based-routing", "fallbacks": {"primary": ["backup"]}},
    )
    rs = config["router_settings"]
    assert rs["routing_strategy"] == "latency-based-routing"
    assert rs["fallbacks"] == [{"primary": ["backup"]}]


def test_compile_defaults_when_no_routing() -> None:
    rs = compile_config([])["router_settings"]
    assert rs["routing_strategy"] == "simple-shuffle"
    assert "fallbacks" not in rs


def test_compile_for_org_reads_deployments_and_policy(db: Session) -> None:
    org = make_org(db)
    cred = make_credential(db, org)
    make_deployment(db, org, public_name="gpt", credential=cred)
    db.add(
        Policy(
            scope_type="org",
            scope_id=org.id,
            routing={"strategy": "least-busy", "fallbacks": {"gpt": ["gpt2"]}},
        )
    )
    db.flush()

    config = compile_for_org(db, org.id)
    assert [m["model_name"] for m in config["model_list"]] == ["gpt"]
    assert config["router_settings"]["routing_strategy"] == "least-busy"
    assert config["router_settings"]["fallbacks"] == [{"gpt": ["gpt2"]}]


def test_write_config_is_valid_yaml(db: Session, tmp_path) -> None:  # type: ignore[no-untyped-def]
    org = make_org(db)
    make_deployment(db, org, public_name="gpt")
    config = compile_for_org(db, org.id)
    path = tmp_path / "litellm.config.yaml"
    write_config(config, str(path))
    loaded = yaml.safe_load(path.read_text())
    assert loaded["model_list"][0]["model_name"] == "gpt"
