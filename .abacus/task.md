# Current Task

## Deploy with full API and verify endpoints

**Status**: Ready to execute

**Steps**:
1. Run `./deploy.sh bootstrap` from `deployment/aws-setup` branch
2. Wait for all 5 stacks to reach CREATE_COMPLETE
3. Get ALB DNS from CloudFormation outputs
4. Test: `curl http://<alb-dns>/health`
5. Test: `curl http://<alb-dns>/api/v1/elements`
6. Test: `curl -X POST http://<alb-dns>/api/v1/render -H 'Content-Type: application/json' -d '{...}'`
7. Check CloudWatch logs for render worker activity

**Success criteria**: All endpoints return expected responses, render worker picks up SQS message
