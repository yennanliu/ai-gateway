import { CfnOutput, Duration, RemovalPolicy, Stack, StackProps } from 'aws-cdk-lib/core';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecr_assets from 'aws-cdk-lib/aws-ecr-assets';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as path from 'path';
import { Construct } from 'constructs';
import { FargateAppService } from './constructs/fargate-app-service';

/**
 * AI Gateway on AWS — Phase 1 (single-stack, deliberately simple, works E2E).
 *
 *   Internet ─▶ ALB (HTTP :80, path-routed)
 *                 ├── /            ─▶ Admin UI  (Vue + nginx, :80)
 *                 ├── /api/* /docs ─▶ Control plane (governance-api, :8080)
 *                 └── /v1/*        ─▶ Data plane (LiteLLM proxy + hooks, :4000)
 *                          │
 *                          ▼
 *                   RDS PostgreSQL (t4g) — source of truth for keys + spend
 *
 * The invariant from `doc/system-design.md` holds on AWS: our Postgres is the
 * source of truth. SQLite can't be shared across Fargate tasks, so Phase 1 uses
 * a small managed Postgres (single RDS t4g instance — the cheapest simple
 * option) from the start.
 *
 * No shared filesystem. The data plane **self-compiles** its LiteLLM config from
 * the DB into container-local storage at boot (`scripts/compile_config.py`), so
 * there is no EFS/S3 to coordinate — rolling the data plane picks up any
 * registry change. Provider access defaults to **Amazon Bedrock via IAM** (no
 * keys). TLS, Redis, autoscaling, WAF and a CI image pipeline are later phases —
 * see `doc/aws-cdk-deployment.md`.
 */
export interface AiGatewayStackProps extends StackProps {
  /** Base name for trackable resources (DB, cluster, ALB, log group). */
  readonly resourceName?: string;
}

export class AiGatewayStack extends Stack {
  constructor(scope: Construct, id: string, props?: AiGatewayStackProps) {
    super(scope, id, props);

    const resourceName = props?.resourceName ?? id;
    const dbName = 'aigw';
    const repoRoot = path.join(__dirname, '..', '..');
    // Container-local config path ("instance memory") — /tmp is always writable.
    const configPath = '/tmp/litellm.config.yaml';

    // Data safety: Phase 1 defaults to a disposable stack (DESTROY) so
    // `cdk destroy -c version=vN` cleans up fully. Pass `-c retainData=true`
    // for anything real — the DB is then kept on delete (SNAPSHOT) with
    // deletion protection on.
    const retainData = Boolean(this.node.tryGetContext('retainData'));

    // Ports each plane listens on (mirrors docker-compose).
    const CONTROL_PORT = 8080;
    const DATA_PORT = 4000;
    const UI_PORT = 80;

    // =====================================================================
    // Phase 1 · Network
    // =====================================================================
    const vpc = new ec2.Vpc(this, 'Vpc', {
      maxAzs: 2,
      natGateways: 1, // single NAT keeps Phase 1 cheap; one-per-AZ in prod
      subnetConfiguration: [
        { name: 'public', subnetType: ec2.SubnetType.PUBLIC, cidrMask: 24 },
        { name: 'private', subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS, cidrMask: 24 },
      ],
    });

    // =====================================================================
    // Phase 1 · Data — a single small RDS PostgreSQL instance (t4g)
    // =====================================================================
    const dbSecurityGroup = new ec2.SecurityGroup(this, 'DbSg', {
      vpc,
      description: 'AI Gateway RDS — ingress from the gateway services only',
      allowAllOutbound: false,
    });

    // Password restricted to URL- and shell-safe characters: the services build
    // AIGW_DATABASE_URL by string interpolation inside a double-quoted shell
    // string, so no character may break URL parsing or the shell.
    const dbCredentials = rds.Credentials.fromGeneratedSecret(dbName, {
      excludeCharacters: "!\"#$%&'()*+,/:;<=>?@[\\]^`{|}~ ",
    });

    const db = new rds.DatabaseInstance(this, 'Database', {
      instanceIdentifier: `${resourceName}-db`,
      engine: rds.DatabaseInstanceEngine.postgres({
        version: rds.PostgresEngineVersion.VER_16_9,
      }),
      // Smallest Graviton burstable — cheap and enough for the control plane,
      // which is not the hot path (system-design). Bump the size in prod.
      instanceType: ec2.InstanceType.of(ec2.InstanceClass.BURSTABLE4_GRAVITON, ec2.InstanceSize.MICRO),
      credentials: dbCredentials,
      databaseName: dbName,
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      securityGroups: [dbSecurityGroup],
      allocatedStorage: 20,
      storageType: rds.StorageType.GP3,
      multiAz: false, // single-AZ in Phase 1; Multi-AZ in prod
      storageEncrypted: true,
      backupRetention: Duration.days(1),
      deleteAutomatedBackups: !retainData,
      deletionProtection: retainData,
      removalPolicy: retainData ? RemovalPolicy.SNAPSHOT : RemovalPolicy.DESTROY,
    });
    const dbSecret = db.secret!;

    // Both planes read the same connection parts; only the credentials are
    // secret. Username/password arrive via Secrets Manager; host/port/name are
    // non-sensitive plain env. A shell wrapper assembles AIGW_DATABASE_URL at
    // startup so no secret is baked into the task definition or image.
    const dbEnvironment: Record<string, string> = {
      DB_HOST: db.dbInstanceEndpointAddress,
      DB_PORT: db.dbInstanceEndpointPort,
      DB_NAME: dbName,
    };
    const dbSecrets: Record<string, ecs.Secret> = {
      DB_USER: ecs.Secret.fromSecretsManager(dbSecret, 'username'),
      DB_PASS: ecs.Secret.fromSecretsManager(dbSecret, 'password'),
    };
    const exportDbUrl =
      'export AIGW_DATABASE_URL="postgresql+psycopg://${DB_USER}:${DB_PASS}@${DB_HOST}:${DB_PORT}/${DB_NAME}"';

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

    // Inner commands come straight from each Dockerfile's CMD; we prepend the
    // DATABASE_URL assembly, and (data plane) a self-compile of the config.
    // `exec` the final process so uvicorn (via uv) becomes the container's PID 1
    // and receives ECS SIGTERM for graceful shutdown during rolls/scale-in.
    const controlCmd =
      'uv run --package governance-api alembic -c control-plane/governance-api/alembic.ini upgrade head && ' +
      'exec uv run --package governance-api uvicorn governance_api.main:app --host 0.0.0.0 --port ' + CONTROL_PORT;
    // Compile the LiteLLM config from the DB, then start the proxy. If the
    // registry is empty (fresh deploy) the compile still writes an empty
    // model_list and the entrypoint's fallback wires custom_auth, so the proxy
    // comes up healthy.
    const dataCmd =
      'uv run --package aigw-hooks python scripts/compile_config.py || echo "compile_config failed; using template"; ' +
      'exec uv run --package aigw-hooks bash data-plane/litellm/entrypoint.sh';

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
        AIGW_LITELLM_CONFIG_PATH: configPath, // local; used by POST /config/compile for validation
        AIGW_ENVIRONMENT: 'aws',
      },
      secrets: dbSecrets,
      entryPoint: ['/bin/sh', '-c'],
      command: [`${exportDbUrl} && ${controlCmd}`],
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
        AIGW_LITELLM_CONFIG: configPath, // entrypoint reads this
        AIGW_LITELLM_CONFIG_PATH: configPath, // compile_config.py writes this
        AIGW_PROXY_PORT: DATA_PORT.toString(),
      },
      secrets: dbSecrets,
      entryPoint: ['/bin/sh', '-c'],
      command: [`${exportDbUrl} && ${dataCmd}`],
      healthCheckGracePeriod: Duration.seconds(150),
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

    // ---- Connectivity: control + data planes -> RDS (5432) -------------
    for (const svc of [control.service, data.service]) {
      db.connections.allowDefaultPortFrom(svc, 'gateway service to RDS');
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

    // Default: the SPA. ALB allows at most 5 path values per condition, so each
    // rule stays <= 5. `/api/*` covers every control-plane route (all under
    // /api/v1); `/v1/*` covers the OpenAI surface. The prefixes are disjoint.
    listener.addTargetGroups('Default', { targetGroups: [uiTg] });
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
          '/v1/*', '/health/*', '/models*', '/chat/*', '/embeddings*',
        ]),
      ],
      targetGroups: [dataTg],
    });

    // =====================================================================
    // Phase 1 · Seed task (optional) — demo data in the DB
    // =====================================================================
    // Not run automatically. After deploy, `aws ecs run-task` this once to seed
    // a demo org/team/models/key. Seeded demo models point at a stub that is NOT
    // deployed on AWS, so this exercises the control plane + UI; for a real /v1
    // call, register a Bedrock model instead. (The data plane self-compiles at
    // boot, so a data-plane roll after seeding picks the models up.)
    const seedSg = new ec2.SecurityGroup(this, 'SeedSg', {
      vpc,
      description: 'AI Gateway one-shot seed task',
    });
    db.connections.allowDefaultPortFrom(seedSg, 'seed task to RDS');

    const seedTask = new ecs.FargateTaskDefinition(this, 'SeedTask', {
      cpu: 512,
      memoryLimitMiB: 1024,
    });
    seedTask.addContainer('seed', {
      image: controlImage,
      logging: ecs.LogDrivers.awsLogs({ streamPrefix: 'seed', logGroup }),
      environment: {
        ...dbEnvironment,
        AIGW_LITELLM_CONFIG_PATH: configPath, // local; discarded
        AIGW_STUB_URL: 'http://stub-provider:9099', // not deployed; demo only
      },
      secrets: dbSecrets,
      entryPoint: ['/bin/sh', '-c'],
      command: [`${exportDbUrl} && exec uv run --package governance-api python scripts/seed.py`],
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
      description: 'RDS credentials secret (username/password/host/port)',
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
