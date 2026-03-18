# ADR-0001: API-First Design — Feature Registry API as Contract, SDK as Thin Wrapper

**Status:** Accepted
**Date:** 2026-03-12
**Deciders:** Gen AI Platform team

---

## Context

The ADR "Option 2: Direct Bedrock Access via Inference Profiles (SDK-Enforced)" defines the strategic direction for Bedrock access governance:

> "SDK encapsulates governance, usage attribution, and policy logic in a reusable, versioned library"

This decision record analyzes how the Intelligent Feature Registry (formerly Intelligent Gateway) applies Option 2 while avoiding a critical historical mistake made by the AWS Platform team.

### Historical mistake — AWS Platform SDK antipattern

The AWS Platform team embedded infrastructure constraints (S3 bucket prefixing, KMS key selection, multitenancy enforcement) directly into a Python SDK. Consequences:

- **Language lock-in**: Python SDK became the only supported path, making TypeScript adoption politically contentious
- **SDK as enforcement**: Without the SDK, multitenancy constraints broke — the SDK was the contract, not a service
- **Portability cost**: Every new language required a full SDK port before teams could use the platform

The root cause: **centralized services should have handled partitioning/encryption/tenancy via API, not required an SDK to enforce them.**

### Current system

The Intelligent Feature Registry is a centralized API service that manages Bedrock inference profile lifecycle:

- `POST /profiles` — Register a profile (triggers async provisioning via DynamoDB Stream)
- `GET /profiles` — Look up an active profile's inference profile ARN
- `DELETE /profiles` — Delete a profile and its Bedrock inference profile

All business logic (quota enforcement, duplicate prevention, model validation, provisioning) is server-side. After obtaining an inference profile ARN, teams call Bedrock directly via `boto3.converse(modelId=arn)` — the registry does not proxy Bedrock calls.

---

## Decision

### 1. Feature Registry API is the contract

The API owns all logic: profile lifecycle, quota enforcement, duplicate prevention, model validation, usage tracking (future), and policy enforcement (future). The API is language-agnostic — any HTTP client can use it.

### 2. SDK is a thin wrapper — no business logic

Any SDK (Python, TypeScript, or otherwise) is a convenience layer only:

- SigV4 request signing
- HTTP GET to resolve `team + featureName → inferenceProfileArn`
- Optional response caching

The SDK contains **zero business logic**. It is a wrapper around a single HTTP call. Building an equivalent in any language takes ~10 lines of code.

### 3. SDK is not required

The system works without any SDK:

```bash
# curl — no SDK needed
curl -s "$REGISTRY_URL/profiles?team=marketing&featureName=chatbot&modelId=anthropic.claude-sonnet-4-20250514" | jq '.inferenceProfileArn'
```

```python
# Python — no SDK needed
resp = requests.get(f"{REGISTRY_URL}/profiles", params={
    "team": "marketing", "featureName": "chatbot", "modelId": "anthropic.claude-sonnet-4-20250514"
})
arn = resp.json()["inferenceProfileArn"]
bedrock.converse(modelId=arn, ...)
```

```typescript
// TypeScript — no SDK needed
const res = await fetch(`${REGISTRY_URL}/profiles?team=marketing&featureName=chatbot&modelId=anthropic.claude-sonnet-4-20250514`);
const { inferenceProfileArn } = await res.json();
```

### 4. Naming: Intelligent Gateway → Intelligent Feature Registry

The system is a registry (register/lookup/delete profiles), not a gateway (proxy). It does not proxy Bedrock calls. "Feature Registry" accurately reflects its role as a team-feature-based inference profile registry.

---

## ADR Option 2 compliance

The ADR states: *"SDK encapsulates governance, usage attribution, and policy logic."*

This is satisfied — but the logic owner is the API, not the SDK:

| Requirement | How it's satisfied | Enforcement mechanism |
|-------------|-------------------|----------------------|
| **Governance** | Feature Registry issues inference profile ARNs; Orca SAST blocks raw model ID usage in code | Orca SAST (CI/CD) — works regardless of SDK usage |
| **Usage Attribution** | Inference profiles carry team/feature tags at creation time (`provision_profile/handler.py`). AWS Cost Explorer tracks usage by tag | Inference profile tags — automatic, no SDK code needed |
| **Policy Logic** | Feature Registry enforces quota, duplicate prevention, model validation at registration time | Server-side API — consistent across all clients |

Key insight: **SDK wrapping does not add enforcement.** If a team bypasses the SDK, Orca SAST still catches raw Bedrock calls. The SDK is a convenience layer, not a security boundary.

---

## Consequences

### Positive

- **No language lock-in**: API is the contract. TypeScript, Python, Go teams all use the same HTTP endpoint
- **No SDK porting burden**: New language support = API documentation, not SDK development
- **Avoids historical mistake**: Business logic stays server-side, not in client SDKs
- **Framework compatible**: Strands, LangChain, raw boto3 — all work with inference profile ARNs
- **Future extensible**: Usage tracking (`POST /usage`), policy enforcement (`GET /policies`) are API additions, not SDK changes

### Negative / trade-offs

- **No automatic enforcement via SDK**: Teams could theoretically bypass the registry. Mitigation: Orca SAST detects raw `modelId` usage in CI/CD
- **Extra network hop**: Profile ARN resolution requires an API call (mitigated by caching)
- **Less "magical" DX**: Teams must know the registry URL and call it explicitly (or use the thin SDK convenience method)

### Neutral

- **agent-sdk integration**: `aws-agent-sdk-python` will add optional `feature_registry_url`, `team`, `feature_name` parameters to `BaseStrandsAgent`. This is a convenience path, not the only path

---

## Historical comparison

| Past mistake (AWS Platform) | Current design (Feature Registry) | Same mistake? |
|-----------------------------|-----------------------------------|---------------|
| S3 bucket prefix decided in SDK | Profile provisioning handled server-side | No |
| KMS key selected/enforced by SDK | Future policy delivered via API response | No |
| SDK required for multitenancy | `curl` can do everything the SDK does | No |
| Python SDK → Python lock-in | API is the contract → language agnostic | No |
| New language = SDK port required | `GET /profiles` → 10 lines in any language | No |

---

## Inference profile strategy: internal vs external

### Internal (current phase)

Inference profiles are shared at the **team + feature + model** level. Tenant isolation is unnecessary — all internal teams belong to the same organization.

- DDB key: `PK=PROFILE`, `SK=TEAM#{team}#FEATURE#{feature}#MODEL#{model_id}`
- One inference profile per team+feature+model combination
- AWS inference profile limit: 1,000 per account per region. Shared profiles keep usage well within this limit
- Authentication: valid nCino tenant credential required to call API. Trust-based access within the organization
- Cost monitoring: CloudWatch Alarms auto-created per inference profile at provisioning time

### External (future — when platform is sold to other banks)

Account-level isolation replaces tenant-level isolation:

- Each customer gets a dedicated AWS account (Option 3 — multi-account strategy)
- Feature Registry creates inference profiles in the customer's account via cross-account role assume
- Account boundary = security boundary. No application-level tenant isolation needed
- Billing: AWS Organizations consolidated billing + inference profile tags for per-customer cost tracking

Key insight: **the transition from internal to external does not require DDB schema changes.** The API contract (team + feature + model) stays the same. Only the provisioning backend changes (which account to create the profile in).

---

## References

- ADR Option 2: Direct Bedrock Access via Inference Profiles (SDK-Enforced)
- AWS Platform SDK postmortem (internal)
- Orca Security SAST — `shiftleft-sast-action` for detecting raw Bedrock model ID usage
