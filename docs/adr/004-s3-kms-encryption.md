# ADR 004: S3 with KMS Encryption for Asset Storage

## Status

Accepted

## Context

The service stores confidential pre-release artwork files that require strong protection. We need to decide on:

1. Storage technology
2. Encryption strategy
3. Access control model

## Decision

We chose **AWS S3 with KMS Customer Managed Keys (CMK)** for all asset storage.

## Rationale

### Why S3

1. **Durability**: 99.999999999% (11 nines) durability
2. **Scalability**: Unlimited storage, no capacity planning
3. **Lifecycle management**: Automatic tiering (Standard → IA → Glacier)
4. **Versioning**: Full audit trail of all file changes
5. **Pre-signed URLs**: Secure, time-limited access without permanent public URLs
6. **CloudFront integration**: Native CDN origin for cached preview delivery

### Why KMS CMK (not SSE-S3)

1. **Key control**: We own and manage the encryption key lifecycle
2. **Audit trail**: CloudTrail logs every key usage (who decrypted what, when)
3. **Key rotation**: Automatic annual rotation
4. **Cross-service**: Same key encrypts S3, DynamoDB, and SQS
5. **Revocation**: Key can be disabled to immediately deny all access
6. **Compliance**: Meets SOC 2 and ISO 27001 requirements for encryption management

### Access Model

- **Block all public access** on every bucket
- **Bucket policies** enforce SSL-only access
- **IAM roles** grant minimal required permissions
- **Pre-signed URLs** for time-limited download access
- **VPC endpoints** for private network access from ECS

## Consequences

- **Positive**: Best-in-class durability and security
- **Positive**: Full audit trail for compliance
- **Positive**: Native integration with all AWS services
- **Negative**: KMS API call cost (~$0.03 per 10,000 requests)
- **Negative**: KMS rate limits (5,500 requests/second per key) — mitigated by data key caching
- **Negative**: Vendor lock-in to AWS — acceptable given AWS-first strategy
