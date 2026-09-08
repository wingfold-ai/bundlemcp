# Core concepts

Five objects describe everything the gateway does: servers, tools, bundles,
endpoints and API keys. Users and OAuth clients arrive on their own once an
endpoint is in use.

## Servers

A server is an upstream MCP server the gateway talks to over **Streamable
HTTP**. It has:

| Field | Meaning |
|---|---|
| `name` | Unique, slug-safe (`[a-zA-Z0-9_-]`, never `__`). It doubles as the prefix of every tool the server contributes. |
| `url` | The server's Streamable HTTP URL, for example `http://weather:8080/mcp`. |
| `auth_mode` | How the gateway authenticates to the server: `none`, `static_headers` (a fixed credential), or `upstream_oauth` (the gateway holds OAuth tokens for the server). |
| `static_headers` | Headers sent on every upstream request. Values are write-only: the API returns only their names. |
| `forward_headers` | Client request headers passed through to the server, mapped incoming name to upstream name. |
| `send_identity_header` | Whether the caller's identity is injected as `X-MCP-User`. On by default. |
| `identity_mode` | For upstream OAuth: `shared` (one connection for everyone) or `per_user` (each caller connects their own account). |
| `protocol_mode` | How the MCP revision is negotiated: `auto`, `legacy`, or a pinned revision date. |

On create and on every update the gateway **probes** the server, negotiates
the protocol, runs `tools/list` and stores the discovered tools. A failed
probe never blocks registration: the server is stored with
`health_status: error` and its last error, so you can register a server that
is not running yet.

## Tools and the tool cache

Discovered tools are cached in Postgres with their name, title, description,
input schema and annotations. The cache lets you curate bundles while a server
is down, and lets an endpoint keep answering `tools/list` when an upstream is
unreachable.

Tools that disappear from a server are not deleted. They stop being served and
their `last_seen_at` stops moving, so the UI can flag them as stale while their
curation survives a temporary outage.

## Bundles

A bundle is an ordered set of member servers presented as **one virtual MCP
server**. Its `description` is served as the MCP `instructions` field.

Every tool is exposed as `<server_name>__<tool_name>`. The double underscore
is reserved: server names cannot contain it, so the gateway splits a presented
name on the first `__` and always finds the owning server.

Per bundle, each tool can be:

- **disabled**, which removes it from `tools/list` and rejects calls;
- given an **override** for its name, title, description or annotations.

A whole membership can also be disabled, hiding all of that server's tools
without losing the per-tool curation. Curation is per bundle: the same server
can look different in two bundles.

Prompts and resources of member servers pass through uncurated: prompts are
prefixed like tools, resource URIs are passed unchanged.

## Endpoints

An endpoint is the public face of a bundle at
`<public url>/<endpoint_name>/mcp`. A bundle may have any number of endpoints.
Each one sets:

| Field | Meaning |
|---|---|
| `bundle_name` | The bundle it serves. |
| `auth_modes` | Which credentials are accepted: `oauth`, `api_key`, or `none`. A request succeeds if it satisfies any listed mode. `none` is only valid alone and needs `allow_unauthenticated: true`. |
| `profile` | `default`, `claude` or `chatgpt`. See below. |
| `rate_limit` | Optional endpoint-wide and per-client limits. |
| `enabled` | A disabled endpoint answers 404 without losing its configuration. |

Endpoint names cannot be `api`, `oauth`, `.well-known`, `healthz`, `readyz`,
`metrics`, `docs`, `login`, `consent` or `static`, since those are the
gateway's own paths.

### Profiles

A profile adapts a bundle to the quirks of one kind of client:

| Profile | Allowed `auth_modes` | What it does |
|---|---|---|
| `default` | any | Passthrough. |
| `claude` | exactly `[oauth]` | Passthrough tools, guarantees the OAuth discovery surface claude.ai needs. |
| `chatgpt` | must include `oauth` or `api_key` | Re-annotates every tool as read-only (`readOnlyHint: true`, `destructiveHint: false`) so ChatGPT accepts write tools. The tools still perform their real operations upstream. |

Profiles are built in. The management API lists them together with any
warning an operator should read before choosing one.

## Identity

Every request through an endpoint resolves a **caller identity**:

- an OAuth bearer resolves to the user's id (`sub`);
- an API key resolves to `api_key:<key id>`;
- on a `none` endpoint the caller is anonymous.

When both an OAuth bearer and an API key are present, OAuth wins. The resolved
identity is what rate limiting, audit records, the metering hook and identity
forwarding all use.

Two things carry identity to upstream servers:

- `X-MCP-User: <sub>`, injected when `send_identity_header` is on. Any
  client-supplied value is stripped first, so it cannot be spoofed.
- `forward_headers`, typically `authorization → authorization`, so an upstream
  can verify the bearer itself by calling the gateway's introspection route.

## Authentication surfaces

The gateway has three distinct authentication mechanisms, and it helps to keep
them apart:

| Who | Mechanism |
|---|---|
| **Humans** signing in to the admin UI or authorising a connector | Federated OIDC login against your identity provider. bundlemcp stores no passwords. Admins are the users whose email is in `BUNDLEMCP_ADMIN_EMAILS`. |
| **MCP clients** such as claude.ai | The gateway's built-in OAuth 2.1 server: dynamic client registration or client ID metadata documents, PKCE, consent, opaque tokens bound to one endpoint. |
| **Scripts and services** | API keys: `endpoint` keys call MCP endpoints, `service` keys also call the management API. |

The gateway may itself be an OAuth **client** toward an upstream server that
is OAuth-protected. That is upstream OAuth, covered in
[Servers](/manage/servers#upstream-oauth).

## State model

Two stores, with a strict split:

- **Postgres** holds everything durable: servers, bundles, endpoints, API
  keys, users, OAuth clients and tokens, upstream tokens, the audit log.
- **Valkey** holds everything live: handshake-era session records, rate-limit
  counters, single-use OAuth state, and the signal bus that tells other
  replicas about configuration changes.

No request depends on process memory, so any replica serves any session and
a restart or a rollout never produces "session not found" errors. Losing
Valkey costs at most the live sessions, and clients simply re-initialise.
