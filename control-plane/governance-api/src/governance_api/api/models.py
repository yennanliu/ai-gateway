"""Model registry: provider credentials and model deployments (org-admin)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from governance_api.api.deps import (
    PrincipalDep,
    SessionDep,
    flush_or_409,
    get_or_404,
)
from governance_api.api.schemas import (
    ModelDeploymentCreate,
    ModelDeploymentOut,
    ModelDeploymentUpdate,
    ProviderCredentialCreate,
    ProviderCredentialOut,
)
from governance_api.auth import authz
from governance_api.auth.principal import ROLE_ORG_ADMIN, Principal
from governance_api.db.models import ModelDeployment, ProviderCredential
from governance_api.services import audit

router = APIRouter(prefix="/api/v1", tags=["registry"])


def _org(principal: Principal) -> str:
    if principal.org_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="no org context")
    authz.require_org_role(principal, principal.org_id, ROLE_ORG_ADMIN)
    return principal.org_id


@router.post(
    "/provider-credentials",
    response_model=ProviderCredentialOut,
    status_code=status.HTTP_201_CREATED,
)
def create_credential(
    body: ProviderCredentialCreate, db: SessionDep, principal: PrincipalDep
) -> ProviderCredential:
    org_id = _org(principal)
    cred = ProviderCredential(org_id=org_id, provider=body.provider, secret_ref=body.secret_ref)
    db.add(cred)
    db.flush()
    audit.record(db, principal, "credential.create", target=cred.id)
    return cred


@router.get("/provider-credentials", response_model=list[ProviderCredentialOut])
def list_credentials(db: SessionDep, principal: PrincipalDep) -> list[ProviderCredential]:
    org_id = _org(principal)
    return list(
        db.execute(select(ProviderCredential).where(ProviderCredential.org_id == org_id)).scalars()
    )


@router.post("/models", response_model=ModelDeploymentOut, status_code=status.HTTP_201_CREATED)
def create_model(
    body: ModelDeploymentCreate, db: SessionDep, principal: PrincipalDep
) -> ModelDeployment:
    org_id = _org(principal)
    dep = ModelDeployment(
        org_id=org_id,
        public_name=body.public_name,
        provider=body.provider,
        model=body.model,
        api_base=body.api_base,
        credential_id=body.credential_id,
        routing_tags=body.routing_tags,
        tpm_limit=body.tpm_limit,
        rpm_limit=body.rpm_limit,
    )
    db.add(dep)
    flush_or_409(db, "a model with this public_name already exists")
    audit.record(
        db, principal, "model.create", target=dep.id, after={"public_name": body.public_name}
    )
    return dep


@router.get("/models", response_model=list[ModelDeploymentOut])
def list_models(db: SessionDep, principal: PrincipalDep) -> list[ModelDeployment]:
    org_id = _org(principal)
    return list(
        db.execute(select(ModelDeployment).where(ModelDeployment.org_id == org_id)).scalars()
    )


@router.patch("/models/{model_id}", response_model=ModelDeploymentOut)
def update_model(
    model_id: str, body: ModelDeploymentUpdate, db: SessionDep, principal: PrincipalDep
) -> ModelDeployment:
    org_id = _org(principal)
    dep = get_or_404(db, ModelDeployment, model_id)
    if dep.org_id != org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="ModelDeployment not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(dep, field, value)
    db.flush()
    audit.record(db, principal, "model.update", target=dep.id)
    return dep


@router.delete("/models/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_model(model_id: str, db: SessionDep, principal: PrincipalDep) -> None:
    org_id = _org(principal)
    dep = get_or_404(db, ModelDeployment, model_id)
    if dep.org_id != org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="ModelDeployment not found")
    db.delete(dep)
    db.flush()
    audit.record(db, principal, "model.delete", target=model_id)
