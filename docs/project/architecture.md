# Architecture

## System Overview

```
Client → CloudFront → ALB → ECS ApiService (FastAPI :8000)
                                  ↓
                              SQS Queue → ECS RenderService (Worker)
                                  ↓
                          DynamoDB (status) + S3 (output)
```

## CDK Stacks (5)

| Stack | Key Resources |
|-------|---------------|
| **NetworkStack** | VPC, public/private subnets, NAT gateway |
| **StorageStack** | S3 buckets, DynamoDB jobs table, SQS queue + DLQ |
| **ComputeStack** | ECS cluster, Fargate task defs, ApiService, RenderService |
| **ApiStack** | ALB, CloudFront distribution, WAF (REGIONAL scope) |
| **MonitoringStack** | CloudWatch alarms, log groups |

## Sync Flow

1. `POST /api/v1/render` → validate → create DynamoDB job → send SQS message → return `job_id`
2. `GET /api/v1/render/{job_id}` → read DynamoDB → return status + result URL

## Async Flow (Render Worker)

1. Long-poll SQS queue
2. Download artwork + element from S3
3. Render composite image (Pillow)
4. Upload result to S3
5. Update DynamoDB status → webhook callback (if configured)
6. Delete SQS message; failures go to DLQ

## Key Files

| File | Purpose |
|------|---------|
| `backend/app/main.py` | FastAPI entry point, routes, error handlers |
| `backend/app/workers/renderer.py` | SQS polling loop, image processing |
| `backend/Dockerfile` | Container build (linux/amd64, non-root user) |
| `infrastructure/stacks/compute_stack.py` | ECS services, task definitions |
| `infrastructure/stacks/api_stack.py` | ALB, CloudFront, WAF |
| `deploy.sh` | CDK deploy orchestrator + troubleshooting |
