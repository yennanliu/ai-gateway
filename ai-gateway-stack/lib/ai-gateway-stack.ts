import { CfnOutput, Duration, RemovalPolicy, Stack, StackProps } from 'aws-cdk-lib/core';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecr_assets from 'aws-cdk-lib/aws-ecr-assets';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as efs from 'aws-cdk-lib/aws-efs';
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as path from 'path';
import { Construct } from 'constructs';
import { FargateAppService } from './constructs/fargate-app-service';

/**
 * AI Gateway on AWS — Phase 1 (single-stack, working end-to-end).
 *
 * Deploys BOTH planes of the gateway and everything they need:
 *
 *   Internet ─▶ ALB (HTTP :80, path-routed)
 *                 ├── /            ─▶ Admin UI  (Vue + nginx, :80)
 *                 ├── /api/* /docs ─▶ Control plane (governance-api, :8080)
 *                 └── /v1/*        ─▶ Data plane (LiteLLM proxy + hooks, :4000)
 *                          │
 *              private ────┼──────────────┐
 *                          ▼              ▼
 *                   Aurora PG v2      EFS (shared compiled LiteLLM config)
 *
 * The invariant from `doc/system-design.md` holds on AWS: our Postgres is the
 * source of truth for keys + spend. SQLite cannot be shared across Fargate
 * tasks, so Phase 1 uses Aurora Postgres Serverless v2 from the start. The
 * control plane compiles the LiteLLM config onto a shared EFS volume; the data
 * plane reads it — the AWS analogue of the docker-compose `/data` volume.
 *
 * Provider access defaults to **Amazon Bedrock via IAM** (no API keys): the
 * data-plane task role can invoke Bedrock models directly. Register a Bedrock
 * model in the console/API, POST /api/v1/config/compile, then roll the data
 * plane to pick up the new config.
 *
 * TLS/HTTPS, Redis, autoscaling, WAF and a CI image pipeline are Phase 2 — see
 * `doc/aws-cdk-deployment.md`.
 */
export interface AiGatewayStackProps extends StackProps {
  /** Base name for trackable resources (cluster, ALB, DB, log group). */
  readonly resourceName?: string;
}

export class AiGatewayStack extends Stack {
  constructor(scope: Construct, id: string, props?: AiGatewayStackProps) {
    super(scope, id, props);

    const resourceName = props?.resourceName ?? id;
    const dbName = 'aigw';
    const repoRoot = path.join(__dirname, '..', '..');
    const configPath = '/data/litellm.config.yaml';

    // Ports each plane listens on (mirrors docker-compose).
    const CONTROL_PORT = 8080;
    const DATA_PORT = 4000;
    const UI_PORT = 80;

    // =====================================================================
    // Phase 1 · Network
    // =====================================================================
    const vpc = new ec2.Vpc(this, 'Vpc', {
      maxAzs: 2,
      natGateways: 1, // single NAT keeps Phase 1 cheap; use one-per-AZ in prod
      subnetConfiguration: [
        { name: 'public', subnetType: ec2.SubnetType.PUBLIC, cidrMask: 24 },
        { name: 'private', subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS, cidrMask: 24 },
      ],
    });

    // =====================================================================
    // Phase 1 · Data — Aurora PostgreSQL Serverless v2 (source of truth)
    // =====================================================================
    const dbSecurityGroup = new ec2.SecurityGroup(this, 'DbSg', {
      vpc,
      description: 'AI Gateway Aurora — ingress from the gateway services only',
      allowAllOutbound: false,
    });

    // Password restricted to URL- and shell-safe characters: the services build
    // AIGW_DATABASE_URL by string interpolation inside a double-quoted shell
    // string, so no character may break URL parsing or the shell.
    const dbCredentials = rds.Credentials.fromGeneratedSecret(dbName, {
      excludeCharacters: "!\"#$%&'()*+,/:;<=>?@[\\]^`{|}~ ",
    });

    const db = new rds.DatabaseCluster(this, 'Database', {
      clusterIdentifier: `${resourceName}-db`,
      engine: rds.DatabaseClusterEngine.auroraPostgres({
        version: rds.AuroraPostgresEngineVersion.VER_16_9,
      }),
      credentials: dbCredentials,
      defaultDatabaseName: dbName,
      writer: rds.ClusterInstance.serverlessV2('writer'),
      serverlessV2MinCapacity: 0.5,
      serverlessV2MaxCapacity: 2,
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      securityGroups: [dbSecurityGroup],
      storageEncrypted: true,
      removalPolicy: RemovalPolicy.DESTROY, // dev; SNAPSHOT/RETAIN in prod
    });
    const dbSecret = db.secret!;

    // Both planes read the same connection parts; only the credentials are
    // secret. The password/username arrive via Secrets Manager; host/port/name
    // are non-sensitive plain env. A shell wrapper assembles AIGW_DATABASE_URL
    // so no secret is ever baked into the task definition or image.
    const dbEnvironment: Record<string, string> = {
      DB_HOST: db.clusterEndpoint.hostname,
      DB_PORT: db.clusterEndpoint.port.toString(),
      DB_NAME: dbName,
    };
    const dbSecrets: Record<string, ecs.Secret> = {
      DB_USER: ecs.Secret.fromSecretsManager(dbSecret, 'username'),
      DB_PASS: ecs.Secret.fromSecretsManager(dbSecret, 'password'),
    };
    const exportDbUrl =
      'export AIGW_DATABASE_URL="postgresql+psycopg://${DB_USER}:${DB_PASS}@${DB_HOST}:${DB_PORT}/${DB_NAME}"';

    // =====================================================================
    // Phase 1 · Shared config volume (EFS) — compiled LiteLLM config
    // =====================================================================
    const fileSystem = new efs.FileSystem(this, 'SharedConfig', {
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      encrypted: true,
      lifecyclePolicy: efs.LifecyclePolicy.AFTER_30_DAYS,
      removalPolicy: RemovalPolicy.DESTROY, // dev; RETAIN in prod
    });
    // Root-owned access point: both containers run as root and share `/data`.
    const accessPoint = fileSystem.addAccessPoint('DataAp', {
      path: '/data',
      createAcl: { ownerUid: '0', ownerGid: '0', permissions: '0755' },
      posixUser: { uid: '0', gid: '0' },
    });
    const efsMount = { fileSystem, accessPoint, containerPath: '/data' };

    // =====================================================================
    // Phase 1 · Compute — ECS Fargate cluster + container images
    // =====================================================================
    const cluster = new ecs.Cluster(this, 'Cluster', {
      clusterName: `${resourceName}-cluster`,
      vpc,
      containerInsightsV2: ecs.ContainerInsights.ENABLED,
    });

    const logGroup = new logs.LogGroup(this, 'Logs', {
      logGroupName: `/ecs/${resourceName}`,
      retention: logs.RetentionDays.ONE_MONTH,
      removalPolicy: RemovalPolicy.DESTROY,
    });

    // Images are built from the repo Dockerfiles as CDK assets (built + pushed
    // to ECR on deploy). Fargate runs linux/amd64, so pin the platform for
    // arm64 dev machines. Phase 2 swaps these for CI-built, tagged ECR images.
    const platform = ecr_assets.Platform.LINUX_AMD64;
    const controlImage = ecs.ContainerImage.fromAsset(repoRoot, {
      file: 'deploy/docker/control-plane.Dockerfile',
      platform,
    });
    const dataImage = ecs.ContainerImage.fromAsset(repoRoot, {
      file: 'deploy/docker/data-plane.Dockerfile',
      platform,
    });
    const uiImage = ecs.ContainerImage.fromAsset(repoRoot, {
      file: 'deploy/docker/admin-ui.Dockerfile',
      platform,
    });

    // Inner commands come straight from each Dockerfile's CMD; we only prepend
    // the DATABASE_URL assembly (see above).
    const controlCmd =
      'uv run --package governance-api alembic -c control-plane/governance-api/alembic.ini upgrade head && ' +
      'uv run --package governance-api uvicorn governance_api.main:app --host 0.0.0.0 --port ' + CONTROL_PORT;
    const dataCmd = 'uv run --package aigw-hooks bash data-plane/litellm/entrypoint.sh';

    // ---- Control plane (governance-api) --------------------------------
    const control = new FargateAppService(this, 'ControlPlane', {
      cluster,
      serviceName: `${resourceName}-control-plane`,
      image: controlImage,
      containerPort: CONTROL_PORT,
      logGroup,
      cpu: 512,
      memoryLimitMiB: 1024,
      environment: {
        ...dbEnvironment,
        AIGW_LITELLM_CONFIG_PATH: configPath,
        AIGW_ENVIRONMENT: 'aws',
      },
      secrets: dbSecrets,
      entryPoint: ['/bin/sh', '-c'],
      command: [`${exportDbUrl} && exec sh -c '${controlCmd}'`],
      efsMount, // writes the compiled LiteLLM config here
      healthCheckGracePeriod: Duration.seconds(120),
    });

    // ---- Data plane (LiteLLM proxy + our hooks) ------------------------
    const data = new FargateAppService(this, 'DataPlane', {
      cluster,
      serviceName: `${resourceName}-data-plane`,
      image: dataImage,
      containerPort: DATA_PORT,
      logGroup,
      cpu: 1024,
      memoryLimitMiB: 2048,
      environment: {
        ...dbEnvironment,
        AIGW_LITELLM_CONFIG: configPath,
        AIGW_PROXY_PORT: DATA_PORT.toString(),
      },
      secrets: dbSecrets,
      entryPoint: ['/bin/sh', '-c'],
      command: [`${exportDbUrl} && exec ${dataCmd}`],
      efsMount, // reads the compiled config + writes hook shims
      healthCheckGracePeriod: Duration.seconds(120),
    });

    // Zero-key provider path: let the data plane invoke Bedrock models via IAM.
    data.taskDefinition.taskRole.addToPrincipalPolicy(
      new iam.PolicyStatement({
        actions: ['bedrock:InvokeModel', 'bedrock:InvokeModelWithResponseStream'],
        resources: ['*'],
      }),
    );

    // ---- Admin UI (Vue built to static assets, served by nginx) --------
    const ui = new FargateAppService(this, 'AdminUi', {
      cluster,
      serviceName: `${resourceName}-admin-ui`,
      image: uiImage,
      containerPort: UI_PORT,
      logGroup,
      cpu: 256,
      memoryLimitMiB: 512,
    });

    // ---- Connectivity: services -> Aurora (5432) and -> EFS (2049) -----
    for (const svc of [control.service, data.service]) {
      db.connections.allowDefaultPortFrom(svc, 'gateway service to Aurora');
      fileSystem.connections.allowDefaultPortFrom(svc, 'gateway service to EFS');
    }

    // =====================================================================
    // Phase 1 · Edge — one public ALB, path-routed to the three services
    // =====================================================================
    const alb = new elbv2.ApplicationLoadBalancer(this, 'Alb', {
      loadBalancerName: `${resourceName}-alb`,
      vpc,
      internetFacing: true,
    });
    const listener = alb.addListener('Http', { port: 80, open: true });

    const makeTargetGroup = (
      tgId: string,
      port: number,
      service: ecs.FargateService,
      healthPath: string,
    ): elbv2.ApplicationTargetGroup => {
      const tg = new elbv2.ApplicationTargetGroup(this, tgId, {
        vpc,
        port,
        protocol: elbv2.ApplicationProtocol.HTTP,
        targetType: elbv2.TargetType.IP,
        targets: [service],
        deregistrationDelay: Duration.seconds(30),
        healthCheck: {
          path: healthPath,
          healthyHttpCodes: '200-399',
          interval: Duration.seconds(30),
          timeout: Duration.seconds(10),
        },
      });
      service.connections.allowFrom(alb, ec2.Port.tcp(port), `ALB to ${tgId}`);
      return tg;
    };

    const uiTg = makeTargetGroup('UiTg', UI_PORT, ui.service, '/');
    const controlTg = makeTargetGroup('ControlTg', CONTROL_PORT, control.service, '/healthz');
    const dataTg = makeTargetGroup('DataTg', DATA_PORT, data.service, '/health/liveliness');

    // Default: the SPA. Specific prefixes: control plane and data plane. The
    // control plane owns `/api/*` and `/healthz`; the data plane owns `/v1/*`
    // and `/health/*` — disjoint, so no rule collides.
    listener.addTargetGroups('Default', { targetGroups: [uiTg] });
    // ALB allows at most 5 path values per condition, so each rule stays <= 5.
    // `/api/*` covers every control-plane route (all under /api/v1); `/v1/*`
    // covers the OpenAI surface (chat/completions, embeddings, models, ...).
    listener.addTargetGroups('ControlPlane', {
      priority: 10,
      conditions: [
        elbv2.ListenerCondition.pathPatterns([
          '/api/*', '/healthz', '/readyz', '/docs', '/openapi.json',
        ]),
      ],
      targetGroups: [controlTg],
    });
    listener.addTargetGroups('DataPlane', {
      priority: 20,
      conditions: [
        elbv2.ListenerCondition.pathPatterns([
          '/v1/*', '/health/*', '/models', '/chat/*', '/embeddings',
        ]),
      ],
      targetGroups: [dataTg],
    });

    // =====================================================================
    // Phase 1 · Seed task (optional) — demo data + compiled config
    // =====================================================================
    // Not run automatically. After deploy, `aws ecs run-task` this once to seed
    // a demo org/team/models/key and compile a config. Note: seeded demo models
    // point at a stub that is NOT deployed on AWS, so it exercises the control
    // plane + UI; for a real /v1 call, register a Bedrock model instead.
    const seedSg = new ec2.SecurityGroup(this, 'SeedSg', {
      vpc,
      description: 'AI Gateway one-shot seed task',
    });
    db.connections.allowDefaultPortFrom(seedSg, 'seed task to Aurora');
    fileSystem.connections.allowDefaultPortFrom(seedSg, 'seed task to EFS');

    const seedTask = new ecs.FargateTaskDefinition(this, 'SeedTask', {
      cpu: 512,
      memoryLimitMiB: 1024,
    });
    seedTask.addVolume({
      name: 'shared-config',
      efsVolumeConfiguration: {
        fileSystemId: fileSystem.fileSystemId,
        transitEncryption: 'ENABLED',
        authorizationConfig: { accessPointId: accessPoint.accessPointId, iam: 'DISABLED' },
      },
    });
    const seedContainer = seedTask.addContainer('seed', {
      image: controlImage,
      logging: ecs.LogDrivers.awsLogs({ streamPrefix: 'seed', logGroup }),
      environment: {
        ...dbEnvironment,
        AIGW_LITELLM_CONFIG_PATH: configPath,
        AIGW_STUB_URL: 'http://stub-provider:9099', // not deployed; demo only
      },
      secrets: dbSecrets,
      entryPoint: ['/bin/sh', '-c'],
      command: [`${exportDbUrl} && exec uv run --package governance-api python scripts/seed.py`],
    });
    seedContainer.addMountPoints({
      sourceVolume: 'shared-config',
      containerPath: '/data',
      readOnly: false,
    });
    // =====================================================================
    // Outputs
    // =====================================================================
    const base = `http://${alb.loadBalancerDnsName}`;
    new CfnOutput(this, 'AdminUiUrl', { value: base, description: 'Admin console (Vue UI)' });
    new CfnOutput(this, 'ControlPlaneUrl', {
      value: `${base}/api/v1/version`,
      description: 'Control-plane API (governance-api) — version probe; Swagger at /docs',
    });
    new CfnOutput(this, 'GatewayUrl', {
      value: `${base}/v1`,
      description: 'OpenAI-compatible endpoint (LiteLLM data plane)',
    });
    new CfnOutput(this, 'DbSecretArn', {
      value: dbSecret.secretArn,
      description: 'Aurora credentials secret (username/password/host/port)',
    });
    new CfnOutput(this, 'ClusterName', { value: cluster.clusterName });
    new CfnOutput(this, 'SeedTaskFamily', {
      value: seedTask.family,
      description: 'Run once to seed demo data (see SeedRunTaskNetwork for --network-configuration)',
    });
    new CfnOutput(this, 'SeedRunTaskNetwork', {
      value: `awsvpcConfiguration={subnets=[${vpc.privateSubnets
        .map((s) => s.subnetId)
        .join(',')}],securityGroups=[${seedSg.securityGroupId}]}`,
      description: 'Pass to `aws ecs run-task --network-configuration` for the seed task',
    });
  }
}
