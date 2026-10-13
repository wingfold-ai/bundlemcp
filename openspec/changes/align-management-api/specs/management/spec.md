## MODIFIED Requirements

### Requirement: MGMT-1 Base path and resources
The management API SHALL be served under the base path `/api/v1` with these resources, each addressed by its natural
key (a name) where it has one: `upstreams`, `upstreams/{name}/tools`, `bundles`, `bundles/{name}/upstreams`
([UPS-16](../upstreams/spec.md)), `bundles/{name}/tools`, `bundles/{name}/prompts` and
`bundles/{name}/resources` ([BND-31](../bundles/spec.md)), `endpoints`, `auth`,
`users`, `audit-records`, `config`, and the read-only profile list at `profiles`
([EP-14](../endpoints/spec.md)), plus action routes (e.g. `upstreams/{name}:refresh-tools`,
`upstreams/{name}:probe`, `upstreams:inspect`, `endpoints/{name}:rename`, `api-keys/{id}:deactivate`). `:probe`
contacts the upstream now — connects, negotiates the protocol, records `connection_state` and counts toward
`health_status` — without re-listing its tools, and returns the outcome. It SHALL also serve `me` (caller identity
for the UI: kind, email, `is_admin` — answers 200 for any active signed-in session, admin or not, so the UI can render
its "no access" page ([UI-2](../admin-ui/spec.md)); service keys get their key identity), and
`me/endpoints` — the catalogue for that same audience: every enabled endpoint accepting `oauth`, with its connection
URL and the bundle's description, so a signed-in non-admin finds what to connect an MCP client to without any
privileged call.

#### Scenario: Non-admin session reads its identity
- **WHEN** a signed-in, active, non-admin user calls `GET /api/v1/me`
- **THEN** the response is 200 with `kind` `user` and `is_admin` false

#### Scenario: Service key reads its identity
- **WHEN** a caller presents a service-kind API key to `GET /api/v1/me`
- **THEN** the response is 200 with `kind` `service` and the key's id

#### Scenario: Catalogue lists only enabled OAuth endpoints
- **GIVEN** one enabled endpoint accepting `oauth`, one disabled endpoint, and one endpoint accepting only `api_key`
- **WHEN** a signed-in non-admin calls `GET /api/v1/me/endpoints`
- **THEN** only the enabled `oauth` endpoint is listed, with its connection URL and its bundle's description

#### Scenario: Anonymous caller is refused by me
- **WHEN** a request without a session cookie or service key calls `GET /api/v1/me`
- **THEN** the response is 401

#### Scenario: Profiles are a top-level resource
- **WHEN** an admin calls `GET /api/v1/profiles`
- **THEN** the response lists the built-in profiles with their descriptions and warnings

#### Scenario: Probing an upstream does not touch its tools
- **WHEN** an admin calls `POST /api/v1/upstreams/{name}:probe` for a reachable upstream
- **THEN** the response reports the negotiated connection, the upstream's `connection_state` is `ready`, and its cached
  tools are unchanged

### Requirement: MGMT-4 Registrar use case
`PUT /api/v1/upstreams/{name}` SHALL be a **config-only upsert** — create-or-update by name, idempotent, returning the
canonical server representation including its current tool cache (the tools discovered so far; empty for a server not
yet discovered). It SHALL never block on probing the upstream ([UPS-2](../upstreams/spec.md)
allows registering not-yet-started servers; discovery runs in the background), so a discovery loop can converge by
repeatedly PUTting desired state. The DTO tolerates an optional `transport` field but SHALL accept only
`streamable-http` — anything else is a 422 whose message names the field and the one supported value — so registrar
payloads carrying the field don't break.

#### Scenario: Repeated PUT converges
- **WHEN** the same body `{"name": "seo", "url": "http://seo:8000/mcp", "transport": "streamable-http"}` is PUT twice
  to `/api/v1/upstreams/seo`
- **THEN** both responses are 200 with the same `id`, and the upstream list holds one server

#### Scenario: Upsert response carries the tool cache
- **GIVEN** upstream `seo` whose discovery has cached tools `audit` and `rank`
- **WHEN** its configuration is PUT again unchanged
- **THEN** the response lists the cached tools `audit` and `rank`, and no probe is started

#### Scenario: Unsupported transport
- **WHEN** a PUT body carries `"transport": "stdio"`
- **THEN** the response is 422 with a message stating that `transport` must be `streamable-http`

#### Scenario: Path and body name disagree
- **WHEN** the body's `name` differs from the `{name}` in the path
- **THEN** the response is 422

### Requirement: MGMT-5 Validation and pagination
Mutations SHALL be validated (Pydantic + domain rules from the owning specs) and return the canonical resource
representation. List routes SHALL support offset/limit pagination (default page size 50, max 500) with a stable
ordering by creation time then id — newest first for audit records — and the filters the UI needs.

#### Scenario: Default page
- **WHEN** a client lists `/api/v1/upstreams` without paging parameters
- **THEN** the envelope reports `offset` 0 and `limit` 50

#### Scenario: Out-of-range paging is rejected
- **WHEN** a client lists with `limit=0`, `limit=501`, `offset=-1` or a non-numeric limit
- **THEN** the response is 422

#### Scenario: Bundle prompts page in creation order
- **GIVEN** a bundle whose prompt `zeta` was created before prompt `alpha`
- **WHEN** a client lists `/api/v1/bundles/{name}/prompts`
- **THEN** `zeta` is listed before `alpha`
