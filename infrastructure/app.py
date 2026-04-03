#!/usr/bin/env python3
"""AWS CDK application entry point.

Defines the CDK app and instantiates all stacks.
Deploy with: cdk deploy --all
"""

import aws_cdk as cdk

from stacks.network_stack import NetworkStack
from stacks.storage_stack import StorageStack
from stacks.compute_stack import ComputeStack
from stacks.api_stack import ApiStack
from stacks.monitoring_stack import MonitoringStack

app = cdk.App()

# Environment configuration
env = cdk.Environment(
    account=app.node.try_get_context("account") or "123456789012",
    region=app.node.try_get_context("region") or "eu-central-1",
)

project_name = "decoration-preview"

# Stack deployment order follows dependency graph
network_stack = NetworkStack(
    app, f"{project_name}-network",
    env=env,
    description="VPC and networking resources for Decoration Preview Service",
)

storage_stack = StorageStack(
    app, f"{project_name}-storage",
    env=env,
    description="S3 buckets, DynamoDB tables, and SQS queues",
)

compute_stack = ComputeStack(
    app, f"{project_name}-compute",
    vpc=network_stack.vpc,
    storage=storage_stack,
    env=env,
    description="ECS Fargate cluster and task definitions for rendering",
)

api_stack = ApiStack(
    app, f"{project_name}-api",
    vpc=network_stack.vpc,
    storage=storage_stack,
    compute=compute_stack,
    env=env,
    description="API Gateway, CloudFront, and API service configuration",
)

monitoring_stack = MonitoringStack(
    app, f"{project_name}-monitoring",
    compute=compute_stack,
    storage=storage_stack,
    env=env,
    description="CloudWatch dashboards, alarms, and logging configuration",
)

# Add tags to all resources
cdk.Tags.of(app).add("Project", "decoration-preview-service")
cdk.Tags.of(app).add("ManagedBy", "CDK")
cdk.Tags.of(app).add("Environment", app.node.try_get_context("environment") or "production")

app.synth()
