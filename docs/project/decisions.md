# Decisions Log

| # | Decision | Reasoning |
|---|----------|-----------|
| 1 | HTTP only (no HTTPS) | No certificate ARN provided; simplifies MVP deployment |
| 2 | WAF REGIONAL scope | WAF with CLOUDFRONT scope must be in us-east-1; our stack is eu-central-1 |
| 3 | ECS circuit breaker + auto-rollback | Prevents stuck deployments; auto-recovers from bad deploys |
| 4 | ECS Exec enabled | Allows `aws ecs execute-command` for live container debugging |
| 5 | `--platform=linux/amd64` in Dockerfile | Fixes ARM64/AMD64 mismatch when building on Apple Silicon for Fargate x86_64 |
| 6 | `/tmp/rendered` for temp storage | Fargate containers have read-only root FS; `/tmp` is writable |
| 7 | 120s health check start period | ECS tasks need time for container startup + pip install; prevents premature kill |
| 8 | 180s service stabilization grace period | Gives ECS time to register healthy targets before circuit breaker triggers |
| 9 | Lazy imports in renderer.py | Avoids import-time crashes when boto3/Pillow not yet available at module load |
| 10 | Minimal stdlib HTTP server for debugging | Used temporarily to isolate Fargate startup issues from FastAPI complexity |
| 11 | SQS long-polling loop in render worker | Worker must have a long-running process; short-lived tasks get killed by Fargate |
| 12 | Non-root Docker user (`appuser`) | Security best practice for container workloads |
| 13 | 5 separate CDK stacks | Allows independent deployment and rollback of each layer |
