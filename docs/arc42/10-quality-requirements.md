# 10. Quality Requirements

## Quality tree

- **Resilience**
  - Gateway restart drops no session — verified restart-under-load
    ([SES-12](../../openspec/specs/sessions/spec.md), [DEP-7](../../openspec/specs/deployment/spec.md))
  - Explicit degradation under Redis/Postgres outage (SES-14, EP-21) — no silent failure
    ([OPS-11](../../openspec/specs/operations/spec.md))
- **Scalability**
  - Any replica serves any session; no sticky sessions (ARC-9, SES-2)
  - Rate limits and caches correct across replicas (EP-17, [SES-19](../../openspec/specs/sessions/spec.md) ≤ 2
    s propagation)
- **Performance**
  - Gateway overhead ≤ 50 ms p95 added latency on tool calls, measured each integration run
    ([OPS-13](../../openspec/specs/operations/spec.md))
  - Long-running calls usable: progress-aware timeouts, cancellation
    ([PROT-1..3](../../openspec/specs/protocol/spec.md))
- **Security**
  - Tokens endpoint-bound + consented ([AUTH-10/11](../../openspec/specs/auth/spec.md)); SSRF egress policy
    ([SEC-1/2](../../openspec/specs/security/spec.md)); secrets never logged/returned (SEC-10, testable)
- **Integrability**
  - Registrar converges by PUTting desired state ([MGMT-4](../../openspec/specs/management/spec.md)); metering hook
    exactly-once per invocation with crash reconciliation ([PROT-26](../../openspec/specs/protocol/spec.md),
    [OPS-7](../../openspec/specs/operations/spec.md))
- **Maintainability**
  - Latest-stable policy (ARC-1); spec-first change process; generated frontend types (ARC-4); hermetic test gate
    (ARC-14)

## Concrete scenarios

| Scenario | Expected |
|---|---|
| `docker compose restart gateway` during an active claude.ai chat with tool use | Next tool call succeeds without the connector re-authorizing or re-initializing |
| Two replicas behind round-robin, one session, alternating requests | All succeed (SES-12) |
| Upstream container redeployed mid-session | One transparent retry re-binds; call succeeds or surfaces a clear retryable error (SES-7) |
| API key deactivated in UI | Rejected on all replicas within 2 s (SES-19) |
| Tool call runs 130 s with progress events | Completes: progress relayed, timeout reset per event, cancel works (PROT-1/2/3) |
| Token minted for endpoint A replayed at endpoint B | 401 with the endpoint's `WWW-Authenticate` challenge carrying `error="invalid_token"` (EP-3a) |
