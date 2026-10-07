# 10. Quality Requirements

## Quality tree

- **Resilience**
  - Gateway restart drops no session — verified restart-under-load ([SES-12](../../spec/30-session-management.md),
    [DEP-7](../../spec/71-deployment.md))
  - Explicit degradation under Redis/Postgres outage (SES-14, RATE-6) — no silent failure
    ([OBS-4](../../spec/51-observability.md))
- **Scalability**
  - Any replica serves any session; no sticky sessions (ARC-9, SES-2)
  - Rate limits and caches correct across replicas (RATE-2, [STP-3](../../spec/33-state-propagation.md) ≤ 2 s
    propagation)
- **Performance**
  - Gateway overhead ≤ 50 ms p95 added latency on tool calls, measured each integration run
    ([OBS-6](../../spec/51-observability.md))
  - Long-running calls usable: progress-aware timeouts, cancellation
    ([PROT-1..3](../../spec/32-protocol-passthrough.md))
- **Security**
  - Tokens endpoint-bound + consented ([OAS-10/11](../../spec/20-oauth-server.md)); SSRF egress policy
    ([SEC-1/2](../../spec/70-security.md)); secrets never logged/returned (SEC-10, testable)
- **Integrability**
  - Registrar converges by PUTting desired state ([API-4](../../spec/40-management-api.md)); metering hook exactly-once
    per invocation with crash reconciliation ([MID-3](../../spec/31-middleware.md), [AUD-7](../../spec/50-audit-log.md))
- **Maintainability**
  - Latest-stable policy (ARC-1); spec-first change process; generated frontend types (ARC-4); hermetic test gate
    (ARC-14)

## Concrete scenarios

| Scenario | Expected |
|---|---|
| `docker compose restart gateway` during an active claude.ai chat with tool use | Next tool call succeeds without the connector re-authorizing or re-initializing |
| Two replicas behind round-robin, one session, alternating requests | All succeed (SES-12) |
| Upstream container redeployed mid-session | One transparent retry re-binds; call succeeds or surfaces a clear retryable error (SES-7) |
| API key deactivated in UI | Rejected on all replicas within 2 s (STP-3) |
| Tool call runs 130 s with progress events | Completes: progress relayed, timeout reset per event, cancel works (PROT-1/2/3) |
| Token minted for endpoint A replayed at endpoint B | 401 invalid_token (EP-3a) |
