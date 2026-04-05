# Decisions Log

| # | Decision | Reasoning |
|---|----------|-----------|
| 1 | HTTP only (no HTTPS) | No certificate ARN; simplifies MVP |
| 2 | WAF REGIONAL scope | CLOUDFRONT scope requires us-east-1; stacks are in eu-central-1 |
| 3 | ECS circuit breaker + auto-rollback | Prevents stuck deployments |
| 4 | ECS Exec enabled | Live debugging via `aws ecs execute-command` |
| 5 | `--platform=linux/amd64` in Dockerfile | Fixes ARM64→AMD64 mismatch building on Apple Silicon |
| 6 | `/tmp/rendered` for temp files | Fargate has read-only root FS; `/tmp` is writable |
| 7 | 120s health check start period | Cold start needs time; prevents premature ECS kill |
| 8 | 180s service stabilization grace | ECS needs time to register targets before circuit breaker |
| 9 | Lazy imports in renderer.py | Avoids import-time crashes before deps available |
| 10 | SQS long-polling in render worker | Worker needs long-running process; short tasks get killed |
| 11 | Non-root Docker user (`appuser`) | Container security best practice |
| 12 | 5 separate CDK stacks | Independent deployment/rollback per layer |
| 13 | Single `main` branch | Consolidated from multiple feature branches for simplicity |
