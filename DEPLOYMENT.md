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

## Production Checklist

Before going live, ensure:

- [ ] **API Key** — Generated and set to a strong secret (not the dev default)
- [ ] **HTTPS Certificate** — Create an ACM certificate and attach to the ALB HTTPS listener
- [ ] **Custom Domain** — Configure Route 53 or your DNS to point to CloudFront/ALB
- [ ] **Alert Subscription** — Subscribe your team email to the SNS alerts topic
- [ ] **WAF Rules** — Review and customize WAF rules for your traffic patterns
- [ ] **S3 CORS** — Restrict `allowed_origins` in `storage_stack.py` from `*` to your domain(s)
- [ ] **Secrets Manager** — Move `API_KEY` to AWS Secrets Manager for rotation support
- [ ] **Backup Policy** — Verify DynamoDB point-in-time recovery is enabled (it is by default)
- [ ] **Cost Alerts** — Set up AWS Budgets for cost monitoring
- [ ] **Logging** — Verify CloudWatch log groups are receiving logs

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
| ALB health check fails | Verify security groups allow port 8000 from ALB |
| `No space left on device` | Docker disk space; run `docker system prune` |
| CDK synth import errors | Ensure `aws-cdk-lib` is installed: `pip install -r requirements.txt` |
| CloudFront 502 errors | ALB may not have healthy targets yet; wait for ECS tasks to start |
