## MODIFIED Requirements

### Requirement: ARC-11 One gateway container, its routes
One gateway container SHALL serve: `/{endpoint}/mcp` (public MCP, [endpoints](../endpoints/spec.md)),
`/oauth/*` + `/.well-known/*` ([auth](../auth/spec.md)), `/api/v1/*` (management,
[management](../management/spec.md)), `/healthz`, `/readyz` and `/metrics`
([operations](../operations/spec.md)).

#### Scenario: Health probes are served by the gateway
- **WHEN** `GET /healthz` and `GET /readyz` are requested from the gateway
- **THEN** both answer from the same container that serves `/{endpoint}/mcp` and `/api/v1/*`

#### Scenario: Metrics are served by the gateway
- **WHEN** `GET /metrics` is requested from the gateway with a service API key
- **THEN** the same container that serves `/{endpoint}/mcp` answers with Prometheus text-format metrics
