# Error Log

| # | Error | Root Cause | Resolution |
|---|-------|-----------|------------|
| 1 | Dockerfile COPY failed | `requirements.txt` path wrong in COPY command | Fixed path to `backend/requirements.txt` |
| 2 | `RetentionDays.THIRTY_DAYS` not found | CDK API changed enum name | Changed to `RetentionDays.ONE_MONTH` |
| 3 | HTTPS listener creation failed | No ACM certificate ARN configured | Made HTTPS conditional on `CERTIFICATE_ARN` env var |
| 4 | WAF creation failed (wrong region) | `CLOUDFRONT` scope requires us-east-1 | Changed WAF scope to `REGIONAL` |
| 5 | RenderService task kept restarting | No long-running process in container | Added SQS long-polling loop as main process |
| 6 | ECS task exec format error | ARM64 image on AMD64 Fargate | Added `--platform=linux/amd64` to Dockerfile |
| 7 | Import crash in renderer.py | boto3/Pillow imported at module level before available | Switched to lazy initialization pattern |
| 8 | Health check failures → circuit breaker | Default timeouts too aggressive for cold start | Extended to 120s start period, 180s grace period |
| 9 | Stacks stuck in CREATE_IN_PROGRESS | Failed resources blocking stack operations | Added `cancel-stuck` command to `deploy.sh` |
