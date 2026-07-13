#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib/core';
import { AiGatewayStackStack } from '../lib/ai-gateway-stack-stack';

const app = new cdk.App();
new AiGatewayStackStack(app, 'AiGatewayStackStack');
