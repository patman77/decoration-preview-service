# Architecture

## System Components

```
Client → CloudFront → ALB → ECS ApiService (FastAPI)
                                  ↓
                              SQS Queue → ECS RenderService (Worker)
                                  ↓
                          DynamoDB (status) + S3 (output)
```

## CDK Stacks (5)

| Stack | Resources |
|-------|----------|
| **NetworkStack** | VPC, public/private subnets, NAT gateway |
| **StorageStack** | S3 buckets (artwork, elements, renders), DynamoDB jobs table, SQS queue + DLQ |
| **ComputeStack** | ECS cluster, Fargate task defs, ApiService, RenderService |
| **ApiStack** | ALB, CloudFront distribution, WAF (REGIONAL) |
| **MonitoringStack** | CloudWatch alarms, log groups |

## Request Flow (Sync)

1. `POST /api/v1/render` → validate input → create DynamoDB job → send SQS message → return `job_id`
2. `GET /api/v1/render/{job_id}` → read DynamoDB → return status + result URL

## Async Flow (Render Worker)

1. Poll SQS queue (long polling)
2. Download artwork + element from S3
3. Render composite image (Pillow)
4. Upload result to S3 renders bucket
5. Update DynamoDB job status → send webhook callback (if configured)
6. Delete SQS message on success; DLQ on failure

## Deployment

- **Platform**: ECS Fargate (linux/amd64)
- **Docker**: Multi-stage build, non-root user, health check built-in
- **Deploy tool**: `deploy.sh bootstrap` — runs pre-flight checks, CDK synth + deploy
- **ECS**: Circuit breaker with auto-rollback, ECS Exec enabled
- **WAF**: REGIONAL scope, rate-limiting + AWS managed rules
- **HTTPS**: Disabled (no certificate ARN) — HTTP-only ALB
