# Design Principles

The following design principles guide the architecture and implementation of the Decoration Preview Service.

## 1. Separation of Concerns

**Principle**: Each component has a single, well-defined responsibility.

**Application**:
- **API Service** handles request routing, validation, and authentication
- **Job Store** manages persistence (swappable: in-memory → DynamoDB)
- **File Validator** handles upload validation independently
- **Render Worker** focuses solely on image processing
- **Infrastructure stacks** are separated by domain (network, storage, compute)

**Benefit**: Changes to rendering logic don't affect API routing. Storage changes don't impact compute configuration.

## 2. Asynchronous by Default

**Principle**: Long-running operations are always asynchronous.

**Application**:
- Render jobs are submitted and return immediately (HTTP 202 Accepted)
- SQS queue decouples submission from processing
- Workers process independently at their own pace
- Clients poll for status or receive webhook notifications

**Benefit**: The API remains responsive regardless of render queue depth. A 5-minute render doesn't block a 200ms API call.

## 3. Fail-Fast Validation

**Principle**: Validate early, fail fast, provide clear error messages.

**Application**:
- File type, size, and format validated before queuing
- Element ID validated against catalog before creating job
- Request schema validated by Pydantic before handler execution
- Invalid requests rejected at the API layer, never reaching the queue

**Benefit**: Invalid requests cost nothing in compute. Users get immediate feedback instead of waiting for a render to fail.

## 4. Idempotency

**Principle**: Operations can be safely retried without side effects.

**Application**:
- Unique `job_id` prevents duplicate job creation
- SQS message visibility timeout prevents duplicate processing
- S3 uploads use deterministic keys (overwrite is safe)
- Status updates are last-writer-wins (no conflicting states)

**Benefit**: Network failures, retries, and duplicate messages don't corrupt state.

## 5. Stateless Services

**Principle**: Service instances hold no local state.

**Application**:
- API tasks share no in-memory state (DynamoDB is source of truth)
- Render workers are interchangeable (any worker can process any job)
- All state lives in managed services (S3, DynamoDB, SQS)
- Horizontal scaling requires no data migration

**Benefit**: Auto-scaling, rolling deployments, and failure recovery are trivial.

> **Note**: The in-memory job store in this demo is a development convenience. In production, DynamoDB provides the stateless persistence layer.

## 6. Defense in Depth

**Principle**: Multiple security layers, each independently effective.

**Application**:
- WAF at CloudFront edge (Layer 1)
- API key validation at ALB/API Gateway (Layer 2)
- Application-level authentication (Layer 3)
- VPC isolation for compute (Layer 4)
- S3 encryption with KMS (Layer 5)
- IAM least-privilege roles (Layer 6)

**Benefit**: Compromise of any single layer doesn't grant access to assets.

## 7. Observability

**Principle**: Every operation is measurable and traceable.

**Application**:
- Structured logging with correlation IDs
- CloudWatch metrics for all services
- Health check endpoints for liveness/readiness
- CloudWatch alarms for critical thresholds
- SNS notifications for operational alerts

**Benefit**: Problems are detected before users report them. Root cause analysis is data-driven.

## 8. Infrastructure as Code

**Principle**: All infrastructure is defined, versioned, and deployable from code.

**Application**:
- AWS CDK defines all resources (5 stacks, ~500 lines)
- Same language as application (Python)
- Git-versioned, code-reviewed changes
- Reproducible deployments across environments

**Benefit**: Infrastructure changes are reviewed, tested, and auditable. No configuration drift.

## 9. Event-Driven Architecture

**Principle**: Components communicate through events, not direct calls.

**Application**:
- API → SQS → Worker (not API → Worker directly)
- Job status changes trigger events (future: EventBridge)
- Webhook notifications for external consumers
- DLQ captures failed events for analysis

**Benefit**: Components are loosely coupled. Adding a new consumer (e.g., analytics) requires no changes to the producer.

## 10. Design for Failure

**Principle**: Assume components will fail; design for graceful recovery.

**Application**:
- SQS DLQ captures messages that fail 3x
- ECS health checks restart unhealthy tasks
- ALB routes away from failing instances
- S3 provides 99.999999999% durability
- DynamoDB provides automatic failover
- Render timeout prevents stuck jobs

**Benefit**: The system self-heals from most failures without human intervention.

## Applied Patterns

| Pattern | Where Applied |
|---------|---------------|
| **Factory Pattern** | `create_app()` for testable FastAPI creation |
| **Repository Pattern** | `InMemoryJobStore` (swappable with DynamoDB) |
| **Strategy Pattern** | Output format selection (PNG/JPEG/WebP) |
| **Observer Pattern** | Background tasks, webhook notifications |
| **Circuit Breaker** | Future: Render worker → S3 communication |
| **Saga Pattern** | Future: Multi-step render with compensation |
| **CQRS** | Separate read (GET) and write (POST) optimizations |
