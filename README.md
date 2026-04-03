# Decoration Preview Service

> A cloud-native API service that accepts 2D artwork files and element identifiers, returning rendered 3D preview images showing how decorations will appear on physical toy elements.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green.svg)](https://fastapi.tiangolo.com/)
[![AWS CDK](https://img.shields.io/badge/AWS_CDK-2.177-orange.svg)](https://aws.amazon.com/cdk/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Overview

Graphic designers creating decorations for toy elements currently wait hours for physical samples or manual renderings. The **Decoration Preview Service** reduces this feedback loop to **minutes** by providing an API that:

1. **Accepts** 2D artwork files (PNG, JPEG, SVG, TIFF, PSD)
2. **Validates** file integrity, size, and format
3. **Renders** a 3D preview of the decoration applied to the specified element
4. **Returns** the preview image via a secure, pre-signed URL

### Key Features

- **Asynchronous rendering** — Submit and poll pattern with webhook support
- **Multi-format output** — PNG, JPEG, and WebP output formats
- **Secure by design** — API key auth, KMS encryption, VPC isolation
- **Auto-scaling** — Handles 100 to 10,000+ renders/day
- **Observable** — CloudWatch dashboards, structured logging, health checks
- **Infrastructure as Code** — Full AWS CDK definitions

---

## Architecture Summary

```
Designer → CloudFront → ALB → FastAPI API → SQS Queue → ECS Render Workers
                                    ↕                          ↕
                              DynamoDB (jobs)        S3 (artwork/renders)
```

The service follows an **event-driven, asynchronous architecture**:

| Layer | Technology | Purpose |
|-------|-----------|---------|
| CDN / Edge | CloudFront + WAF | Caching, DDoS protection, TLS |
| API Gateway | ALB + FastAPI | Request routing, validation, auth |
| Job Queue | SQS + DLQ | Async job dispatching, retry handling |
| Compute | ECS Fargate | Auto-scaling API + render workers |
| Storage | S3 (KMS encrypted) | Artwork, elements, rendered previews |
| Database | DynamoDB | Job metadata and status tracking |
| Monitoring | CloudWatch + SNS | Dashboards, alarms, notifications |

See [Architecture Documentation](docs/architecture.md) for detailed design.

---

## Project Structure

```
decoration-preview-service/
├── backend/                    # FastAPI application
│   ├── app/
│   │   ├── api/               # API route definitions
│   │   │   └── routes.py      # All REST endpoints
│   │   ├── core/              # Configuration, security, exceptions
│   │   │   ├── config.py      # Environment-based settings
│   │   │   ├── security.py    # API key authentication
│   │   │   ├── exceptions.py  # Custom exception handlers
│   │   │   └── logging.py     # Structured logging setup
│   │   ├── models/            # Pydantic schemas
│   │   │   └── schemas.py     # Request/response models
│   │   ├── services/          # Business logic
│   │   │   ├── job_store.py   # In-memory job store (DynamoDB sim)
│   │   │   ├── element_catalog.py  # Element catalog service
│   │   │   └── file_validator.py   # Upload validation
│   │   ├── workers/           # Background processing
│   │   │   └── renderer.py    # Stubbed rendering worker
│   │   └── main.py            # FastAPI app factory
│   └── run.py                 # Development server entry point
├── infrastructure/             # AWS CDK stacks
│   ├── stacks/
│   │   ├── network_stack.py   # VPC, subnets, security groups
│   │   ├── storage_stack.py   # S3, DynamoDB, SQS
│   │   ├── compute_stack.py   # ECS Fargate cluster and tasks
│   │   ├── api_stack.py       # ALB, CloudFront, WAF
│   │   └── monitoring_stack.py # CloudWatch, SNS alerts
│   ├── app.py                 # CDK app entry point
│   └── cdk.json               # CDK configuration
├── docs/                       # Documentation
│   ├── architecture.md        # Detailed architecture
│   ├── security.md            # Security considerations
│   ├── scalability.md         # Scalability strategy
│   ├── design-principles.md   # Design principles
│   ├── adr/                   # Architecture Decision Records
│   └── diagrams/              # C4 diagrams (source + PNG)
├── tests/                      # Test suite
│   ├── conftest.py            # Shared fixtures
│   └── unit/                  # Unit tests
├── requirements.txt           # Production dependencies
├── requirements-dev.txt       # Development dependencies
├── pytest.ini                 # Pytest configuration
├── pyproject.toml             # Project metadata
└── README.md                  # This file
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- pip

### Installation

```bash
# Clone the repository
git clone https://github.com/patman77/decoration-preview-service.git
cd decoration-preview-service

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### Running the API

```bash
# Start the development server
uvicorn backend.app.main:app --reload --port 8000

# Or use the run script
python -m backend.run
```

The API will be available at `http://localhost:8000` with:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json
- **Health Check**: http://localhost:8000/health

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=backend --cov-report=html --cov-report=term-missing

# Run only unit tests
pytest tests/unit/ -v
```

---

## API Usage Examples

### Health Check

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "environment": "development"
}
```

### Submit a Render Job

```bash
curl -X POST http://localhost:8000/api/v1/render \
  -H "X-API-Key: dev-api-key-change-in-production" \
  -F "artwork_file=@artwork.png" \
  -F "element_id=elem-minifig-torso-001" \
  -F "output_format=png" \
  -F "resolution_width=1024" \
  -F "resolution_height=1024"
```

```json
{
  "job_id": "job-a1b2c3d4e5f6",
  "status": "pending",
  "element_id": "elem-minifig-torso-001",
  "created_at": "2026-04-03T10:30:00Z",
  "estimated_duration_seconds": 30,
  "message": "Render job queued successfully. Use the status endpoint to track progress."
}
```

### Check Job Status

```bash
curl http://localhost:8000/api/v1/render/job-a1b2c3d4e5f6/status \
  -H "X-API-Key: dev-api-key-change-in-production"
```

```json
{
  "job_id": "job-a1b2c3d4e5f6",
  "status": "completed",
  "element_id": "elem-minifig-torso-001",
  "progress_percent": 100,
  "created_at": "2026-04-03T10:30:00Z",
  "updated_at": "2026-04-03T10:30:32Z"
}
```

### Get Preview URL

```bash
curl http://localhost:8000/api/v1/render/job-a1b2c3d4e5f6/preview \
  -H "X-API-Key: dev-api-key-change-in-production"
```

### List Available Elements

```bash
curl http://localhost:8000/api/v1/elements \
  -H "X-API-Key: dev-api-key-change-in-production"
```

### Cancel/Delete a Job

```bash
curl -X DELETE http://localhost:8000/api/v1/render/job-a1b2c3d4e5f6 \
  -H "X-API-Key: dev-api-key-change-in-production"
```

---

## Deployment Guide

### AWS Prerequisites

- AWS CLI configured with appropriate credentials
- AWS CDK CLI installed (`npm install -g aws-cdk`)
- Docker (for building container images)

### Deploy Infrastructure

```bash
cd infrastructure

# Install CDK dependencies
pip install -r ../requirements.txt

# Bootstrap CDK (first time only)
cdk bootstrap aws://ACCOUNT_ID/eu-central-1

# Deploy all stacks
cdk deploy --all

# Deploy specific stack
cdk deploy decoration-preview-storage
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ENVIRONMENT` | Deployment environment | `development` |
| `API_KEY` | API authentication key | `dev-api-key-change-in-production` |
| `AWS_REGION` | AWS region | `eu-central-1` |
| `ARTWORK_BUCKET` | S3 bucket for artwork | `decoration-preview-artwork` |
| `ELEMENTS_BUCKET` | S3 bucket for 3D elements | `decoration-preview-elements` |
| `RENDERS_BUCKET` | S3 bucket for renders | `decoration-preview-renders` |
| `JOBS_TABLE` | DynamoDB table name | `decoration-preview-jobs` |
| `RENDER_QUEUE_URL` | SQS queue URL | — |
| `LOG_LEVEL` | Logging verbosity | `INFO` |

---

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture](docs/architecture.md) | Detailed system architecture and component design |
| [Security](docs/security.md) | Security considerations and threat mitigation |
| [Scalability](docs/scalability.md) | Scaling strategy and bottleneck analysis |
| [Design Principles](docs/design-principles.md) | Applied design principles and patterns |
| [ADR: Python + FastAPI](docs/adr/001-python-fastapi.md) | Why Python and FastAPI were chosen |
| [ADR: Async Rendering](docs/adr/002-async-rendering.md) | Why asynchronous rendering over synchronous |
| [ADR: AWS ECS Fargate](docs/adr/003-ecs-fargate.md) | Container orchestration decision |
| [ADR: S3 + KMS Encryption](docs/adr/004-s3-kms-encryption.md) | Storage encryption strategy |

---

## Technology Stack

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| API Framework | FastAPI | Async support, auto OpenAPI docs, type safety |
| Language | Python 3.11+ | Pillow/Blender ecosystem, team expertise |
| Image Processing | Pillow (stub) / Blender (production) | 2D overlay (stub) / Full 3D rendering |
| Infrastructure | AWS CDK (Python) | Type-safe IaC, same language as app |
| Container Runtime | ECS Fargate | Serverless containers, auto-scaling |
| Job Queue | SQS | Managed, scalable, DLQ support |
| Database | DynamoDB | Serverless, low-latency, auto-scaling |
| Storage | S3 + KMS | Durable, encrypted, lifecycle management |
| CDN | CloudFront | Edge caching, WAF integration |
| Testing | Pytest | Industry standard, excellent plugin ecosystem |

---

## License

MIT License - see [LICENSE](LICENSE) for details.
