# ADR 001: Python with FastAPI for API Service

## Status

Accepted

## Context

We need to choose a programming language and web framework for the Decoration Preview Service API. The service must:

- Handle file uploads and validation
- Manage asynchronous rendering jobs
- Provide REST API with OpenAPI documentation
- Integrate with AWS services (S3, DynamoDB, SQS)
- Be maintainable by the creative tooling team

Options considered:
1. **Python + FastAPI**
2. **Python + Flask**
3. **C# + ASP.NET Core**
4. **Node.js + Express**

## Decision

We chose **Python with FastAPI**.

## Rationale

1. **Async-native**: FastAPI is built on Starlette/ASGI, providing native async support crucial for I/O-bound operations (S3, DynamoDB, SQS).

2. **Automatic OpenAPI documentation**: FastAPI generates interactive Swagger UI and ReDoc from Pydantic models, reducing documentation burden.

3. **Type safety**: Pydantic models provide runtime validation and clear API contracts.

4. **Image processing ecosystem**: Python's Pillow library (and future Blender scripting) are best-in-class for image/3D processing.

5. **AWS SDK maturity**: boto3 is the most mature and well-documented AWS SDK.

6. **Team expertise**: The creative tooling team has strong Python experience.

7. **Performance**: FastAPI is one of the fastest Python web frameworks, benchmarking near Node.js and Go for API workloads.

## Consequences

- **Positive**: Fast development, excellent documentation, strong typing
- **Positive**: Same language for API and rendering worker
- **Negative**: Python's GIL limits CPU-bound parallelism (mitigated by ECS horizontal scaling)
- **Negative**: Startup time slightly slower than compiled languages (mitigated by container keep-alive)
