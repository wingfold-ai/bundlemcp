# bundlemcp — Specifications

bundlemcp is a self-hostable **MCP bundling gateway**: register upstream MCP servers, compose them into **bundles**, and
expose each bundle through one or more **endpoints** tailored to the consuming client (claude.ai, ChatGPT, plain API
clients). It is a focused Python/Nuxt rewrite of the bundling core of [metamcp](https://github.com/metatool-ai/metamcp),
designed from day one for restart-safe sessions and horizontal scaling, and built to be consumed by an application layer
that adds its own identity provider, billing, and discovery on top.

The specifications are kept with [OpenSpec](https://github.com/Fission-AI/OpenSpec) (`spec-driven` schema).

## How the specs are organised

| Where | What it holds |
|---|---|
| `specs/<capability>/spec.md` | What the system does **today**. One capability per folder; every requirement is implemented. |
| `changes/<change>/` | A change not yet implemented: `proposal.md` (why), `specs/` (the requirement deltas), `design.md` (how, when it is not obvious), `tasks.md` (the checklist). |
| `changes/archive/` | Changes that were implemented and merged into `specs/`. |
| `config.yaml` | Project context and per-artifact rules every OpenSpec workflow reads. |
| `slices.json` | The registry of slices and their requirement codes ([Slices and codes](#slices-and-codes)). |
| `requirements-baseline.json` | Frozen dates for the requirements that predate OpenSpec; later dates come from `changes/archive/`. |

Requirements are written `### Requirement: <code>-<n> <Short name>`, with at least one `#### Scenario:`. The code
(`UPS-1`, `EP-3`, …) is stable: tests cite it in their names and docstrings, and it is never reused. See [Slices and
codes](#slices-and-codes).

## Making a change

Every new behaviour starts as a change proposal, not as code:

1. **Propose:** `/opsx:propose <idea>` (or `openspec new change <name>`) creates `openspec/changes/<name>/` with the
   proposal, the delta specs, the design and the tasks. Read the decision log below first.
2. **Review** the proposal in its pull request, like code.
3. **Apply:** `/opsx:apply <name>` works through `tasks.md`; tests cite the requirement IDs.
4. **Archive:** `/opsx:archive <name>` once it is merged and done. The deltas move into `specs/`, and the change folder
   into `changes/archive/`.

`openspec list` shows the open changes, `openspec list --specs` the capabilities, and
`openspec validate --all --strict` must pass (CI runs it).

## Vision

bundlemcp does one thing well: **bundle MCP servers and expose the bundles the way each consuming client needs them.**

```text
upstream MCP servers ──▶ [ upstream registry ] ──▶ [ bundle ] ──▶ [ endpoint(s) ]
 (Streamable HTTP)          connection +            tool            per-client
                            tool discovery          curation        surface:
                                                                    auth mode,
                                                                    profile,
                                                                    rate limits
```

A **bundle** aggregates the tools of several upstream servers into one virtual MCP server. An **endpoint** is a public
URL serving that bundle over Streamable HTTP. One bundle can have **many endpoints**, each shaped for its consumer:

- a claude.ai endpoint that requires OAuth 2.1 (dynamic client registration + PKCE),
- a ChatGPT endpoint that re-annotates write tools as read-safe so ChatGPT accepts them,
- an internal endpoint authenticated by API key for scripts and automations.

### Why a rewrite (and not a fork)

metamcp proved the product shape but is barely maintained and has an architectural flaw that caused repeated production
pain: **all live state — connection pools, transports, rate-limit counters — lives in the memory of a single Node
process.** A restart drops every session (`404 Session not found` storms); a second replica is impossible; the fork
accumulated an entire recovery subsystem just to mitigate it.

bundlemcp inverts that: durable configuration in Postgres, live session state in Valkey, **no in-memory-only state that
a request depends on**. Any replica serves any session; restarts are non-events (see
[sessions](specs/sessions/spec.md)).

The rewrite also switches to the maintainer's home stack — Python (FastAPI + FastMCP, Pydantic everywhere) and Nuxt 4 —
and strips features that do not serve the bundling mission (see the decision log below).

### Scope boundary: bundlemcp vs. the application layer

bundlemcp is the **reusable building block**; the application layer is an **application** of it (a commercial
multi-tenant MCP platform). bundlemcp must be fully usable standalone — with any OIDC provider and no billing — while
exposing the exact contact points such an application needs.

| Concern | bundlemcp (this project) | Application layer |
|---|---|---|
| MCP aggregation, bundles, endpoints | ✔ owns | consumes |
| OAuth 2.1 server toward MCP clients (+ token introspection) | ✔ owns | consumes `sub` for billing |
| Admin authentication | federates to **an external OIDC IdP** | ships and operates Keycloak |
| Upstream registration | ✔ management REST API | registrar (Docker-label discovery) calls it |
| Tool-call interception | ✔ middleware chain + documented metering hook | plugs check-and-debit / refund into the hook |
| Identity propagation to upstreams | ✔ header forwarding + `X-MCP-User` | upstream servers rely on it |
| Billing, credits, Stripe, pricing | ✖ never | ✔ owns |
| Identity provider itself | ✖ required but external | ✔ owns (Keycloak realms) |
| Container discovery | ✖ | ✔ owns (label contract) |
| Storefront | ✖ | ✔ owns |

The two integration warts this boundary explicitly fixes:

1. metamcp had **no service-authenticated registration API** — the first consumer's registrar had to replay login
   cookies against internal tRPC. bundlemcp ships a first-class REST API
   ([management](specs/management/spec.md)).
2. metamcp's metering middleware was a code comment. bundlemcp specifies the hook as a supported contract
   ([protocol](specs/protocol/spec.md)) matching the first consumer's `check-and-debit` / `refund` API.

### Goals

1. Bundle Streamable-HTTP MCP servers and serve bundles over Streamable HTTP.
2. Per-client endpoint shaping (auth mode, tool re-annotation, rate limits).
3. Survive restarts and scale horizontally without losing sessions.
4. Everything manageable via UI **and** an equivalent authenticated REST API.
5. Pydantic-typed end to end: DB model → API DTO → generated TS types in the UI.
6. Deployable as a small Docker Compose stack: gateway, web, Postgres, Valkey (+ any OIDC IdP).

### Non-goals

- Being an MCP server marketplace, an IdP, or a billing system.
- Supporting every MCP transport ever shipped (Streamable HTTP only).
- Multi-tenancy inside bundlemcp (single shared admin workspace).

## Slices and codes

Every capability is a **slice** with its own requirement-code prefix: requirements are coded `<code>-<n>` (`BND-5`,
`SES-11`), numbered in order and never renumbered. The registry is [`slices.json`](slices.json), which
`openspec/config.yaml` points every OpenSpec workflow at, and `tools/check_spec_ids.py` enforces it in CI. The docs
site's [Requirements](../docs/reference/requirements.md) page lists every requirement in full, grouped and filterable
by slice, with its status and dates.

| Code | Slice | In one line |
|---|---|---|
| `ARC` | [Architecture](#arc--architecture) | How the system is built and what it stores. |
| `DOC` | [Documentation](#doc--documentation) | What people read to run, use and change bundlemcp. |
| `UPS` | [Upstreams](#ups--upstreams) | The upstream MCP servers the gateway proxies, and how it reaches them. |
| `BND` | [Bundles](#bnd--bundles) | Composing upstreams into one virtual MCP server, and curating what it presents. |
| `EP` | [Endpoints](#ep--endpoints) | The public URLs that serve a bundle, each shaped for one kind of client. |
| `AUTH` | [Authentication and identity](#auth--auth) | Who may call the gateway, and who the upstreams learn the caller is. |
| `SES` | [Sessions](#ses--sessions) | Live state that any replica can serve, and keeping every replica's view current. |
| `PROT` | [Protocol](#prot--protocol) | The MCP surface the gateway speaks to clients and upstreams. |
| `MGMT` | [Management](#mgmt--management) | Configuring the gateway without clicking. |
| `OPS` | [Operations](#ops--operations) | What operators see while the gateway runs. |
| `UI` | [Admin UI](#ui--admin-ui) | The admin app, and the catalogue signed-in users see. |
| `SEC` | [Security](#sec--security) | The threat model and the controls the other slices rely on. |
| `DEP` | [Deployment](#dep--deployment) | Running bundlemcp in production and upgrading it safely. |

### Foundation

#### `ARC` — architecture

**How the system is built and what it stores.** The two-container shape of bundlemcp (a Python gateway serving MCP
endpoints, OAuth and the management API, and an optional Nuxt admin app), the stack and version policy, and the state
model behind the restart-safety promise: Postgres for everything durable, a RESP store (Valkey) for everything live, and
no in-memory-only state a request depends on. It also defines the persisted entities, their naming rules, cascades and
secret-bearing columns, and the package layout with its layer rules.

*Not here:* Behaviour that clients observe lives in the feature slices; this slice holds the structural rules they all
rely on.

Spec: [`specs/architecture/spec.md`](specs/architecture/spec.md). Merged from: Architecture, Domain model.

#### `DOC` — documentation

**What people read to run, use and change bundlemcp.** The user-facing documentation site (self-hosting, managing,
connecting clients, integrating), the repository README and the demo seed that makes a fresh install useful. It also
owns the architecture documentation: arc42 sections, append-only ADRs, the LikeC4 model as the single source of
diagrams, and the rule that docs and decisions land in the same pull request as the behaviour they describe.

*Not here:* What the gateway does is specified in the other slices; this slice specifies how it is documented and where.

Spec: [`specs/documentation/spec.md`](specs/documentation/spec.md). Merged from: Docs and onboarding, Architecture
documentation.

### Bundling core

#### `UPS` — upstreams

**The upstream MCP servers the gateway proxies, and how it reaches them.** Registering an upstream server (Streamable
HTTP only, with inspection that pre-fills a registration), its connection settings and health, the egress policy every
request to it passes, and discovering and caching its tools in Postgres so bundles can be curated while it is down. It
also covers authenticating to upstreams: static headers, OAuth with tokens held per user or shared, the interactive
connect flow, refresh on 401, and introspection for forwarded bearers.

*Not here:* How an upstream's tools are presented in a bundle is the bundles slice; the caller's identity forwarded to
an upstream is the auth slice.

Spec: [`specs/upstreams/spec.md`](specs/upstreams/spec.md). Merged from: Upstream registry, Tool discovery, Upstream
OAuth.

#### `BND` — bundles

**Composing upstreams into one virtual MCP server, and curating what it presents.** A bundle combines several upstreams
under one set of prefixed, collision-free tool names and routes each call back to its owner. Per bundle, an admin
decides which tools are shown and how: enable flags, name, title, description and annotation overrides. A bundle can
also carry prompts and resources of its own, written by an admin and served without contacting any upstream, beside the
members' prompts and resources, which pass through live. The catalogue overview a user reads before connecting belongs
here too.

*Not here:* Where a bundle is reachable, by whom and with which client quirks is the endpoints slice.

Spec: [`specs/bundles/spec.md`](specs/bundles/spec.md). Merged from: Bundles, Tool curation, Bundle prompts and
resources.

#### `EP` — endpoints

**The public URLs that serve a bundle, each shaped for one kind of client.** One bundle can have many endpoints, each
with its own URL, accepted authentication modes (OAuth, API key, none), profile and rate limits. Profiles adapt the tool
surface to a client's quirks: claude, chatgpt (which re-annotates write tools so ChatGPT accepts them) and default. Rate
limits hold across all replicas through shared counters, answer 429 with Retry-After, and include the limiter on
authentication failures.

*Not here:* How a credential is issued and validated is the auth slice; what the endpoint serves is the bundles and
protocol slices.

Spec: [`specs/endpoints/spec.md`](specs/endpoints/spec.md). Merged from: Endpoints, Endpoint profiles, Rate limiting.

### Authentication and identity

#### `AUTH` — auth

**Who may call the gateway, and who the upstreams learn the caller is.** The built-in OAuth 2.1 authorization server for
MCP clients (discovery, dynamic and metadata-document client registration, PKCE, consent, endpoint-bound tokens,
introspection and revocation), OIDC-only login for admins and users with roles taken from the identity provider, API
keys for scripts and services, and identity forwarding: selected client headers, the X-MCP-User header and delegated
tokens that tell an upstream who is calling.

*Not here:* Authenticating the gateway to an upstream with the upstream's own OAuth is the upstreams slice.

Spec: [`specs/auth/spec.md`](specs/auth/spec.md). Merged from: OAuth server, Admin authentication, API keys, Identity
forwarding.

### Runtime and platform

#### `SES` — sessions

**Live state that any replica can serve, and keeping every replica's view current.** Handshake-era MCP sessions are
records in the RESP store, so any replica serves them and a restart loses nothing; modern-era requests are stateless.
Live streams are pinned to the replica holding them, and messages reach them from any replica over pub/sub. The
degradation matrix says what happens when the RESP store or Postgres is down. Configuration changes publish invalidation
events, so caches on every replica are flushed within a two-second budget.

*Not here:* The MCP messages carried over a session are the protocol slice.

Spec: [`specs/sessions/spec.md`](specs/sessions/spec.md). Merged from: Session management, State propagation.

#### `PROT` — protocol

**The MCP surface the gateway speaks to clients and upstreams.** bundlemcp is a bidirectional proxy, not a tools-only
router: it relays progress, cancellation, logging, completions, list-changed notifications and the upstream's requests
for client input, across protocol revisions (the session-based handshake era and the stateless 2026-07-28 era) with one
dialect per revision. Every tool call runs through a fixed pipeline (curation, profile, metering, audit), and the
metering hook is the supported, versioned extension point where an application layer plugs in billing.

*Not here:* Session storage and cross-replica delivery are the sessions slice; what is recorded per call is the
operations slice.

Spec: [`specs/protocol/spec.md`](specs/protocol/spec.md). Merged from: Protocol passthrough, Tool-call pipeline and
metering hook.

#### `MGMT` — management

**Configuring the gateway without clicking.** The versioned management REST API under /api/v1 (the admin UI uses nothing
else, so everything is automatable), authenticated by admin session or service key, with its DTOs, pagination,
retry-safe writes and browser-facing protections. Bootstrap provisions upstreams, bundles and endpoints idempotently
from a document at startup, through the same code paths as the API. Export and import of the whole configuration will
live here once built.

*Not here:* The UI on top of this API is the admin-ui slice.

Spec: [`specs/management/spec.md`](specs/management/spec.md). Merged from: Management API, Bootstrap, Export and import.

### Operations and UI

#### `OPS` — operations

**What operators see while the gateway runs.** The append-only audit log: one record per tool call (who, what, where,
how long, how it ended), denied calls included, never arguments or results, written asynchronously without slowing
calls, queryable through the API and UI, and the reconciliation source for an application layer's billing. Structured
logs and the health and readiness probes for orchestrators. Prometheus metrics, optional tracing, and the live log view
of every replica's recent events.

*Not here:* Rate-limit and lockout counters are specified with their limiters in the endpoints slice.

Spec: [`specs/operations/spec.md`](specs/operations/spec.md). Merged from: Audit log, Observability, Live logs.

#### `UI` — admin-ui

**The admin app, and the catalogue signed-in users see.** A Nuxt single-page app that is a pure client of the management
API, with types generated from its OpenAPI document: pages for upstreams (with guided registration), bundles and
curation, endpoints and their connection cards, API keys, users and consents, audit, live logs and settings, the
built-in inspector, and a catalogue showing a signed-in non-admin what they can connect to.

*Not here:* Every action the UI offers is specified as API behaviour in the management slice and the feature slices.

Spec: [`specs/admin-ui/spec.md`](specs/admin-ui/spec.md). Merged from: Admin UI, Inspector.

### Cross-cutting

#### `SEC` — security

**The threat model and the controls the other slices rely on.** One egress policy for every request the gateway makes to
an admin-supplied or remotely named URL, and its defaults against SSRF (blocked metadata and loopback ranges, allowed
private networks); CORS and CSRF rules for the management API; hardening of the OAuth browser pages; request size
limits; limits against dynamic client registration abuse; lockout after authentication failures; and the rule that
secrets never appear in logs, responses or audit records.

*Not here:* Feature slices reference these controls instead of re-deriving them.

Spec: [`specs/security/spec.md`](specs/security/spec.md). 

#### `DEP` — deployment

**Running bundlemcp in production and upgrading it safely.** The public URL as the single source of the gateway's
identity behind a reverse proxy, trusted proxies and the client IP, the reference topology and health checks, migrations
as a guarded step that stays backward compatible one release back, versioned session records so rolling upgrades work,
backup and restore, rotation of the token encryption keys, and the CI gates and image publishing that deliver it.

*Not here:* Configuration settings themselves are documented per feature; this slice is the operational contract.

Spec: [`specs/deployment/spec.md`](specs/deployment/spec.md). 

Until 2026-10-13 these were 31 smaller slices with their own prefixes (`DISC`, `OAS`, `MID`, …). Those prefixes are
retired and never reused; [`slices.json`](slices.json) maps each code published under them (`DISC-3`) to its code now
(`UPS-19`), and the Requirements page finds a requirement by either. `openspec list` shows every open change.

## Decision log — deliberately dropped from metamcp

These metamcp features were reviewed and **rejected** for bundlemcp. They are recorded here so nobody re-proposes them
without new evidence.

| Dropped | Why |
|---|---|
| **STDIO upstream servers** | Biggest complexity driver in metamcp (process spawning, crash tracking, env plumbing, fat image). Wrap stdio servers in a Streamable-HTTP sidecar instead — pattern documented in [upstreams](specs/upstreams/spec.md). |
| **SSE upstream & downstream transport** | Deprecated by the MCP spec; all targeted upstreams and clients speak Streamable HTTP. |
| **OpenAPI REST bridge** (`/api` per endpoint) | Notable build effort, not needed for the target clients (claude.ai, ChatGPT, MCP-native tools). |
| **Query-parameter API-key auth** | Keys leak into logs/URLs; header auth only. |
| **Multi-user resource ownership** (public/private per user) | bundlemcp is a single shared workspace — every admin sees and manages everything. Tenanting is the application layer's job. |
| **Admin tools over MCP** (~40 `metamcp-admin__*` tools) | The management REST API covers automation; agents can call REST. |
| **i18n** | English-only admin UI. |
| **Local password accounts** (better-auth style) | Admin login is OIDC-only; bundlemcp never stores passwords. |
| **Marketplace/search page** (metamcp's registry-browse UI) | bundlemcp is not a marketplace (non-goal above); upstreams arrive via API/UI/bootstrap. |
| **`/oauth/userinfo` endpoint** | Introspection's `sub` covers all known consumers; no OIDC-provider surface ([auth](specs/auth/spec.md) out of scope). |
| **Opportunistic discovery on live `tools/list`** (metamcp's sync-on-list) | bundlemcp serves an endpoint's `tools/list` from the Postgres cache ([UPS-20](specs/upstreams/spec.md)), so no live upstream `tools/list` happens to piggy-back on. A periodic refresh ([UPS-23](specs/upstreams/spec.md), [ADR-0038](../docs/adr/0038-periodic-tool-refresh.md)) keeps the cache current instead. |

## Roadmap — deferred, not dropped

| Item | Status |
|---|---|
| **metamcp migration importer** — one-shot CLI reading a metamcp Postgres DB and mapping servers→registry, namespaces→bundles (+curation), endpoints→endpoints | Deferred by decision (2026-07). Revisit when bundlemcp reaches feature parity; until then migration is manual/bootstrap-file based. |
| **ChatGPT `search`/`fetch` connector profile** | Possible fourth endpoint profile ([endpoints](specs/endpoints/spec.md) out of scope). |

## Former spec numbers

Until October 2026 the specs were numbered files in `spec/`. Older ADRs, commits and pull requests cite them as
"spec 30" or `spec/30-session-management.md`; this is where each one went. Their requirement codes changed when the
slices were consolidated; `slices.json` maps each old code to its new one.

| Former file | Now |
|---|---|
| `spec/00-overview.md` | [Vision](#vision) in this file |
| `spec/01-architecture.md` | [`architecture`](specs/architecture/spec.md) (`ARC`) |
| `spec/02-domain-model.md` | [`architecture`](specs/architecture/spec.md) (`ARC`) |
| `spec/10-server-registry.md` | [`upstreams`](specs/upstreams/spec.md) (`UPS`) |
| `spec/11-tool-discovery.md` | [`upstreams`](specs/upstreams/spec.md) (`UPS`) |
| `spec/12-bundles.md` | [`bundles`](specs/bundles/spec.md) (`BND`) |
| `spec/13-tool-management.md` | [`bundles`](specs/bundles/spec.md) (`BND`) |
| `spec/14-endpoints.md` | [`endpoints`](specs/endpoints/spec.md) (`EP`) |
| `spec/15-endpoint-profiles.md` | [`endpoints`](specs/endpoints/spec.md) (`EP`) |
| `spec/16-rate-limiting.md` | [`endpoints`](specs/endpoints/spec.md) (`EP`) |
| `spec/17-bundle-prompts-resources.md` | [`bundles`](specs/bundles/spec.md) (`BND`) |
| `spec/20-oauth-server.md` | [`auth`](specs/auth/spec.md) (`AUTH`) |
| `spec/21-admin-auth.md` | [`auth`](specs/auth/spec.md) (`AUTH`) |
| `spec/22-api-keys.md` | [`auth`](specs/auth/spec.md) (`AUTH`) |
| `spec/23-upstream-oauth.md` | [`upstreams`](specs/upstreams/spec.md) (`UPS`) |
| `spec/24-identity-forwarding.md` | [`auth`](specs/auth/spec.md) (`AUTH`) |
| `spec/30-session-management.md` | [`sessions`](specs/sessions/spec.md) (`SES`) |
| `spec/31-middleware.md` | [`protocol`](specs/protocol/spec.md) (`PROT`) |
| `spec/32-protocol-passthrough.md` | [`protocol`](specs/protocol/spec.md) (`PROT`) |
| `spec/33-state-propagation.md` | [`sessions`](specs/sessions/spec.md) (`SES`) |
| `spec/40-management-api.md` | [`management`](specs/management/spec.md) (`MGMT`) |
| `spec/41-bootstrap.md` | [`management`](specs/management/spec.md) (`MGMT`) |
| `spec/42-export-import.md` | [`management`](specs/management/spec.md) (`MGMT`) |
| `spec/50-audit-log.md` | [`operations`](specs/operations/spec.md) (`OPS`) |
| `spec/51-observability.md` | [`operations`](specs/operations/spec.md) (`OPS`) |
| `spec/52-live-logs.md` | [`operations`](specs/operations/spec.md) (`OPS`) |
| `spec/53-inspector.md` | [`admin-ui`](specs/admin-ui/spec.md) (`UI`) |
| `spec/60-admin-ui.md` | [`admin-ui`](specs/admin-ui/spec.md) (`UI`) |
| `spec/61-docs-and-onboarding.md` | [`documentation`](specs/documentation/spec.md) (`DOC`) |
| `spec/62-architecture-documentation.md` | [`documentation`](specs/documentation/spec.md) (`DOC`) |
| `spec/70-security.md` | [`security`](specs/security/spec.md) (`SEC`) |
| `spec/71-deployment.md` | [`deployment`](specs/deployment/spec.md) (`DEP`) |

## Prior art

Specs cite these read-only reference repos (sibling checkouts):

- `../metamcp` — the fork being replaced; schema at `apps/backend/src/db/schema.ts`, gateway at
  `apps/backend/src/lib/metamcp/`, OAuth server at `apps/backend/src/routers/oauth/`.
- The first consumer, a private application layer, is not named in this repo; its registrar client and its metering
  router are the contracts the management-api and protocol specs were written against.
