# ai-gateway-stack — AWS CDK

Deploys the **AI Gateway** (control plane + data plane + admin UI) to AWS with
the AWS CDK (TypeScript). Full architecture, rationale, and the phased roadmap
live in [`doc/aws-cdk-deployment.md`](../doc/aws-cdk-deployment.md).

## What Phase 1 deploys

One stack, everything it needs to serve a governed request end to end:

| Layer | AWS service | Notes |
|---|---|---|
| Ingress | Application Load Balancer (HTTP :80) | Path-routed to the three services |
| Admin UI | ECS Fargate (Vue + nginx) | Default `/` route |
| Control plane | ECS Fargate (`governance-api`, :8080) | `/api/*`, `/docs`, `/healthz` |
| Data plane | ECS Fargate (LiteLLM + hooks, :4000) | `/v1/*`, `/health/*`; self-compiles its config from the DB at boot |
| Source of truth | RDS PostgreSQL (`t4g.micro`) | Keys + spend; shared by both planes |
| Secrets | Secrets Manager | DB credentials (auto-generated) |
| Providers | Amazon Bedrock via IAM | Zero-key default; the data-plane task role can invoke Bedrock |

No shared filesystem: the data plane runs `scripts/compile_config.py` at startup
to generate its LiteLLM config from the DB into container-local `/tmp` (see
`doc/aws-cdk-deployment.md` §7).

```
Internet ─▶ ALB :80
              ├── /            ─▶ Admin UI      (Fargate)
              ├── /api/* /docs ─▶ Control plane (Fargate) ─┐
              └── /v1/*        ─▶ Data plane    (Fargate) ─┤ self-compiles config
                                                           │
                              RDS PostgreSQL ◀──both planes, source of truth
```

## Prerequisites

- Node 20+, Docker running (images are built locally as CDK assets), AWS creds.
- Bootstrap once per account/region: `npx cdk bootstrap`.

## Deploy

```bash
npm install
npm run build            # tsc
npx cdk synth            # render CloudFormation (no AWS calls)
npx cdk deploy           # build images, push to ECR, create the stack
```

Name the deploy with context (a version suffix gives clean re-deploys/teardown):

```bash
npx cdk deploy -c appName=ai-gateway -c version=v1
```

Outputs include `AdminUiUrl`, `ControlPlaneUrl`, `GatewayUrl`, and the seed
task's `run-task` network config.

## Make it serve a real request (Bedrock, no API keys)

1. Enable model access for the model you want in the **Amazon Bedrock** console.
2. Open `AdminUiUrl` (or call the API) and **register a model**: provider
   `bedrock`, e.g. model `anthropic.claude-3-5-sonnet-20240620-v1:0`.
3. Roll the data plane — it recompiles its config from the DB at boot:
   `aws ecs update-service --cluster <ClusterName> --service ai-gateway-v1-data-plane --force-new-deployment`.
4. Call it: `POST {GatewayUrl}/chat/completions` with a virtual key.

> Phase 1 has **no live config reload** and no shared filesystem — the data plane
> self-compiles its config from the DB at startup, so the roll in step 3 *is* the
> reload. Phase 2 wires an automatic (no-roll) reload (see the doc).

## Optional: seed demo data

Seeds a demo org/team/models/key and compiles a config (demo models point at a
stub that isn't deployed on AWS, so this is for exercising the control plane +
UI, not `/v1`):

```bash
aws ecs run-task --cluster <ClusterName> \
  --task-definition <SeedTaskFamily> --launch-type FARGATE \
  --network-configuration '<SeedRunTaskNetwork output>'
```

## Teardown

```bash
npx cdk destroy -c version=v1
```

Aurora and EFS use `DESTROY` removal in Phase 1 (dev). Switch to
`SNAPSHOT`/`RETAIN` before using this for anything real.

## Commands

- `npm run build` — compile TypeScript
- `npm test` — Jest structural assertions on the synthesized stack
- `npx cdk diff` / `synth` / `deploy` / `destroy`
