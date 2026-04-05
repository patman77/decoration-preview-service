# Product Brief

## Goal

Deploy a **production-grade async decoration preview service** to AWS using ECS Fargate.

- Accept artwork + 3D element → render a decorated preview image
- Async processing via SQS with job status tracking in DynamoDB
- Fully automated infrastructure via AWS CDK

## MVP Scope

- **API Service**: FastAPI on ECS Fargate behind ALB + CloudFront
  - `POST /api/v1/render` — submit render job
  - `GET /api/v1/render/{job_id}` — poll job status
  - `GET /api/v1/elements` — list available 3D elements
  - `GET /health` — health check
- **Render Worker**: SQS consumer on ECS Fargate
  - Polls render queue, processes jobs, writes output to S3
  - Updates DynamoDB job status, sends webhook callbacks
- **Storage**: S3 (artwork, elements, renders), DynamoDB (jobs), SQS (queue + DLQ)
- **Infrastructure**: 5 CDK stacks — network, storage, api, compute, monitoring
- **Region**: eu-central-1

## Non-Goals

- No custom domain / HTTPS (no certificate ARN provided)
- No CI/CD pipeline (manual deploy via `deploy.sh`)
- No user authentication / multi-tenancy
- No GPU-based rendering
- No auto-scaling (fixed Fargate task count for MVP)
- No production monitoring dashboards (basic CloudWatch only)
