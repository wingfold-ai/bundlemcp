# 3. Context and Scope

Rendered from the LikeC4 view `index` in [`../likec4/model.c4`](../likec4/model.c4) (render with `npx likec4` or the VS
Code extension):

```likec4-view
view: index — "bundlemcp — System Context"
```

## Business context

| Partner | Interaction |
|---|---|
| **Administrator** | Manages servers/bundles/endpoints via the admin web app |
| **MCP clients** (claude.ai, ChatGPT, scripts) | Call `/{endpoint}/mcp`; authenticate via OAuth 2.1 (DCR + PKCE + consent) or API key ([endpoints spec](../../openspec/specs/endpoints/spec.md), [auth spec](../../openspec/specs/auth/spec.md)) |
| **Upstream MCP servers** | Aggregated over Streamable HTTP; receive forwarded identity (`X-MCP-User`, selected headers); may verify bearers via `/oauth/introspect` ([auth spec](../../openspec/specs/auth/spec.md)) |
| **OIDC IdP** (Keycloak, dex, …) | Authenticates all humans; bundlemcp federates, never stores passwords ([auth spec](../../openspec/specs/auth/spec.md)) |
| **Application layer** (optional) | Registers servers via `PUT /api/v1/servers/{name}`; meters tool calls via the metering hook ([management spec](../../openspec/specs/management/spec.md), [protocol spec](../../openspec/specs/protocol/spec.md)) |

## Technical context

All external interfaces are HTTPS (TLS at the operator's reverse proxy,
[DEP-1/2](../../openspec/specs/deployment/spec.md)): MCP Streamable HTTP on `/{endpoint}/mcp`, OAuth/`.well-known`
routes, REST `/api/v1`, probes `/healthz` and `/readyz`, and Prometheus metrics on `/metrics`
([ARC-11](../../openspec/specs/architecture/spec.md)).

## Out of scope

Billing, identity provision, container discovery, storefront — application layer
([the overview in openspec/README.md](../../openspec/README.md) boundary table); dropped metamcp features per the
[decision log](../../openspec/README.md).
