# management Specification

## Purpose

Configuring the gateway without clicking. The versioned management REST API under /api/v1 (the admin UI uses nothing
else, so everything is automatable), authenticated by admin session or service key, with its DTOs, pagination,
retry-safe writes and browser-facing protections. Bootstrap provisions upstreams, bundles and endpoints idempotently
from a document at startup, through the same code paths as the API. Export and import of the whole configuration will
live here once built.

The UI on top of this API is the admin-ui slice.

It merges what were separate specs until 2026-10-13: Management API, Bootstrap.

## Requirements

### Requirement: MGMT-1 Base path and resources
The management API SHALL be served under the base path `/api/v1` with these resources, each addressed by its natural
key (a name) where it has one: `upstreams`, `upstreams/{name}/tools`, `bundles`, `bundles/{name}/upstreams`
([UPS-16](../upstreams/spec.md)), `bundles/{name}/tools`, `bundles/{name}/prompts` and
`bundles/{name}/resources` ([BND-31](../bundles/spec.md)), `endpoints`, `api-keys`, `users`,
`audit-records`, `config`, and the read-only profile list at `endpoints/profiles`
([EP-14](../endpoints/spec.md)), plus action routes (e.g. `upstreams/{name}:refresh-tools`,
`upstreams:inspect`, `endpoints/{name}:rename`, `api-keys/{id}:deactivate`). It SHALL also serve `me` (caller identity
for the UI: kind, email, `is_admin` — answers 200 for any active signed-in session, admin or not, so the UI can render
its "no access" page ([UI-2](../admin-ui/spec.md)); service keys get their key identity), and `me/endpoints` — the
catalogue for that same audience: every enabled endpoint accepting `oauth`, with its connection URL and the bundle's
description, so a signed-in non-admin finds what to connect an MCP client to without any privileged call.

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

### Requirement: MGMT-2 Authentication
Every management route SHALL require either an admin browser session ([auth](../auth/spec.md)) or a
`service`-kind API key ([AUTH-23](../auth/spec.md)) via the `Authorization` header; `me` and `me/endpoints` are the
exception and accept any active signed-in session. Missing credentials SHALL be answered 401 and an endpoint-kind key
403, both as structured JSON error bodies.

#### Scenario: No credentials
- **WHEN** a request without credentials calls `GET /api/v1/upstreams`
- **THEN** the response is 401 with a JSON `detail`

#### Scenario: Endpoint-kind key is forbidden
- **WHEN** a request presents an `endpoint`-kind API key to `GET /api/v1/upstreams`
- **THEN** the response is 403

### Requirement: MGMT-3 DTOs and OpenAPI
Request and response DTOs SHALL be Pydantic models mapped from the domain entities
([ARC-3](../architecture/spec.md)); the OpenAPI schema SHALL be served at `/api/v1/openapi.json` and used to generate
the frontend client ([ARC-4](../architecture/spec.md)).

#### Scenario: OpenAPI document is served
- **WHEN** a client requests `GET /api/v1/openapi.json`
- **THEN** it receives the OpenAPI document describing the management routes

#### Scenario: Generated client is current
- **WHEN** CI regenerates `apps/web/openapi.json` and `apps/web/types/api.d.ts`
- **THEN** the regenerated files are identical to the committed ones, or the build fails

### Requirement: MGMT-4 Registrar use case
`PUT /api/v1/upstreams/{name}` SHALL be a **config-only upsert** — create-or-update by name, idempotent, returning the
canonical server representation (the tool cache is read from `upstreams/{name}/tools`). It SHALL never block on probing
the upstream ([UPS-2](../upstreams/spec.md) allows registering not-yet-started servers; discovery runs in the
background), so a discovery loop can converge by repeatedly PUTting desired state. The DTO tolerates an optional
`transport` field but SHALL accept only `streamable-http` (422 otherwise) — so registrar payloads carrying the field
don't break.

#### Scenario: Repeated PUT converges
- **WHEN** the same body `{"name": "seo", "url": "http://seo:8000/mcp", "transport": "streamable-http"}` is PUT twice
  to `/api/v1/upstreams/seo`
- **THEN** both responses are 200 with the same `id`, and the upstream list holds one server

#### Scenario: Unsupported transport
- **WHEN** a PUT body carries `"transport": "stdio"`
- **THEN** the response is 422

#### Scenario: Path and body name disagree
- **WHEN** the body's `name` differs from the `{name}` in the path
- **THEN** the response is 422

### Requirement: MGMT-5 Validation and pagination
Mutations SHALL be validated (Pydantic + domain rules from the owning specs) and return the canonical resource
representation. List routes SHALL support offset/limit pagination (default page size 50, max 500) with a stable
ordering — creation time then id for registry resources, newest first for audit records, name for a bundle's prompts
and resources — and the filters the UI needs.

#### Scenario: Default page
- **WHEN** a client lists `/api/v1/upstreams` without paging parameters
- **THEN** the envelope reports `offset` 0 and `limit` 50

#### Scenario: Out-of-range paging is rejected
- **WHEN** a client lists with `limit=0`, `limit=501`, `offset=-1` or a non-numeric limit
- **THEN** the response is 422

### Requirement: MGMT-6 Retryable writes
Write operations SHALL be safely retryable: upserts by natural key where sensible (MGMT-4), and deletes idempotent —
deleting a resource that does not exist answers 204.

#### Scenario: Deleting a missing resource
- **WHEN** a client calls `DELETE /api/v1/upstreams/ghost` and no such upstream exists
- **THEN** the response is 204

### Requirement: MGMT-7 Browser-facing security
Browser-facing security SHALL follow [SEC-4](../security/spec.md): credentials-enabled CORS for exactly the configured
web origins, and an Origin/Referer check on cookie-authenticated mutations. Consent revocation
([AUTH-11](../auth/spec.md)) and user deactivation ([AUTH-20](../auth/spec.md)) SHALL be exposed as routes
(`DELETE /api/v1/users/{id}/consents/{consent_id}`, `POST /api/v1/users/{id}:deactivate`).

#### Scenario: Cross-site mutation with an admin cookie
- **WHEN** an admin session cookie accompanies a `PUT` whose `Origin` is neither the gateway nor an allowlisted web
  origin
- **THEN** the response is 403

#### Scenario: Service key is not origin-checked
- **WHEN** a service-kind key performs a mutation without an `Origin` header
- **THEN** the request is processed normally

### Requirement: MGMT-8 Document sources
The gateway SHALL read a bootstrap document from `BUNDLEMCP_BOOTSTRAP_FILE` (path to a YAML/JSON file,
compose-friendly) and/or `BUNDLEMCP_BOOTSTRAP` (the same document inline as JSON); when both are set, the file is
applied first, then the inline document. The document SHALL be a Pydantic-validated model carrying a format `version`
(only `1` exists; any other value is rejected) and the lists `upstreams`, `bundles` and `endpoints`.

#### Scenario: Both sources apply
- **GIVEN** `BUNDLEMCP_BOOTSTRAP_FILE` names a file registering upstream `filed` and `BUNDLEMCP_BOOTSTRAP` inlines a
  document registering upstream `echo`
- **WHEN** the gateway starts
- **THEN** both `filed` and `echo` are registered

#### Scenario: Unknown version is refused
- **WHEN** a document declares `"version": 2`
- **THEN** it fails validation instead of being applied

### Requirement: MGMT-9 Idempotent upserts through the API's code path
The document SHALL be applied on startup as **upserts by natural key** (upstream server/bundle/endpoint names) — the
same service operations the management API uses ([MGMT-4](../management/spec.md), MGMT-6) — inside one transaction,
so a document lands entirely or not at all. Running the same bootstrap twice SHALL be a no-op.

#### Scenario: Re-applying changes nothing
- **WHEN** the same document is applied twice
- **THEN** the second run creates no further rows and changes no stored resource

#### Scenario: A failing document leaves nothing behind
- **WHEN** one entry of a document fails a domain rule
- **THEN** no resource from that document is stored

### Requirement: MGMT-10 Initial service key
When `BUNDLEMCP_INITIAL_SERVICE_KEY` is set, the gateway SHALL provision a service-kind API key with that value at
startup if no service key exists yet, so the management API is reachable headlessly. Existing keys SHALL never be
overwritten; once any service key exists the setting is ignored.

#### Scenario: First boot provisions the key
- **GIVEN** no service-kind key exists and `BUNDLEMCP_INITIAL_SERVICE_KEY` is set
- **WHEN** the gateway starts
- **THEN** a service key with that value exists and authenticates management calls

#### Scenario: Existing service key is kept
- **GIVEN** a service-kind key already exists
- **WHEN** the gateway starts with `BUNDLEMCP_INITIAL_SERVICE_KEY` set
- **THEN** no key is created or changed

### Requirement: MGMT-11 Strict mode
Bootstrap failures SHALL follow `BUNDLEMCP_BOOTSTRAP_STRICT`: `true` → refuse to start (CI/production), `false`
(default) → log and continue (dev convenience).

#### Scenario: Strict mode refuses to start
- **GIVEN** `BUNDLEMCP_BOOTSTRAP_STRICT=true`
- **WHEN** the bootstrap document is invalid
- **THEN** startup fails with the error

#### Scenario: Lenient mode logs and continues
- **GIVEN** `BUNDLEMCP_BOOTSTRAP_STRICT` is unset
- **WHEN** the bootstrap document is invalid
- **THEN** a `bootstrap.failed` error is logged and the gateway starts

### Requirement: MGMT-12 Bootstrapped resources are ordinary
Resources created by bootstrap SHALL be ordinary resources — editable in the UI afterwards; bootstrap does not "own" or
re-lock them (last write wins, no reconciliation loop — that's a registrar-style external agent's job via the API).

#### Scenario: Edit after bootstrap
- **GIVEN** a bundle created by bootstrap
- **WHEN** an admin changes its description through the management API
- **THEN** the change is accepted and stays until the next start re-applies the document

### Requirement: MGMT-13 Demo bootstrap
The dev compose stack SHALL ship a demo bootstrap file ([DOC-3](../documentation/spec.md)) so a fresh install
starts non-empty.

#### Scenario: Demo seed is valid
- **WHEN** `deploy/seed.yaml` is parsed as a bootstrap document
- **THEN** it validates and declares at least one upstream, bundle and endpoint

### Requirement: MGMT-14 Discovery after commit
Every server the document creates, or updates in a way that needs a probe ([UPS-2](../upstreams/spec.md)),
SHALL be discovered ([UPS-17](../upstreams/spec.md)) through the same best-effort background probe as a
management-API create, scheduled only after the document's transaction commits — a probe runs in its own transaction
and would not see an uncommitted server. A fresh start therefore serves the servers' tools without a manual refresh. A
failed probe is recorded on the server ([UPS-4](../upstreams/spec.md)) and never fails the bootstrap, strict or
not; a document that does not land probes nothing.

#### Scenario: Fresh bootstrap serves tools
- **WHEN** a document registering a reachable upstream is applied
- **THEN** the upstream's tools are cached without a manual refresh

#### Scenario: Unreachable upstream under strict mode
- **GIVEN** `BUNDLEMCP_BOOTSTRAP_STRICT=true` and an unreachable upstream in the document
- **WHEN** the gateway starts
- **THEN** startup succeeds and the server's connection state records the failure

#### Scenario: Failed document probes nothing
- **WHEN** a document fails to apply
- **THEN** no discovery probe is scheduled

#### Scenario: Re-applied document wakes no working upstream
- **GIVEN** a server whose last probe succeeded
- **WHEN** the unchanged document is applied again on restart
- **THEN** no probe is scheduled for it

### Requirement: MGMT-15 Key names
The document SHALL list upstream servers under `upstreams`, and a bundle SHALL list its members under `upstreams`
([UPS-16](../upstreams/spec.md)), and its own prompts and resources under `prompts` and `resources`
([BND-32](../bundles/spec.md)). An unknown key in the document or in a bundle entry — a typo, or the
former name `servers` — SHALL make the document invalid (MGMT-11 applies) rather than being ignored, so an outdated
document fails loudly instead of quietly provisioning nothing.

#### Scenario: Former top-level key
- **WHEN** a document lists servers under `servers`
- **THEN** validation fails naming `servers`

#### Scenario: Former bundle member key
- **WHEN** a bundle entry lists its members under `servers`
- **THEN** validation fails naming `servers`

### Requirement: MGMT-16 Upstream OAuth client in the document
A server entry MAY carry an `upstream_oauth` block — the pre-registered client the gateway presents to the server's
authorization server ([UPS-25](../upstreams/spec.md)), in the same shape as the management API's client route
takes. When present it SHALL be applied after the server's upsert, inside the document's transaction, exactly as that
route applies it: the client secret is encrypted at rest and never returned. Storing a client needs token encryption
keys ([DEP-9](../deployment/spec.md)); a document that names one without them SHALL NOT land, so a secret is never
stored in the clear.

#### Scenario: Client applied with the server
- **GIVEN** token encryption keys are configured
- **WHEN** a document's server entry carries `upstream_oauth`
- **THEN** the client is stored as the client route would store it, and re-applying changes nothing

#### Scenario: No encryption keys
- **GIVEN** no token encryption keys are configured
- **WHEN** a document's server entry carries `upstream_oauth`
- **THEN** the document does not apply and no server from it is stored

## Out of scope

### Management API

- GraphQL/tRPC surfaces.
- Webhooks/event subscriptions (possible later addition; poll `audit-records` and resource `updated_at` for now).

### Bootstrap

- Continuous reconciliation / GitOps-style drift correction.
- Provisioning users (users come from OIDC — [AUTH-16](../auth/spec.md)).

## Notes

### Management API

Origin: new — fixes the first consumer's biggest integration wart, a registrar client that replayed cookie logins and
hand-crafted tRPC batch calls because metamcp had no service API.

### Bootstrap

Origin: metamcp carry-over (fork feature); prior art `../metamcp/apps/backend/src/lib/bootstrap.service.ts`
(`BOOTSTRAP_*` env JSON). The document is intended to share its schema with the export format of
[add-export-import](../../changes/add-export-import/proposal.md), which does not exist yet.
