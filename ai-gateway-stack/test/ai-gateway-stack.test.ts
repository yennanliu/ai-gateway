import * as cdk from 'aws-cdk-lib/core';
import { Template } from 'aws-cdk-lib/assertions';
import { AiGatewayStack } from '../lib/ai-gateway-stack';

/**
 * Phase 1 shape assertions. These are structural (counts / key properties), not
 * a full snapshot, so they stay stable as the stack grows into Phase 2.
 *
 * The optional LiteLLM native Admin UI is ON by default (`-c litellmUi=false`
 * disables it) and stands up its OWN isolated service + target group. These
 * core-topology assertions disable it so they measure only the governed stack;
 * the default-on behavior is covered separately below.
 */
function synth(context: Record<string, unknown> = { litellmUi: false }): Template {
  const app = new cdk.App({ context });
  const stack = new AiGatewayStack(app, 'TestStack', { resourceName: 'ai-gateway-test' });
  return Template.fromStack(stack);
}

test('deploys both planes plus the UI: three ECS services', () => {
  synth().resourceCountIs('AWS::ECS::Service', 3);
});

test('a single RDS PostgreSQL instance is the shared source of truth', () => {
  const t = synth();
  t.resourceCountIs('AWS::RDS::DBInstance', 1);
  t.hasResourceProperties('AWS::RDS::DBInstance', { Engine: 'postgres' });
});

test('one public, internet-facing ALB fronts the stack', () => {
  const t = synth();
  t.resourceCountIs('AWS::ElasticLoadBalancingV2::LoadBalancer', 1);
  t.hasResourceProperties('AWS::ElasticLoadBalancingV2::LoadBalancer', { Scheme: 'internet-facing' });
});

test('no shared filesystem: the data plane self-compiles config at boot', () => {
  synth().resourceCountIs('AWS::EFS::FileSystem', 0);
});

test('path routing splits /api, /v1 and the default UI target', () => {
  // Default + two prefix rules => three target groups behind one listener.
  synth().resourceCountIs('AWS::ElasticLoadBalancingV2::TargetGroup', 3);
});

test('the LiteLLM native Admin UI is on by default: a fourth, isolated service', () => {
  // No context => default-on. The optional UI adds its own service + target
  // group + a dedicated listener, without touching the three governed services.
  const t = synth({});
  t.resourceCountIs('AWS::ECS::Service', 4);
  t.resourceCountIs('AWS::ElasticLoadBalancingV2::TargetGroup', 4);
  // Its own edge listener on :4001, separate from the :80 governed listener.
  t.resourceCountIs('AWS::ElasticLoadBalancingV2::Listener', 2);
});

test('the LiteLLM native Admin UI is disabled with -c litellmUi=false', () => {
  const t = synth({ litellmUi: false });
  t.resourceCountIs('AWS::ECS::Service', 3);
  t.resourceCountIs('AWS::ElasticLoadBalancingV2::TargetGroup', 3);
  t.resourceCountIs('AWS::ElasticLoadBalancingV2::Listener', 1);
});
