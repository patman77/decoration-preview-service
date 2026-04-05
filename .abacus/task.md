# Current Task

## Deploy and verify full API

**Status**: Ready to execute

**Steps**:
1. `./deploy.sh bootstrap` from repo root
2. Wait for all 5 stacks → CREATE_COMPLETE
3. Get ALB DNS from CloudFormation outputs
4. `curl http://<alb-dns>/health`
5. `curl http://<alb-dns>/api/v1/elements`
6. `curl -X POST http://<alb-dns>/api/v1/render -H 'Content-Type: application/json' -d '{"element_id": "test", "artwork_url": "..."}'`
7. Check CloudWatch for render worker activity

**Success**: All endpoints respond, render worker processes SQS message
