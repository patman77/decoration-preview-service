# Product Brief

## Goal

Async decoration preview service on AWS — accept artwork + 3D element, render composite image, return via S3.

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
- **Deploy**: `./deploy.sh bootstrap` from repo root

## Non-Goals (MVP)

- No HTTPS / custom domain (no certificate ARN)
- No CI/CD pipeline (manual deploy via `deploy.sh`)
- No user authentication / multi-tenancy
- No GPU rendering
- No auto-scaling (fixed Fargate task count)
- No production monitoring dashboards
