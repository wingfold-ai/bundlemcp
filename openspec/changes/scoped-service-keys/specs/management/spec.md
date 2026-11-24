# Spec Delta

## ADDED Requirements

### Requirement: MGMT-23 Every management route declares its access
Every management route (`/api/v1/*` and `/metrics`) SHALL declare the access it needs: one scope of
[AUTH-40](../auth/spec.md), or full access, which only an admin session or a service key without scopes has. Reads of
bundles, endpoints, upstreams, API keys and runtime settings SHALL need `read`; writes to bundles (with their members,
curation, prompts and resources) `bundles:write`; to endpoints `endpoints:write`; to upstreams (with discovery,
inspection by URL and upstream OAuth) `upstreams:write`; to API keys `keys:manage`. Every other route SHALL need full
access. A route without a declaration SHALL NOT be served, and the declaration SHALL be published in the OpenAPI
document as `x-bundlemcp-access`.

#### Scenario: Undeclared route
- **WHEN** a management route is added without declaring its access
- **THEN** the gateway does not build it, and the route audit test fails

#### Scenario: Full-access route
- **WHEN** a service key holding every scope calls `GET /api/v1/audit-records`
- **THEN** the gateway answers 403, while a service key without scopes is accepted

## MODIFIED Requirements

### Requirement: MGMT-2 Authentication
Every management route SHALL require either an admin browser session ([auth](../auth/spec.md)) or a `service`-kind API
key ([AUTH-23](../auth/spec.md)) via the `Authorization` header that grants the route's access
([MGMT-23](../management/spec.md)); `me` and `me/endpoints` are the exception and accept any active signed-in session.
Missing credentials SHALL be answered 401, and an endpoint-kind key or a scoped service key without the route's access
403, both as structured JSON error bodies.

#### Scenario: No credentials
- **WHEN** a request without credentials calls `GET /api/v1/upstreams`
- **THEN** the response is 401 with a JSON `detail`

#### Scenario: Endpoint-kind key is forbidden
- **WHEN** a request presents an `endpoint`-kind API key to `GET /api/v1/upstreams`
- **THEN** the response is 403

#### Scenario: Scoped key without the route's access is forbidden
- **WHEN** a request presents a service key scoped to `read` to `DELETE /api/v1/upstreams/x`
- **THEN** the response is 403

### Requirement: MGMT-10 API keys at bootstrap
Each `api_keys` entry SHALL name a key, its kind, for an endpoint-kind key its endpoints by name, and for a
service-kind key optionally its `scopes` ([AUTH-40](../auth/spec.md)), and take its
value from a named environment variable — the document never holds a key value — or as `create_if_missing`, generated
and written to the file the entry names, created with mode `0600`; the value never appears in a log line. A file that
already exists is never overwritten: when it holds a well-formed `bmcp_sk_…` value that value is used, otherwise the
document does not land. A key whose name already exists is never overwritten. When
`BUNDLEMCP_INITIAL_SERVICE_KEY` is set and no service key exists, the gateway SHALL also provision a service key with
that value.

#### Scenario: First boot provisions the key
- **GIVEN** no service-kind key exists and `BUNDLEMCP_INITIAL_SERVICE_KEY` is set
- **WHEN** the gateway starts
- **THEN** a service key with that value exists and authenticates management calls

#### Scenario: Existing service key is kept
- **GIVEN** a service-kind key already exists
- **WHEN** the gateway starts with `BUNDLEMCP_INITIAL_SERVICE_KEY` set
- **THEN** no key is created or changed

#### Scenario: Key value from an environment reference
- **GIVEN** an `api_keys` entry `registrar` of kind `service` naming the variable `REGISTRAR_KEY`, and that variable
  holds a well-formed `bmcp_sk_…` value
- **WHEN** the gateway starts with no key named `registrar`
- **THEN** a service key `registrar` exists, authenticates with the variable's value, and only its hash is stored

#### Scenario: Missing referenced variable invalidates the document
- **GIVEN** an `api_keys` entry naming a variable that is unset, or holds a value not in the `bmcp_sk_…` format
- **WHEN** the document is applied
- **THEN** the document does not land and the strict-mode rule (MGMT-11) decides whether the gateway starts

#### Scenario: Plaintext value is refused
- **WHEN** an `api_keys` entry carries a key value inline instead of a variable reference or `create_if_missing`
- **THEN** the document fails validation

#### Scenario: Generated key is written to its file
- **GIVEN** an `api_keys` entry `ci` of kind `endpoint` with `create_if_missing` writing to `/secrets/ci.key`, scoped
  to endpoint `demo`
- **WHEN** the gateway starts for the first time
- **THEN** a key `ci` scoped to `demo` is created, `/secrets/ci.key` holds its value with mode `0600`, and no log line
  carries the value
- **AND** on the next start no key is created and the file is unchanged

#### Scenario: An existing file is reused, not overwritten
- **GIVEN** `/secrets/ci.key` holds a well-formed key value and no key named `ci` exists
- **WHEN** the document is applied
- **THEN** key `ci` is created with the value from the file, and the file is unchanged

#### Scenario: Existing key is never overwritten
- **GIVEN** a key named `registrar` already exists, possibly deactivated or with another scope
- **WHEN** a document with an `api_keys` entry `registrar` is applied
- **THEN** the stored key's value, kind, scope and state are unchanged

#### Scenario: Scope names an unknown endpoint
- **WHEN** an endpoint-kind entry is scoped to an endpoint name that neither the document nor the store defines
- **THEN** the document does not land

#### Scenario: Scoped service key from an environment reference
- **GIVEN** an `api_keys` entry `edge-filter` of kind `service` with `scopes: [introspect]` naming the variable
  `EDGE_KEY`, which holds a well-formed `bmcp_sk_…` value
- **WHEN** the gateway starts with no key named `edge-filter`
- **THEN** a service key `edge-filter` scoped to `introspect` exists and authenticates only introspection

#### Scenario: Scopes on an endpoint key are refused
- **WHEN** an `api_keys` entry of kind `endpoint` names scopes, or any entry names an unknown scope
- **THEN** the document fails validation
