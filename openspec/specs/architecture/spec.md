# architecture Specification

## Purpose

How the system is built and what it stores. The two-container shape of bundlemcp (a Python gateway serving MCP
endpoints, OAuth and the management API, and an optional Nuxt admin app), the stack and version policy, and the state
model behind the restart-safety promise: Postgres for everything durable, a RESP store (Valkey) for everything live, and
no in-memory-only state a request depends on. It also defines the persisted entities, their naming rules, cascades and
secret-bearing columns, and the package layout with its layer rules.

Behaviour that clients observe lives in the feature slices; this slice holds the structural rules they all rely on.

It merges what were separate specs until 2026-10-13: Architecture, Domain model.

## Requirements

### Requirement: ARC-1 Latest stable versions
Every framework/tool MUST be adopted at its **latest stable version** at the time of implementation, and dependencies
MUST specify minimum-version pins (`>=`) rather than exact pins for libraries. Staying current is a standing rule, not a
one-time choice.

#### Scenario: Library dependencies use minimum-version pins
- **WHEN** a library dependency is declared in a `pyproject.toml` of the uv workspace
- **THEN** it is pinned with `>=` (e.g. `fastmcp>=4.0.3`), never with an exact `==` pin

### Requirement: ARC-2 Runtime versions
The gateway SHALL require Python ≥ 3.13 (`requires-python = ">=3.13"`) and SHALL be built, tested and shipped on the
latest stable Python release, 3.14 at the time of writing. The repository declares that version in one place, and
every image that runs Python (the gateway and the example upstreams) and every CI job that sets up Python uses exactly
the declared version. The web app SHALL be built and run on Node ≥ 24: `apps/web/package.json` declares it in
`engines`, every CI and publishing job that runs Node uses 24 or later, and the web image runs Node 26.

#### Scenario: Gateway refuses an older Python
- **WHEN** the workspace is installed with a Python older than 3.13
- **THEN** `uv sync` rejects the interpreter because of `requires-python`

#### Scenario: Web app is built on Node 24 or later
- **WHEN** CI builds the web app or the web image is built
- **THEN** the Node version used is 24 or later

#### Scenario: Images and CI use the declared Python
- **GIVEN** the repository declares Python 3.14 as the shipped version
- **WHEN** an image's base or build stage, or a CI job, names a different Python version
- **THEN** the hermetic test suite fails and names the file and the version it found

#### Scenario: Shipped gateway runs the declared Python
- **WHEN** the gateway image is built and started
- **THEN** it runs on the declared Python version and reports ready

#### Scenario: Older Node is refused by the web app
- **WHEN** `npm ci` runs in `apps/web` under Node 22 with engine checks enforced
- **THEN** the install fails on the `engines` constraint

#### Scenario: No CI job runs an older Node
- **WHEN** the workflows under `.github/workflows/` are inspected
- **THEN** every `node-version` they set is 24 or later

### Requirement: ARC-3 Pydantic everywhere
Every structured value MUST be a Pydantic model; no `dataclasses`. Domain entities are plain `BaseModel` classes in
`domain/` with no ORM import; their tables are SQLModel row classes in `infrastructure/postgres/rows/`, mapped by the
repositories; API request/response DTOs are `BaseModel` classes in `application/schemas/`. A persisted field is
therefore declared twice — once on the entity, once on the row — and the repository is the only place the two meet
([ADR-0034](../../../docs/adr/0034-pydantic-entities-and-row-classes.md), which replaced the single-SQLModel-class rule
this requirement previously stated).

#### Scenario: No dataclasses in the library
- **WHEN** the library code under `packages/bundlemcp/` is searched for `dataclass`
- **THEN** there is no match

#### Scenario: Domain stays ORM-free
- **WHEN** `uv run lint-imports` runs
- **THEN** the contract that keeps `domain/` and `application/` free of drivers (SQLAlchemy, SQLModel, redis, httpx, …)
  is kept

### Requirement: ARC-4 Generated frontend types
The gateway MUST publish its OpenAPI schema, and the web app MUST generate its TypeScript client types from it
(openapi-typescript) as a build step. Frontend DTOs are **generated, never hand-written**.

#### Scenario: A stale generated contract fails CI
- **WHEN** a DTO or route changes and `apps/web/openapi.json` / `apps/web/types/api.d.ts` were not regenerated
- **THEN** the CI step that runs `npm run openapi` and `git diff --exit-code` on both files fails

### Requirement: ARC-5 Validation at the API boundary
All tool/endpoint/server inputs MUST be validated by Pydantic at the API boundary; validation errors return structured
422 responses.

#### Scenario: Invalid input is rejected with 422
- **WHEN** a management API request body violates its DTO (e.g. a server name with a space)
- **THEN** the response is `422` with a structured list of validation errors

### Requirement: ARC-6 Package layout and layers
All gateway logic MUST live in `packages/bundlemcp`; `apps/gateway` is a thin entrypoint. The web app is self-contained
in `apps/web`. The library is four clean-architecture layers plus a composition root, with dependencies pointing inward
only, enforced by `lint-imports` ([ADR-0033](../../../docs/adr/0033-clean-architecture-layers.md)). The authoritative
description of each package is [`packages/bundlemcp/README.md`](../../../packages/bundlemcp/README.md) — this spec fixes
the layer *names* and the dependency rule, not the contents.

#### Scenario: An outward import breaks the build
- **WHEN** a module in `domain/` or `application/` imports from `infrastructure/`, `api/` or `main/`
- **THEN** `uv run lint-imports` fails the layers contract

### Requirement: ARC-7 Postgres is the durable store
Postgres MUST hold the durable state: servers, bundles, endpoints, tools cache, users, OAuth clients/codes/tokens,
upstream OAuth tokens, API keys, audit log, config. Postgres is the system of record.

#### Scenario: Configuration survives a RESP-store flush
- **WHEN** the RESP store is emptied and the gateway restarts
- **THEN** every upstream, bundle, endpoint, API key and config value is still served, because it is read from Postgres

### Requirement: ARC-8 RESP store holds live state
The RESP store MUST hold the live state: MCP session state, upstream session bindings, rate-limit counters, the
live-log ring buffer ([OPS-14](../operations/spec.md)), cross-replica pub/sub. The store never holds configuration;
outage behavior is explicitly defined in the degradation matrix
([SES-14](../sessions/spec.md)) — bounded, honest degradation, not silent failure. The store
is a **RESP-compatible** server — the default is **Valkey** (BSD-3), accessed via the MIT `redis-py` client
([ADR-0022](../../../docs/adr/0022-valkey-store.md)); "Redis" elsewhere in these specs denotes this RESP
store/protocol, not the Redis product specifically.

#### Scenario: Session records live in the RESP store
- **WHEN** a client initializes a session against an endpoint
- **THEN** the session record is written to the RESP store, not to process memory

#### Scenario: Config changes travel over pub/sub
- **WHEN** a config-class record is changed through the management API
- **THEN** an invalidation event is published on the RESP store's invalidation channel after the commit

#### Scenario: The live-log buffer lives in the RESP store
- **WHEN** a replica logs an event at or above the live-log threshold
- **THEN** the event is appended to the capped log stream in the RESP store, not kept in process memory

### Requirement: ARC-9 Any replica serves any request
A request MUST be servable by **any gateway replica**: no process-local state may be required to route or answer a
request (details in [sessions](../sessions/spec.md)).

#### Scenario: Alternating replicas on one session
- **WHEN** two replicas share Postgres and the RESP store and a client's requests on one session alternate between them
- **THEN** each request is answered from the shared session record

### Requirement: ARC-10 Restarts keep sessions
A gateway restart MUST NOT invalidate client sessions that are otherwise still within their lifetime.

#### Scenario: Session survives a restart
- **WHEN** the gateway restarts while a client session is within its lifetime
- **THEN** the client's next request with the same session id succeeds without re-initializing

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

### Requirement: ARC-12 Web app is a separate container
The web app is a separate container; it SHALL talk to the gateway only through the management API and the admin
sign-in/sign-out routes ([auth](../auth/spec.md)). Nothing in the gateway depends on the web app.

#### Scenario: Gateway runs without the web app
- **WHEN** the gateway is started without the web container
- **THEN** the MCP endpoints, OAuth server and management API all serve normally

### Requirement: ARC-13 One-command compose stack
`deploy/docker-compose.yml` MUST bring up a working stack (gateway, web, Postgres, Valkey, and an OIDC IdP for
development) with a single command; TLS termination is left to the operator's proxy. Public base URL, trusted-proxy
headers, and cookie attributes are governed by [deployment](../deployment/spec.md) (DEP-1/DEP-2).

#### Scenario: Stack comes up with one command
- **WHEN** an operator runs `docker compose -f deploy/docker-compose.yml up`
- **THEN** the gateway, web app, Postgres, Valkey and the development IdP start, without any optional profile

### Requirement: ARC-14 Hermetic tests and green gates
Unit tests are hermetic (no Docker, no network): in-memory/fake Redis and SQLite-or-fixture Postgres where feasible.
Integration tests run against the compose stack. `uv run pytest -q` and `uv run ruff check .` MUST be green before any
change is done.

#### Scenario: The unit suite runs without Docker or network
- **WHEN** `uv run pytest -q` runs on a machine without Docker or network access
- **THEN** the suite runs on in-memory SQLite and fakeredis and passes

#### Scenario: CI enforces the gates
- **WHEN** a pull request is opened
- **THEN** CI runs `uv run ruff check .` and `uv run pytest -q`, and a failure in either fails the build

### Requirement: ARC-15 Clock assumptions
Time-window logic (rate limits, token expiry) MUST NOT assume perfectly synced replica clocks: rate-limit windows use
the RESP store's server time; token/code expiry tolerates ordinary NTP-level skew (documented assumption: replicas run
NTP).

#### Scenario: Rate-limit buckets use the store's clock
- **WHEN** a rate-limit or auth-failure counter is incremented
- **THEN** the window bucket is computed from the RESP store's `TIME`, not from the replica's clock

### Requirement: ARC-16 Row classes and Alembic migrations
Every persisted entity listed in this spec MUST have a SQLModel row class in `infrastructure/postgres/rows/`, mapped to
its Pydantic entity by its repository ([ADR-0034](../../../docs/adr/0034-pydantic-entities-and-row-classes.md));
migrations MUST be Alembic-managed from the first table.

#### Scenario: Schema comes from Alembic
- **WHEN** the gateway container starts against an empty Postgres database
- **THEN** `alembic upgrade head` creates the schema, starting with `0001_initial_schema`, before the gateway serves

#### Scenario: Unique constraints hold at the row level
- **WHEN** two servers with the same `name`, or two `BundleServer` rows for the same `(bundle_id, server_id)`, are
  inserted
- **THEN** the database rejects the second insert

### Requirement: ARC-17 Cascades and surviving audit records
Deleting a server MUST cascade its tools and mapping rows; deleting a bundle MUST cascade mappings and endpoints; audit
records survive deletes (FKs nullable + denormalized name columns).

#### Scenario: Deleting a server removes its tools and memberships
- **WHEN** a server that has cached tools and is a member of a bundle is deleted
- **THEN** its `Tool`, `BundleServer` and `BundleTool` rows are deleted with it

#### Scenario: Deleting a bundle removes its mappings and endpoints
- **WHEN** a bundle with members, curated tools, own prompts/resources and endpoints is deleted
- **THEN** its `BundleServer`, `BundleTool`, `BundlePrompt`, `BundleResource` and `Endpoint` rows are deleted with it

#### Scenario: Audit records outlive what they name
- **WHEN** an endpoint that has audit records is deleted
- **THEN** the audit records remain, with `endpoint_id` set to null and the denormalized names intact

### Requirement: ARC-18 Secret-bearing columns
Secret-bearing columns (token values, api keys, client secrets) MUST be stored hashed where only equality checks are
needed, and MUST NOT appear in logs or API responses (upstream OAuth tokens and client secrets must be recoverable, so
they are stored encrypted at rest rather than hashed).

#### Scenario: Gateway-issued secrets are stored as hashes
- **WHEN** an API key, an OAuth client secret, an authorization code or an access/refresh token is issued
- **THEN** only its hash is persisted (`key_hash`, `client_secret_hash`, `code_hash`, `access_token_hash`,
  `refresh_token_hash`)

#### Scenario: Upstream tokens are encrypted, not hashed
- **WHEN** an upstream OAuth token set is stored
- **THEN** it is persisted encrypted (`tokens_encrypted`) and can be decrypted for the upstream call

### Requirement: ARC-19 Name rules
`name` fields used in URLs or tool prefixes MUST enforce `^[a-zA-Z0-9_-]+$` at the Pydantic layer and in a DB
constraint. **Server names** additionally MUST NOT contain `__` (double underscore), so prefixed tool names parse
unambiguously ([BND-2](../bundles/spec.md)).

#### Scenario: A name with a forbidden character is rejected
- **WHEN** a server, bundle or endpoint is written with a name such as `my server` or `a.b`
- **THEN** the API answers `422`

#### Scenario: A server name with a double underscore is rejected
- **WHEN** a server is written with the name `foo__bar`
- **THEN** the API answers `422`, while a bundle may still be named `foo__bar`

#### Scenario: The database enforces the pattern too
- **WHEN** a statement bypassing the API inserts a server name containing `__` into Postgres
- **THEN** the check constraint `ck_mcp_servers_name` rejects it

### Requirement: ARC-20 Config-class entities invalidate across replicas
Config-class entities MUST participate in cross-replica cache invalidation per
[sessions](../sessions/spec.md).

#### Scenario: A config change is announced to every replica
- **WHEN** a server, bundle, bundle tool, endpoint, API key or runtime config entry is created, updated or deleted
- **THEN** an invalidation event naming its entity type and key is published after the commit

## Out of scope

### Architecture

- Kubernetes manifests (compose first; k8s can come later) — upgrade/rollout rules are in
  [deployment](../deployment/spec.md).
- Multi-region or geo-distribution concerns.

### Domain model

- Organizations/teams/ownership columns (single workspace — see decision log in [../../README.md](../../README.md)).

## Notes

### Architecture

#### Stack

| Layer | Choice |
|---|---|
| MCP framework | **FastMCP v4** on MCP SDK v2 (dual-era client; proxying, composition, middleware) |
| HTTP/API | **FastAPI** on uvicorn |
| Models/ORM | **SQLModel** (Pydantic-native, on SQLAlchemy 2.0 async + asyncpg) |
| Migrations | **Alembic** |
| Validation/config | **Pydantic v2** + `pydantic-settings` (`BUNDLEMCP_` env prefix) |
| Live state | **Valkey** (BSD-3, RESP; `redis-py` async client, MIT) |
| Frontend | **Nuxt 4** + **Nuxt UI v4** (Tailwind v4) |
| Python tooling | **uv** workspace, **ruff**, **pytest** |

#### Repository layout

uv workspace monorepo, following the `packages/` (importable libraries, flat, no `src/`) + `apps/` (deployable
applications) convention:

```
bundlemcp/
├── packages/
│   └── bundlemcp/            # the library: all gateway code
│       └── bundlemcp/
│           ├── domain/           # entities, value objects, rules; no I/O
│           ├── application/      # use cases, contracts/, schemas/, settings/
│           ├── infrastructure/   # one adapter per contract, by technology
│           ├── api/              # FastAPI controllers, OAuth and the MCP edge
│           └── main/             # the composition root
├── apps/
│   ├── gateway/              # thin entrypoint + Dockerfile
│   └── web/                  # Nuxt 4 admin UI + its Dockerfile
├── deploy/
│   ├── docker-compose.yml    # gateway, web, Postgres, Valkey, dev IdP
│   └── ...
└── openspec/                 # these specifications
```

#### Related documentation

Architecture rationale, views, and decision records live in `docs/arc42/`, `docs/adr/`, and `docs/likec4/` per
[documentation](../documentation/spec.md); this spec stays the normative source for the
requirements above.

#### Resolved questions

- *Whether SQLModel needs a thin escape hatch to raw SQLAlchemy for advanced queries.* Answered by
  [ADR-0034](../../../docs/adr/0034-pydantic-entities-and-row-classes.md): the row classes in
  `infrastructure/postgres/rows/` **are** that hatch. They are SQLAlchemy models, so any query SQLAlchemy supports is
  available without the domain layer knowing. The residual cost — duplicated field lists — is recorded as accepted debt
  in [arc42 §11](../../../docs/arc42/11-risks-and-technical-debt.md).

### Domain model

Prior art: `../metamcp/apps/backend/src/db/schema.ts`.

#### Entities

The field lists below describe the row classes in `infrastructure/postgres/rows/`; the Pydantic entities in `domain/`
carry the same fields.

- **McpServer** ([upstreams](../upstreams/spec.md)): `id`, `name` (unique, slug-safe, no `__`; the tool
  prefix), `description`, `url` (Streamable HTTP endpoint), `static_headers` (json, write-only secrets),
  `forward_headers` (json, [auth](../auth/spec.md)), `auth_mode` (`none` |
  `static_headers` | `upstream_oauth` | `delegated_token`), `identity_mode`, `send_identity_header`, `capabilities`
  (json snapshot captured at discovery, [UPS-22](../upstreams/spec.md)), `protocol_mode` (`auto` | `legacy` |
  pinned revision) and `protocol_version` ([UPS-10](../upstreams/spec.md)), `health_status` + `last_error`,
  `connection_state` ([UPS-12](../upstreams/spec.md)), `last_discovered_at` (last successful discovery),
  `created_at`, `updated_at`.
- **Tool** ([upstreams](../upstreams/spec.md)): discovered tool cache. `id`, `server_id` FK, `name`,
  `title`, `description`, `input_schema` (json), `annotations` (json), `schema_hash`, `stale_since` (set when a
  successful discovery stops listing the tool, [UPS-19](../upstreams/spec.md)). Unique `(server_id, name)`.
- **Bundle** ([bundles](../bundles/spec.md)): `id`, `name` (unique, slug-safe), `description` (served as MCP
  `instructions`), `overview` (catalogue text, [BND-11](../bundles/spec.md)), timestamps.
- **BundleServer**: M:N bundle↔server. `bundle_id`, `server_id`, `enabled`, `position` (member order,
  [BND-1](../bundles/spec.md)). Unique `(bundle_id, server_id)`.
- **BundleTool** ([bundles](../bundles/spec.md)): per-bundle tool state. `bundle_id`, `tool_id`,
  `enabled`, `override_name`, `override_title`, `override_description`, `override_annotations` (json). Unique
  `(bundle_id, tool_id)`. Rows exist only where state deviates from the default (enabled, no overrides).
- **BundlePrompt / BundleResource** ([bundles](../bundles/spec.md)): content authored
  on a bundle. `BundlePrompt`: `bundle_id`, `name`, `title`, `description`, `arguments` (json), `messages` (json),
  timestamps; unique `(bundle_id, name)`. `BundleResource`: `bundle_id`, `name`, `title`, `description`, `mime_type`,
  `size_bytes` (derived from `content`, stored so a listing never reads the content), `content` (text), timestamps;
  unique `(bundle_id, name)`. Both cascade with their bundle (ARC-17) and are config-class entities (ARC-20).
- **Endpoint** ([endpoints](../endpoints/spec.md)): `id`, `name` (globally unique, slug-safe, appears in the public
  URL), `bundle_id` FK (many endpoints may point at one bundle), `profile` (`default` | `oauth_only` | `write_as_read`,
  [endpoints](../endpoints/spec.md)), `auth_modes` (json subset of `oauth`, `api_key`, `none`),
  `rate_limit` (json, [endpoints](../endpoints/spec.md)), `enabled`, timestamps.
- **User** ([auth](../auth/spec.md), [auth](../auth/spec.md)): provisioned on first OIDC
  login. `id`, `oidc_issuer`, `oidc_sub` (unique together), `email`, `display_name`, `is_admin`, `is_active`,
  `created_at`. The `id` is the `sub` reported by token introspection, stable within one gateway database. The IdP
  subject (`oidc_issuer`, `oidc_sub`) is stable beyond it — across a database rebuild or restore, and for users who
  exist in the IdP but have not yet signed in through the gateway — so it is exposed alongside `sub`, never instead of
  it: to the metering hook ([PROT-24](../protocol/spec.md)), in introspection ([AUTH-5](../auth/spec.md)), and
  optionally as `X-MCP-User` ([AUTH-29](../auth/spec.md)).
- **OAuthClient / OAuthAuthorizationCode / OAuthAccessToken** ([auth](../auth/spec.md)): the gateway's
  own OAuth 2.1 server state (dynamically registered clients, single-use PKCE codes, opaque access tokens with rotating
  refresh tokens). Token values stored **hashed**. Codes and tokens carry an `endpoint_id` **audience**
  ([AUTH-10](../auth/spec.md)).
- **OAuthConsent**: `user_id`, `client_id`, `endpoint_id`, `granted_at`, `revoked_at` (nullable).
- **ApiKey** ([auth](../auth/spec.md)): `id`, `name`, `key_hash` (+ `key_prefix` for display), `kind`,
  `endpoint_ids` (json scope, empty = all), `is_active`, `last_used_at`, `created_at`.
- **UpstreamOAuthClient / UpstreamOAuthToken** ([upstreams](../upstreams/spec.md)): client registration per
  upstream server (secret encrypted), and tokens stored encrypted per `(server_id, user_id)` — `user_id` nullable for
  the shared/service connection.
- **AuditRecord** ([operations](../operations/spec.md)): append-only per-tool-call record: `endpoint_id` (nullable FK)
  and the denormalized endpoint/bundle/server/tool names, caller (`user_id` or `api_key_id`, `auth_method`), `status`,
  `denied_reason`, `duration_ms`, `error_message`, `session_id`, `created_at`.
- **Config** (`config_entries`): key/value runtime settings editable in the UI. Env vars (`BUNDLEMCP_*` via
  pydantic-settings) cover deploy-time settings; `Config` covers runtime-tunable ones.

#### Relationships

```
McpServer 1──n Tool
McpServer n──m Bundle          (BundleServer: enabled)
Tool      n──m Bundle          (BundleTool: enabled + overrides)
Bundle    1──n Endpoint        (profile, auth_modes, rate_limit)
Bundle    1──n BundlePrompt / BundleResource
User      1──n OAuthAccessToken / UpstreamOAuthToken
Endpoint  1──n AuditRecord (denormalized names retained after deletes)
```

#### Resolved questions

- Encryption mechanism for upstream tokens at rest: app-level Fernet via MultiFernet
  ([ADR-0017](../../../docs/adr/0017-upstream-oauth-encryption.md)); key provisioning/rotation per
  [DEP-9](../deployment/spec.md).
