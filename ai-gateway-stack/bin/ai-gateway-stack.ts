#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib/core';
import { AiGatewayStack } from '../lib/ai-gateway-stack';

const app = new cdk.App();

// Single knob for the deploy's identity. Bump the version (v1 -> v2) to stand up
// a fresh, independently-named stack (and its DB / ECS / ALB) alongside or in
// place of the old one — makes teardown and re-deploy easy to track.
// Override at deploy time: `-c appName=... -c version=...`.
const appName = (app.node.tryGetContext('appName') as string | undefined) ?? 'ai-gateway';
const version = (app.node.tryGetContext('version') as string | undefined) ?? 'v1';
const resourceName = `${appName}-${version}`;

new AiGatewayStack(app, resourceName, {
  stackName: resourceName,
  resourceName,
  // Uses CDK_DEFAULT_ACCOUNT/REGION from your environment. Set explicitly for
  // cross-account/region deploys.
  env: { account: process.env.CDK_DEFAULT_ACCOUNT, region: process.env.CDK_DEFAULT_REGION },
});
