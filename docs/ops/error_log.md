# Error Log

| # | Error | Root Cause | Fix |
|---|-------|------------|-----|
| 1 | Dockerfile COPY failed | Wrong `requirements.txt` path | Fixed COPY path |
| 2 | `RetentionDays.THIRTY_DAYS` not found | CDK enum name changed | Use `ONE_MONTH` |
| 3 | HTTPS listener failed | No ACM certificate | Made HTTPS conditional on `CERTIFICATE_ARN` |
| 4 | WAF creation failed | `CLOUDFRONT` scope needs us-east-1 | Changed to `REGIONAL` |
| 5 | RenderService keeps restarting | No long-running process | Added SQS long-polling loop |
| 6 | ECS exec format error | ARM64 image on AMD64 Fargate | `--platform=linux/amd64` in Dockerfile |
| 7 | renderer.py import crash | boto3/Pillow imported at module level | Lazy initialization |
| 8 | Health check → circuit breaker | Timeouts too aggressive for cold start | 120s start, 180s grace |
| 9 | Stacks stuck in CREATE_IN_PROGRESS | Failed resources blocking ops | `deploy.sh cancel-stuck` |
