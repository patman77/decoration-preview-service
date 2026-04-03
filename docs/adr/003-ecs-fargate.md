# ADR 003: ECS Fargate for Container Orchestration

## Status

Accepted

## Context

We need a container runtime for both the API service and render workers. Options:

1. **ECS Fargate** — Serverless containers
2. **ECS on EC2** — Self-managed container instances
3. **EKS (Kubernetes)** — Managed Kubernetes
4. **AWS Lambda** — Serverless functions

## Decision

We chose **ECS Fargate** for both API and render workers.

## Rationale

1. **Operational simplicity**: No EC2 instances to patch, no Kubernetes cluster to manage. Fargate handles OS updates, scaling, and placement.

2. **Right-sized resources**: Each task gets exactly the CPU and memory it needs. API tasks: 0.5 vCPU / 1 GB. Render tasks: 2 vCPU / 4 GB.

3. **Auto-scaling**: Fargate scales tasks independently. API scales on CPU; workers scale on queue depth.

4. **Cost model**: Pay per task-second. Render workers can scale to zero. Fargate Spot provides up to 70% discount for fault-tolerant workloads.

5. **Security**: Each task runs in its own isolated environment with its own ENI and security group.

6. **Team size**: EKS requires dedicated platform engineering. Fargate is manageable by the application team.

## Consequences

- **Positive**: Zero server management, automatic patching
- **Positive**: Per-second billing, scale-to-zero workers
- **Positive**: Strong security isolation per task
- **Negative**: No GPU support on Fargate (future: ECS on p3/g4 EC2 for production rendering)
- **Negative**: Maximum 4 vCPU / 30 GB per task (sufficient for current needs)
- **Migration path**: Move render workers to ECS on GPU EC2 when needed, keeping API on Fargate
