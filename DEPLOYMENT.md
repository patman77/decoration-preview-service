# Decoration Preview Service — AWS Deployment Guide

This guide walks you through deploying the **Decoration Preview Service** to AWS using **AWS CDK** (Cloud Development Kit) with Python.

---

## Architecture Overview

```
Designer → CloudFront → ALB → FastAPI API → SQS Queue → ECS Render Workers
                                    ↕                          ↕
                              DynamoDB (jobs)        S3 (artwork/renders)
```

The deployment creates **5 CDK stacks** (deployed in dependency order):

| Stack | Resources Created |
|-------|-------------------|
| `decoration-preview-network` | VPC, subnets (public/private/isolated), NAT Gateway, security groups, VPC Flow Logs |
| `decoration-preview-storage` | 3 S3 buckets (artwork, elements, renders), DynamoDB table, SQS queue + DLQ, KMS key |
| `decoration-preview-compute` | ECS Fargate cluster, API service (2-10 tasks), Render workers (0-50 tasks), IAM roles |
| `decoration-preview-api` | Application Load Balancer, CloudFront distribution, WAF WebACL |
| `decoration-preview-monitoring` | CloudWatch dashboard, CPU/queue/DLQ alarms, SNS alert topic |

---

## Prerequisites

Before deploying, ensure you have the following installed on your machine:

| Tool | Minimum Version | Installation |
|------|----------------|--------------|
| **Python** | 3.11+ | [python.org](https://www.python.org/downloads/) |
| **Node.js** | 18+ | [nodejs.org](https://nodejs.org/) (required by CDK CLI) |
| **AWS CLI** | 2.x | [AWS CLI Install Guide](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html) |
| **AWS CDK CLI** | 2.177+ | `npm install -g aws-cdk` |
| **Docker** | 20+ | [docker.com](https://docs.docker.com/get-docker/) |
| **pip** | latest | Comes with Python |

---

## Step-by-Step Deployment

### Step 1: Configure AWS Credentials

```bash
# Option A: Interactive configuration
aws configure
# Enter: AWS Access Key ID, Secret Access Key, Region (eu-central-1), Output format (json)

# Option B: Use environment variables
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_DEFAULT_REGION="eu-central-1"

# Option C: Use AWS SSO
aws configure sso
```

Verify credentials are working:
```bash
aws sts get-caller-identity
# Should return: Account, UserId, Arn
```

### Step 2: Clone & Set Up the Project

```bash
git clone https://github.com/patman77/decoration-preview-service.git
cd decoration-preview-service

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

# Install all dependencies (app + CDK)
pip install -r requirements.txt
```

### Step 3: Configure Environment Variables

```bash
# Copy the production template
cp .env.production.template .env.production

# Edit with your values
nano .env.production
```

**Critical settings to update:**
- `API_KEY` — Generate with: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
- `AWS_ACCOUNT_ID` — Your 12-digit AWS account ID
- `AWS_REGION` — Target region (default: `eu-central-1`)

### Step 4: Update CDK Configuration

The `deploy.sh` script handles this automatically, but to do it manually:

```bash
# Get your AWS account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Update infrastructure/cdk.json
cat > infrastructure/cdk.json <<EOF
{
  "app": "python3 app.py",
  "context": {
    "account": "${AWS_ACCOUNT_ID}",
    "region": "eu-central-1",
    "environment": "production"
  }
}
EOF
```

### Step 5: Bootstrap CDK (First Time Only)

CDK bootstrap creates an S3 bucket and IAM roles in your account that CDK uses to deploy:

```bash
# Using the deploy script (recommended)
chmod +x deploy.sh
./deploy.sh bootstrap

# Or manually
cd infrastructure
cdk bootstrap aws://${AWS_ACCOUNT_ID}/eu-central-1
```

### Step 6: Preview Changes (Recommended)

```bash
# See what will be created
./deploy.sh synth

# Compare with what's currently deployed
./deploy.sh diff
```

### Step 7: Deploy to AWS

```bash
# Deploy all 5 stacks (takes ~15-25 minutes on first deploy)
./deploy.sh deploy
```

Or deploy stacks individually (in order):

```bash
./deploy.sh deploy-stack decoration-preview-network
./deploy.sh deploy-stack decoration-preview-storage
./deploy.sh deploy-stack decoration-preview-compute
./deploy.sh deploy-stack decoration-preview-api
./deploy.sh deploy-stack decoration-preview-monitoring
```

### Step 8: Verify Deployment

```bash
# Show all stack outputs (ALB DNS, CloudFront domain, etc.)
./deploy.sh status

# Test the health endpoint via the ALB
ALB_DNS=$(aws cloudformation describe-stacks \
  --stack-name decoration-preview-api \
  --query 'Stacks[0].Outputs[?OutputKey==`AlbDnsName`].OutputValue' \
  --output text)

curl -s "http://${ALB_DNS}/health" | jq .
```

### Step 9: Subscribe to Alerts (Optional)

```bash
# Get the SNS topic ARN
ALERTS_ARN=$(aws cloudformation describe-stacks \
  --stack-name decoration-preview-monitoring \
  --query 'Stacks[0].Outputs[?OutputKey==`AlertsTopicArn`].OutputValue' \
  --output text)

# Subscribe your email
aws sns subscribe \
  --topic-arn "${ALERTS_ARN}" \
  --protocol email \
  --notification-endpoint your-team@example.com
```

---

## Testing the Deployed Service

```bash
# Set your ALB or CloudFront URL
export SERVICE_URL="http://${ALB_DNS}"
# Or after DNS setup: export SERVICE_URL="https://your-domain.com"

# Health check
curl -s "${SERVICE_URL}/health" | jq .

# List available elements
curl -s "${SERVICE_URL}/api/v1/elements" \
  -H "X-API-Key: YOUR_PRODUCTION_API_KEY" | jq .

# Submit a render job
curl -X POST "${SERVICE_URL}/api/v1/render" \
  -H "X-API-Key: YOUR_PRODUCTION_API_KEY" \
  -F "artwork_file=@examples/sample_artwork.png" \
  -F "element_id=elem-minifig-torso-001" \
  -F "output_format=png" | jq .
```

---

## Adding HTTPS / SSL Certificate (Optional)

By default the ALB is deployed in **HTTP-only** mode so you can get started without
a certificate. CloudFront still serves end-user traffic over HTTPS — the HTTP-only
part is only the connection between CloudFront and the ALB (within AWS).

When you're ready to add TLS to the ALB:

1. **Request an ACM certificate** in the same region as your deployment:
   ```bash
   aws acm request-certificate \
     --domain-name your-domain.com \
     --validation-method DNS \
     --region eu-central-1
   ```
2. **Validate the certificate** by adding the CNAME records that ACM provides (see the
   AWS Console → Certificate Manager → your certificate → "Create records in Route 53").
3. **Set the certificate ARN** before deploying:
   ```bash
   # Option A: Environment variable
   export CERTIFICATE_ARN="arn:aws:acm:eu-central-1:123456789012:certificate/abc-123"

   # Option B: CDK context in infrastructure/cdk.json
   # Add "certificate_arn": "arn:aws:acm:..." inside the "context" block
   ```
4. **Re-deploy** the API stack:
   ```bash
   ./deploy.sh deploy
   ```

After redeployment the ALB will serve HTTPS on port 443 and the HTTP listener
will redirect to HTTPS automatically.

---

## Production Checklist

Before going live, ensure:

- [ ] **API Key** — Generated and set to a strong secret (not the dev default)
- [ ] **HTTPS Certificate** — (Recommended) Create an ACM certificate and enable HTTPS (see above)
- [ ] **Custom Domain** — Configure Route 53 or your DNS to point to CloudFront/ALB
- [ ] **Alert Subscription** — Subscribe your team email to the SNS alerts topic
- [ ] **WAF Rules** — Review and customize WAF rules for your traffic patterns (see WAF notes below)
- [ ] **S3 CORS** — Restrict `allowed_origins` in `storage_stack.py` from `*` to your domain(s)
- [ ] **Secrets Manager** — Move `API_KEY` to AWS Secrets Manager for rotation support
- [ ] **Backup Policy** — Verify DynamoDB point-in-time recovery is enabled (it is by default)
- [ ] **Cost Alerts** — Set up AWS Budgets for cost monitoring
- [ ] **Logging** — Verify CloudWatch log groups are receiving logs

---

## WAF (Web Application Firewall) Notes

The deployment includes a **REGIONAL** WAF WebACL attached to the Application
Load Balancer. This protects the ALB (and the ECS services behind it) with:

- **Rate limiting** — 1 000 requests per 5-minute window per IP
- **AWS Managed Common Rule Set** — blocks known malicious request patterns

### Why not a CloudFront WAF?

AWS WAFv2 WebACLs with `CLOUDFRONT` scope **must** be created in
**us-east-1**, because CloudFront is a global service. When the stack is
deployed to any other region (e.g. `eu-central-1`) a `CLOUDFRONT`-scoped ACL
will fail with:

> *The scope is not valid., field: SCOPE_VALUE, parameter: CLOUDFRONT*

To keep the deployment region-agnostic the WAF uses `REGIONAL` scope and
protects the ALB directly.

### Adding CloudFront WAF protection later

If you need WAF rules at the CloudFront edge:

1. Create a **separate CDK stack** (or CloudFormation template) that deploys
   **only** in `us-east-1`.
2. In that stack create a `CfnWebACL` with `scope="CLOUDFRONT"`.
3. Pass the WebACL ARN to the main stack and set
   `web_acl_id=<arn>` on the `cloudfront.Distribution`.

This two-stack pattern is the standard AWS approach for multi-region
deployments that need CloudFront-level WAF.

---

## Estimated AWS Costs

| Resource | Configuration | Est. Monthly Cost |
|----------|--------------|-------------------|
| ECS Fargate (API) | 2 tasks × 0.5 vCPU / 1 GB | ~$30 |
| ECS Fargate (Render) | 0-50 tasks × 2 vCPU / 4 GB | $0-$400+ (scales) |
| NAT Gateway | 1 gateway | ~$32 |
| ALB | 1 load balancer | ~$22 |
| S3 | 3 buckets | ~$5-20 (usage based) |
| DynamoDB | On-demand | ~$2-10 (usage based) |
| CloudFront | Standard tier | ~$5-50 (usage based) |
| CloudWatch | Logs + dashboards | ~$5-15 |
| **Total (low traffic)** | | **~$100-130/month** |

> 💡 For development/staging, reduce costs by setting API `desired_count=1` and render `min_capacity=0`.

---

## Tear Down

```bash
# Destroy all CDK-managed resources
./deploy.sh destroy

# Note: S3 buckets with RemovalPolicy.RETAIN (artwork, elements) must be
# manually emptied and deleted via the AWS Console or CLI:
aws s3 rb s3://decoration-preview-artwork-YOUR_ACCOUNT_ID --force
aws s3 rb s3://decoration-preview-elements-YOUR_ACCOUNT_ID --force
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `cdk bootstrap` fails | Ensure your IAM user has `AdministratorAccess` or equivalent |
| Docker build fails | Check Docker daemon is running; ensure `requirements.txt` is in `backend/` |
| ECS tasks keep restarting | Check CloudWatch logs: `/ecs/decoration-preview/api` |
| ECS service stuck in CREATE_IN_PROGRESS | Run `./deploy.sh cancel-stuck`, then `cleanup`, then redeploy — see [Handling Stacks Stuck in CREATE_IN_PROGRESS](#handling-stacks-stuck-in-create_in_progress) |
| ALB health check fails | Verify security groups allow port 8000 from ALB |
| `No space left on device` | Docker disk space; run `docker system prune` |
| CDK synth import errors | Ensure `aws-cdk-lib` is installed: `pip install -r requirements.txt` |
| CloudFront 502 errors | ALB may not have healthy targets yet; wait for ECS tasks to start |
| HTTPS Listener needs certificate | Don't set `CERTIFICATE_ARN` until you have an ACM cert; ALB works fine with HTTP only |
| WAF scope error (`CLOUDFRONT` in non-us-east-1) | Ensure `api_stack.py` uses `scope="REGIONAL"` — see [WAF Notes](#waf-web-application-firewall-notes) |

### Handling Stacks Stuck in CREATE_IN_PROGRESS

When a CloudFormation stack hangs during creation (e.g. an ECS service waiting
for tasks to stabilize), it stays in `CREATE_IN_PROGRESS` indefinitely. **You
cannot update or redeploy a stack in this state** — the deployment will fail with:

> *Stack [name] is in CREATE_IN_PROGRESS state and can not be updated.*

This commonly happens with the `decoration-preview-compute` stack when the ECS
service (`ApiService/Service`) cannot reach a healthy state.

#### Quick fix — use the cancel-stuck command

```bash
# 1. Cancel stacks stuck in CREATE_IN_PROGRESS or UPDATE_IN_PROGRESS
./deploy.sh cancel-stuck

# 2. After rollback completes, clean up the ROLLBACK_COMPLETE stack
./deploy.sh cleanup

# 3. Redeploy
./deploy.sh deploy
```

The `cancel-stuck` command will:
- Show the last 5 stack events so you can see which resource is stuck
- For `CREATE_IN_PROGRESS` stacks: offer to **delete** the stack (the only
  option, since `cancel-update-in-progress` only works for updates)
- For `UPDATE_IN_PROGRESS` stacks: send a `cancel-update-in-progress` signal
  to trigger a rollback

#### Manual fix via AWS CLI

```bash
# 1. Check which stacks are stuck
aws cloudformation list-stacks \
  --stack-status-filter CREATE_IN_PROGRESS UPDATE_IN_PROGRESS \
  --query 'StackSummaries[*].[StackName,StackStatus,CreationTime]' \
  --output table

# 2a. For CREATE_IN_PROGRESS — delete the stack
aws cloudformation delete-stack --stack-name decoration-preview-compute
aws cloudformation wait stack-delete-complete --stack-name decoration-preview-compute

# 2b. For UPDATE_IN_PROGRESS — cancel the update
aws cloudformation cancel-update-in-progress --stack-name decoration-preview-compute
# Wait for it to reach UPDATE_ROLLBACK_COMPLETE

# 3. Redeploy
./deploy.sh deploy
```

#### Preventing future stuck deployments

- **Fix the root cause first**: before redeploying, check why the ECS tasks
  failed (see [ECS Service Deployment Hangs](#ecs-service-deployment-hangs))
- **Test locally**: `docker build -t test backend/ && docker run -p 8000:8000 test`
  then `curl localhost:8000/health`
- **Use `./deploy.sh ecs-status`** in a second terminal to monitor task health
  during deployment

---

### Handling Stacks in ROLLBACK_COMPLETE State

When a CloudFormation stack fails during creation it enters `ROLLBACK_COMPLETE`.
A stack in this state **cannot be updated or redeployed** — it must be deleted
first.

#### Quick fix — use the cleanup command

```bash
# Interactively delete all failed stacks
./deploy.sh cleanup

# Then re-deploy
./deploy.sh deploy
```

#### Manual fix via AWS CLI

```bash
# 1. Check which stacks are in a failed state
aws cloudformation list-stacks \
  --stack-status-filter ROLLBACK_COMPLETE CREATE_FAILED \
  --query 'StackSummaries[*].[StackName,StackStatus]' \
  --output table

# 2. Delete the failed stack (start with the highest-level stack first)
aws cloudformation delete-stack --stack-name decoration-preview-api

# 3. Wait for deletion to complete
aws cloudformation wait stack-delete-complete --stack-name decoration-preview-api

# 4. Re-deploy
./deploy.sh deploy
```

#### Deletion order for dependent stacks

If multiple stacks are in `ROLLBACK_COMPLETE`, delete them in **reverse
dependency order** (top-level first):

1. `decoration-preview-monitoring`
2. `decoration-preview-api`
3. `decoration-preview-compute`
4. `decoration-preview-storage`
5. `decoration-preview-network`

> **Tip:** The `./deploy.sh cleanup` command already processes stacks in this
> order and prompts you before deleting each one.

### ECS Service Deployment Hangs

During `decoration-preview-compute` stack deployment, the ECS service
(`ApiService/Service`) may appear stuck at `CREATE_IN_PROGRESS` for an
extended period. This happens when ECS tasks fail to reach a healthy state.

#### Quick diagnosis

Open a **second terminal** and run:

```bash
# Real-time ECS service and task status
./deploy.sh ecs-status
```

This shows running/pending/stopped tasks, deployment rollout state, and stop
reasons for failed tasks.

#### Common causes and solutions

| Cause | Symptoms | Fix |
|-------|----------|-----|
| **Docker image build failure** | No tasks start; CDK output shows Docker build errors | Fix `backend/Dockerfile` or `requirements.txt` and redeploy |
| **Container crashes on startup** | Tasks start then immediately stop (`Essential container exited`) | Check logs: `aws logs tail /ecs/decoration-preview/api --follow` |
| **Health check fails** | Tasks run but are marked `UNHEALTHY` | Verify `/health` endpoint works locally: `docker build -t test ../backend && docker run -p 8000:8000 test` then `curl localhost:8000/health` |
| **IAM permission issues** | Tasks stop with `CannotPullContainerError` | Ensure ECS task execution role has ECR pull permissions (CDK handles this, but check if customized) |
| **Subnet/NAT issues** | Tasks stay in `PROVISIONING` | Verify NAT Gateway is healthy and private subnets have routes to it |
| **Resource limits** | Tasks killed with `OutOfMemoryError` | Increase `memory_limit_mib` in `compute_stack.py` |

#### Step-by-step debugging

```bash
# 1. Check ECS service events (shows why tasks are failing)
aws ecs describe-services \
  --cluster decoration-preview-cluster \
  --services decoration-preview-api \
  --query 'services[0].events[0:10]' \
  --output table --region eu-central-1

# 2. View container logs for the API service
aws logs tail /ecs/decoration-preview/api --follow --region eu-central-1

# 3. List stopped (failed) tasks and see their stop reasons
aws ecs list-tasks --cluster decoration-preview-cluster \
  --desired-status STOPPED --output text --region eu-central-1 | \
  xargs -r aws ecs describe-tasks --cluster decoration-preview-cluster \
  --query 'tasks[*].{Task:taskArn,StopCode:stopCode,Reason:stoppedReason}' \
  --output table --tasks --region eu-central-1

# 4. Check ECS task definition is using the right image
aws ecs describe-task-definition --task-definition decoration-preview-api \
  --query 'taskDefinition.containerDefinitions[0].image' --output text \
  --region eu-central-1

# 5. ECS Exec into a running task for live debugging
aws ecs execute-command \
  --cluster decoration-preview-cluster \
  --task <TASK_ARN> \
  --container ApiContainer \
  --interactive \
  --command '/bin/sh' \
  --region eu-central-1
```

#### Circuit breaker protection

The ECS services are configured with a **deployment circuit breaker** that
automatically detects repeated task failures and rolls back the deployment.
This prevents indefinite hangs — if tasks keep crashing, the deployment will
fail and CloudFormation will report an error instead of waiting forever.

If you see `ROLLBACK` in the circuit breaker status, the tasks are failing
consistently. Check the container logs to find the root cause before
redeploying.
