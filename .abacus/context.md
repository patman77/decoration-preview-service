# Context

## System

- **Project**: decoration-preview-service
- **Stack**: Python 3.11, FastAPI, AWS CDK, ECS Fargate, SQS, DynamoDB, S3
- **Region**: eu-central-1 | **Account**: 414773530481
- **Repo**: github.com/patman77/decoration-preview-service

## Goal

Deploy async decoration preview API to AWS — accept artwork + element, render composite, return via S3.

## Architecture

- ApiService: FastAPI → ALB → CloudFront (HTTP only)
- RenderService: SQS worker → S3 + DynamoDB
- 5 CDK stacks: network, storage, api, compute, monitoring

## Current Phase

**Phase: Post-deployment verification**

- ✅ All 5 CDK stacks deploy successfully
- ✅ Docker images build for linux/amd64
- ✅ Full API endpoints restored (PR #9)
- 🔧 Need to verify full API after deploy
- 🔧 Need to test SQS → render worker flow

## Active Branch

`deployment/aws-setup` — all fixes merged, ready for deploy verification

## Key Decisions

- HTTP only (no cert)
- WAF REGIONAL (not CLOUDFRONT)
- ECS circuit breaker + auto-rollback
- 120s/180s health check timeouts
