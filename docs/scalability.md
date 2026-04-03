# Scalability Strategy

## Current Design Targets

| Metric | Baseline | Target | Peak |
|--------|----------|--------|------|
| Renders per day | 100 | 1,000 | 10,000+ |
| Concurrent renders | 5 | 50 | 200+ |
| API response time (p99) | < 200ms | < 500ms | < 1s |
| Render completion time | < 60s | < 120s | < 300s |
| File upload size | 50 MB max | 50 MB max | 100 MB max |

## Scaling Strategy by Component

### 1. API Service (Horizontal Scaling)

**Current**: 2-10 ECS Fargate tasks
**Scaling trigger**: CPU utilization > 70%
**Scaling speed**: New task in ~60 seconds

```
Baseline:  2 tasks  × 100 req/s each = 200 req/s
Peak:      10 tasks × 100 req/s each = 1,000 req/s
```

The API service is stateless — scaling horizontally is trivial. The ALB distributes requests evenly across tasks.

### 2. Render Workers (Queue-Driven Scaling)

**Current**: 0-50 ECS Fargate tasks
**Scaling trigger**: SQS queue depth + CPU utilization
**Scale-to-zero**: When queue is empty for 10 minutes

```
Baseline:  1-5 workers   = ~100 renders/hour
Normal:    10-20 workers  = ~500 renders/hour
Peak:      50 workers     = ~2,500 renders/hour
Burst:     50+ with spot  = ~5,000+ renders/hour
```

Key design: Workers pull from SQS, so we can scale independently of API traffic.

### 3. Storage (Managed Scaling)

| Service | Scaling Model | Capacity |
|---------|--------------|----------|
| S3 | Unlimited | No limits |
| DynamoDB | On-demand (PAY_PER_REQUEST) | Auto-scales to workload |
| SQS | Unlimited | 120,000 in-flight messages |

All storage services are fully managed and scale automatically.

### 4. CDN (Edge Scaling)

CloudFront absorbs read traffic for rendered previews:
- **Cache hit**: Served from edge (< 50ms latency)
- **Cache miss**: Route to origin, cache for 1 hour
- **Effect**: Reduces origin load by 60-80% for popular previews

## Bottleneck Analysis

### Potential Bottlenecks

| Bottleneck | Impact | Mitigation |
|-----------|--------|------------|
| Render worker capacity | Queued jobs wait longer | Auto-scaling, Spot instances |
| S3 upload throughput | Slow artwork uploads | Multi-part upload, Transfer Acceleration |
| DynamoDB hot partition | Throttled status queries | On-demand billing, query optimization |
| NAT Gateway bandwidth | Worker S3 downloads slow | VPC endpoints for S3 |
| KMS API rate limit | Encryption/decryption throttled | KMS key caching, request batching |

### Mitigation Strategies

1. **Pre-warming**: Maintain minimum worker capacity during business hours
2. **Batching**: Group small renders into batch jobs
3. **Caching**: Redis (ElastiCache) for element catalog and job status
4. **Connection pooling**: Reuse boto3 connections across requests
5. **Async I/O**: FastAPI's async nature maximizes API throughput

## Cost Optimization

### Fargate Pricing Strategy

```
API Service:     On-Demand (always-on, predictable)
Render Workers:  Fargate Spot (70% discount, tolerant of interruption)
```

### S3 Lifecycle Optimization

```
Day 0-30:   Standard (frequent access)
Day 30-90:  Intelligent-Tiering (auto-optimized)
Day 90+:    Glacier (archive, rare access)
Day 365:    Delete (expired previews)
```

### DynamoDB Cost Control

- **On-demand billing**: No over-provisioning
- **TTL**: Automatic deletion of old job records
- **GSI**: Only create indexes that are actively queried

## Load Testing Strategy

```bash
# Recommended load testing approach
1. Baseline: 10 concurrent users, 5 minutes
2. Stress: Ramp to 100 concurrent users over 10 minutes
3. Spike: Jump to 500 concurrent users for 2 minutes
4. Endurance: 50 concurrent users for 1 hour
```

Tools: Locust (Python), k6, or AWS-native load testing.

## Scaling Roadmap

### Phase 1: Current (100 renders/day)
- 2 API tasks, 1-5 render workers
- Single region (eu-central-1)
- Estimated cost: ~$200/month

### Phase 2: Growth (1,000 renders/day)
- 4 API tasks, 10-20 render workers
- Redis caching for hot data
- Fargate Spot for workers
- Estimated cost: ~$800/month

### Phase 3: Scale (10,000+ renders/day)
- 8-10 API tasks, 30-50+ render workers
- GPU instances for rendering
- Multi-region with Global Accelerator
- Batch processing pipeline
- Estimated cost: ~$3,000-5,000/month
