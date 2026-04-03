# ADR 002: Asynchronous Rendering via SQS

## Status

Accepted

## Context

3D rendering is CPU/GPU-intensive and can take 10 seconds to 5 minutes depending on complexity. We need to decide between:

1. **Synchronous rendering** — API blocks until render completes
2. **Asynchronous rendering** — API returns immediately, client polls for result

## Decision

We chose **asynchronous rendering** with SQS as the message broker.

## Rationale

1. **API responsiveness**: Synchronous rendering would hold HTTP connections for minutes, degrading user experience and wasting API capacity.

2. **Independent scaling**: Render workers scale based on queue depth, not API traffic. A burst of submissions doesn't overwhelm the renderer.

3. **Fault tolerance**: If a render fails, SQS automatically retries. After 3 failures, the message moves to DLQ for investigation.

4. **Cost efficiency**: Workers can scale to zero when idle. No renders = no compute cost.

5. **Backpressure**: SQS naturally buffers during load spikes. The queue absorbs bursts that would overwhelm synchronous processing.

## Alternatives Considered

- **AWS Step Functions**: More complex orchestration than needed for single-step rendering. Would add latency and cost.
- **Lambda**: Render times exceed Lambda's 15-minute limit for complex models. Memory/CPU constraints too limiting.
- **Redis Queue (Celery)**: Additional operational burden managing Redis cluster.

## Consequences

- **Positive**: API always responds in < 1 second
- **Positive**: Natural retry and dead-letter handling
- **Positive**: Zero-cost when idle
- **Negative**: Requires polling or webhook for completion notification
- **Negative**: Adds ~1-2 seconds latency for queue transit
