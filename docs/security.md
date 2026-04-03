# Security Considerations

## Overview

The Decoration Preview Service handles **confidential, pre-release artwork** that represents significant competitive value. A security breach could result in:

- Premature product reveals
- Loss of competitive advantage
- Intellectual property theft
- Reputational damage

Security is therefore a **primary architectural concern**, not an afterthought.

## Threat Model

### Assets to Protect

| Asset | Classification | Impact of Breach |
|-------|---------------|------------------|
| Pre-release artwork files | Confidential | High — competitive damage |
| 3D element models | Proprietary | High — trade secrets |
| Rendered previews | Confidential | Medium — reveals designs |
| Job metadata | Internal | Low — operational data |
| API keys / credentials | Secret | Critical — full access |

### Threat Categories (STRIDE)

| Threat | Mitigation |
|--------|------------|
| **Spoofing** | API key authentication, future: OIDC/SAML SSO |
| **Tampering** | S3 versioning, HTTPS everywhere, input validation |
| **Repudiation** | CloudTrail audit logging, structured application logs |
| **Information Disclosure** | KMS encryption, VPC isolation, pre-signed URLs |
| **Denial of Service** | WAF rate limiting, CloudFront absorption, auto-scaling |
| **Elevation of Privilege** | Least-privilege IAM, security group isolation |

## Security Controls

### 1. Authentication & Authorization

**Current Implementation:**
- API key authentication via `X-API-Key` header
- Keys validated at the application layer (defense-in-depth)

**Production Enhancement:**
- AWS API Gateway with usage plans and API keys
- OIDC/SAML integration with corporate Identity Provider
- Fine-grained authorization: per-element, per-team access
- JWT tokens with short expiry and refresh rotation

### 2. Encryption

**At Rest:**
- All S3 buckets: AWS KMS Customer Managed Key (CMK)
- DynamoDB: KMS encryption
- SQS: KMS encryption
- EBS volumes: Default encryption
- Key rotation: Enabled (annual)

**In Transit:**
- TLS 1.2+ enforced everywhere
- S3 bucket policy: `aws:SecureTransport` condition
- ALB: HTTP → HTTPS redirect
- CloudFront: Viewer Protocol Policy → HTTPS only
- Internal: VPC endpoints for AWS services

### 3. Network Security

- **VPC Isolation**: Render workers in private subnets (no public IP)
- **Security Groups**: Minimal port exposure
  - API: Port 8000 from ALB only
  - Render workers: No inbound, outbound to S3/SQS via VPC endpoints
- **NAT Gateway**: Controlled outbound access for ECR pulls
- **VPC Flow Logs**: All rejected traffic logged to CloudWatch
- **VPC Endpoints**: S3, DynamoDB, SQS, ECR (avoid public internet)

### 4. Input Validation & File Security

```python
# Multi-layer file validation
1. Extension check (allowlist: .png, .jpg, .jpeg, .svg, .tiff, .psd)
2. File size limit (50 MB)
3. MIME type validation
4. Filename sanitization (path traversal prevention)
5. Empty file rejection
```

**Production Enhancements:**
- ClamAV antivirus scanning on upload (ECS sidecar)
- File magic number validation
- Image dimension limits
- Content-type verification vs. actual content
- Quarantine bucket for suspicious files

### 5. Access Control (IAM)

**Principle of Least Privilege:**

| Role | Permissions |
|------|------------|
| API Task Role | S3 read/write (artwork), S3 read (renders), DynamoDB read/write, SQS send |
| Render Task Role | S3 read (artwork, elements), S3 write (renders), DynamoDB update, SQS consume |
| CI/CD Pipeline | ECR push, ECS deploy, CDK deploy |

### 6. Audit & Logging

- **CloudTrail**: All AWS API calls logged
- **S3 Access Logging**: Who accessed which artwork files
- **Application Logs**: Structured JSON, request correlation IDs
- **VPC Flow Logs**: Network traffic audit
- **Log Retention**: 30 days active, archived to S3/Glacier

### 7. Pre-Signed URLs

Rendered previews are never directly accessible. Access is granted via:

```
1. Client requests preview via API (authenticated)
2. API generates pre-signed S3 URL (1-hour expiry)
3. Client downloads directly from S3 via URL
4. URL expires, preventing further access
```

Benefits:
- No permanent public URLs
- Time-limited access
- No need for client AWS credentials
- CloudFront can cache without exposing S3

### 8. WAF Protection

- **Rate Limiting**: 1,000 requests per IP per 5-minute window
- **AWS Managed Rules**: Common attack patterns (SQLi, XSS, etc.)
- **Size Constraints**: Request body size limits
- **Geo-Blocking**: Restrict to corporate-approved regions (optional)

## Security Best Practices Implemented

1. ✅ All S3 buckets block public access
2. ✅ KMS encryption with automatic key rotation
3. ✅ VPC isolation for compute workloads
4. ✅ Input validation and sanitization
5. ✅ Structured logging for audit trail
6. ✅ Health check endpoints (no sensitive data)
7. ✅ Error responses hide internal details
8. ✅ Dependencies pinned to specific versions
9. ✅ Environment-based configuration (no hardcoded secrets)
10. ✅ CORS restricted to known origins

## Compliance Considerations

- **GDPR**: No PII stored; artwork is corporate IP, not personal data
- **SOC 2**: Audit logging, encryption, access controls meet requirements
- **ISO 27001**: Information security management controls addressed

## Incident Response Plan

1. **Detection**: CloudWatch alarms, WAF alerts, anomalous access patterns
2. **Containment**: Revoke API keys, disable affected services
3. **Eradication**: Patch vulnerabilities, rotate credentials
4. **Recovery**: Restore from versioned S3 backups, redeploy services
5. **Lessons Learned**: Post-incident review, update security controls
