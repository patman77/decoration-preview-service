# Context

## System

- **Project**: decoration-preview-service
- **Tech**: Python 3.11, FastAPI, Uvicorn, AWS CDK, boto3, Pillow
- **Infra**: ECS Fargate, ALB, CloudFront, SQS, DynamoDB, S3, WAF
- **Region**: eu-central-1 | **Account**: 414773530481
- **Repo**: github.com/patman77/decoration-preview-service

## Goal

Async decoration preview API — accept artwork + element, render composite, return via S3.

## Architecture

- ApiService: FastAPI → ALB → CloudFront (HTTP only)
- RenderService: SQS long-poll worker → S3 + DynamoDB
- 5 CDK stacks: network, storage, api, compute, monitoring

## Current Phase

**Post-consolidation, pre-deploy verification**

- ✅ All branches merged to `main`
- ✅ All 5 CDK stacks deploy
- ✅ Docker images build (linux/amd64)
- ✅ Full API endpoints restored
- 🔧 Verify endpoints after fresh deploy
- 🔧 Test SQS → render worker flow

## Active Branch

`main` — single branch, all work consolidated
