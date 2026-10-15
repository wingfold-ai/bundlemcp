## MODIFIED Requirements

### Requirement: MGMT-4 Registrar use case
`PUT /api/v1/upstreams/{name}` SHALL be a **config-only upsert** — create-or-update by name, idempotent, returning the
canonical server representation (the tool cache is read from `upstreams/{name}/tools`). It SHALL never block on probing
the upstream ([UPS-2](../upstreams/spec.md) allows registering not-yet-started servers; discovery runs in the
background), so a discovery loop can converge by repeatedly PUTting desired state. The DTO tolerates an optional
`transport` field but SHALL accept only `streamable-http` — anything else is a 422 whose message names the field and
the one supported value — so registrar payloads carrying the field don't break.

#### Scenario: Repeated PUT converges
- **WHEN** the same body `{"name": "seo", "url": "http://seo:8000/mcp", "transport": "streamable-http"}` is PUT twice
  to `/api/v1/upstreams/seo`
- **THEN** both responses are 200 with the same `id`, and the upstream list holds one server

#### Scenario: Unsupported transport
- **WHEN** a PUT body carries `"transport": "stdio"`
- **THEN** the response is 422 with a message stating that `transport` must be `streamable-http`

#### Scenario: Path and body name disagree
- **WHEN** the body's `name` differs from the `{name}` in the path
- **THEN** the response is 422
