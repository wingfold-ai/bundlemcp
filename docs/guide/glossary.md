# Glossary

The vocabulary the rest of these pages assumes.

## The four things you configure

| Term | Meaning |
|---|---|
| **Upstream server** (or **upstream**) | An MCP server you registered, addressed by a unique name, that bundlemcp forwards calls to. bundlemcp is a client of it. *Upstream* is the short form used interchangeably in these pages, and the one the management API uses in its paths (`/api/v1/upstreams`). See [Upstream servers](/manage/servers). |
| **Bundle** | Several upstream servers composed into one virtual MCP server, with per-bundle tool curation. metamcp called this a *namespace*. See [Bundles](/manage/bundles). |
| **Endpoint** | A public URL, `/{name}/mcp`, serving one bundle with its own auth modes, profile and rate limits. One bundle can have several. See [Endpoints](/manage/endpoints). |
| **Profile** | A per-endpoint preset shaping the auth and tool surface: `default`, `oauth_only` or `write_as_read`, each named for what it changes. See [Endpoints](/manage/endpoints). |

## Tools

| Term | Meaning |
|---|---|
| **Presented tool** | A tool as a client sees it on an endpoint, after curation, overrides and the profile transform. |
| **Presented name** | The name the client calls, `server__tool` by default. The `__` separator is what lets the gateway route a call back to the right upstream. |
| **Override** | A per-bundle change to a tool's presented name, description or annotations. Applied after the profile, so it always wins. |
| **Curation** | Choosing which of a server's tools a bundle exposes. A tool disabled in the bundle does not exist for that bundle's clients. |
| **Bundle prompt / bundle resource** | A prompt or document written on the bundle itself rather than offered by a member: context for the bundle's purpose, served by the gateway without contacting an upstream. A bundle prompt's name has no server prefix; a bundle resource is read as `bundle://resources/<name>`. See [Bundles](/manage/bundles#bundle-prompts-and-documents). |
| **Catalogue** | What a signed-in non-administrator sees: the bundles they could connect a client to, and nothing else. |

## Identity and access

| Term | Meaning |
|---|---|
| **Administrator** | A signed-in user whose verified email is in `BUNDLEMCP_ADMIN_EMAILS`, or whose ID token carries the admin claim, re-evaluated at every login. Configures everything. |
| **User** | Any other signed-in person. Sees the catalogue, authorises connectors, connects their own upstream accounts. |
| **Caller identity** | Who the gateway resolved a request to: a user id, `api_key:<id>`, or nothing on an open endpoint. It is what audit records, the metering hook and `X-MCP-User` all report. |
| **Service key** | An API key that manages the gateway through `/api/v1`. |
| **Endpoint key** | An API key scoped to specific endpoints, for calling them. It cannot manage anything. |
| **Upstream identity** | Which account a call to an upstream server uses: one `shared` connection for everyone, or `per_user`, where each person connects their own. See [Identity for upstream servers](/integrate/upstream-identity). |
| **Connect link** | The URL a user follows to attach their own account on a `per_user` server. |
| **`X-MCP-User`** | A header the gateway adds to upstream calls carrying the caller identity. A plain header, not a signed assertion. |
| **Consent** | A user's standing permission for one OAuth client to use one endpoint. |

## Protocol

| Term | Meaning |
|---|---|
| **Streamable HTTP** | The MCP transport bundlemcp speaks, in both directions: `POST` for messages, `GET` for a server-to-client event stream. The only transport; there is no stdio or SSE. |
| **Protocol era** | Which family of MCP revisions a client speaks. **Stateless** (2026-07-28) repeats its context in every request and needs no session; **session** (2025-03-26 to 2025-11-25) opens with `initialize` and holds one. One endpoint URL serves both. See [Request envelope](/integrate/http-surface#request-envelope). |
| **Session** | A client's conversation with the gateway, stored as a record in Valkey rather than in a process, so any replica can serve it and a restart does not end it. Session era only. |
| **Request envelope** | The `params._meta` block and mirrored headers a stateless-era request carries in place of a session. |
| **DCR** | Dynamic Client Registration (RFC 7591): an OAuth client registers itself, which is how claude.ai connects without you pre-registering it. |
| **Resource indicator** | The RFC 8707 `resource` parameter that binds an access token to one endpoint, so a token minted for one cannot be replayed at another. |
| **Introspection** | `POST /oauth/introspect` (RFC 7662): an upstream or application layer resolves a bearer token to a caller and an audience. |

## Operating it

| Term | Meaning |
|---|---|
| **Bootstrap file** | A declarative YAML or JSON document applied at every startup, so a deployment can be provisioned without clicking. Authoritative for the fields it names. See [Bootstrap file](/self-hosting/bootstrap). |
| **Runtime setting** | Configuration changeable while running, stored in Postgres, as opposed to an environment variable that needs a restart. See [Configuration](/self-hosting/configuration). |
| **Egress policy** | The allow/deny rules on every outbound HTTP request the gateway makes, which is what stops a registered URL reaching cloud metadata or loopback. |
| **Metering hook** | The Python extension point called around every tool call, where an application layer plugs in billing or quotas. See [Metering hook](/integrate/metering-hook). |
| **Application layer** | A separate system built on top of bundlemcp that adds its own identity provider, billing, registrar or storefront. bundlemcp is designed to be consumed by one, and works without one. |
| **Workspace** | The single shared configuration scope. One instance is one workspace; there is no multi-tenancy. |

Contributors will also want the implementation vocabulary — contracts, unit of
work, dialects, the admission gate — which lives in the architecture glossary in
the repository (`docs/arc42/12-glossary.md`).
