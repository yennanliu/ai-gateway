import { Duration } from 'aws-cdk-lib/core';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as logs from 'aws-cdk-lib/aws-logs';
import { Construct } from 'constructs';

export interface FargateAppServiceProps {
  readonly cluster: ecs.ICluster;
  /** Human-readable service name; also used as the CloudWatch stream prefix. */
  readonly serviceName: string;
  readonly image: ecs.ContainerImage;
  readonly containerPort: number;
  readonly logGroup: logs.ILogGroup;

  readonly cpu?: number;
  readonly memoryLimitMiB?: number;
  readonly desiredCount?: number;
  readonly environment?: Record<string, string>;
  readonly secrets?: Record<string, ecs.Secret>;
  /** Override the image ENTRYPOINT (e.g. `['/bin/sh','-c']`). */
  readonly entryPoint?: string[];
  /** Override the image CMD. */
  readonly command?: string[];
  /** Grace period before the load balancer health check can fail a task. */
  readonly healthCheckGracePeriod?: Duration;
}

/**
 * One long-running Fargate service: a task definition (single app container)
 * plus a service placed in private-with-egress subnets.
 *
 * The service creates its own security group; callers wire ingress/egress via
 * `service.connections` (ALB -> service, service -> RDS).
 */
export class FargateAppService extends Construct {
  public readonly service: ecs.FargateService;
  public readonly taskDefinition: ecs.FargateTaskDefinition;
  public readonly container: ecs.ContainerDefinition;

  constructor(scope: Construct, id: string, props: FargateAppServiceProps) {
    super(scope, id);

    this.taskDefinition = new ecs.FargateTaskDefinition(this, 'Task', {
      cpu: props.cpu ?? 512,
      memoryLimitMiB: props.memoryLimitMiB ?? 1024,
    });

    this.container = this.taskDefinition.addContainer('app', {
      image: props.image,
      logging: ecs.LogDrivers.awsLogs({ streamPrefix: props.serviceName, logGroup: props.logGroup }),
      environment: props.environment,
      secrets: props.secrets,
      entryPoint: props.entryPoint,
      command: props.command,
      portMappings: [{ containerPort: props.containerPort }],
    });

    this.service = new ecs.FargateService(this, 'Service', {
      cluster: props.cluster,
      serviceName: props.serviceName,
      taskDefinition: this.taskDefinition,
      desiredCount: props.desiredCount ?? 1,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      healthCheckGracePeriod: props.healthCheckGracePeriod,
      // Hold full capacity during rolling deploys and roll back a wedged one
      // instead of churning unhealthy tasks for hours.
      minHealthyPercent: 100,
      circuitBreaker: { rollback: true },
    });
  }
}
