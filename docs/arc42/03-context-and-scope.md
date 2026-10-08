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
| **MCP clients** (claude.ai, ChatGPT, scripts) | Call `/{endpoint}/mcp`; authenticate via OAuth 2.1 (DCR + PKCE + consent) or API key ([spec/14](../../spec/14-endpoints.md), [spec/20](../../spec/20-oauth-server.md)) |
| **Upstream MCP servers** | Aggregated over Streamable HTTP; receive forwarded identity (`X-MCP-User`, selected headers); may verify bearers via `/oauth/introspect` ([spec/24](../../spec/24-identity-forwarding.md)) |
| **OIDC IdP** (Keycloak, dex, …) | Authenticates all humans; bundlemcp federates, never stores passwords ([spec/21](../../spec/21-admin-auth.md)) |
| **Application layer** (optional) | Registers servers via `PUT /api/v1/servers/{name}`; meters tool calls via the metering hook ([spec/40](../../spec/40-management-api.md), [spec/31](../../spec/31-middleware.md)) |

## Technical context

All external interfaces are HTTPS (TLS at the operator's reverse proxy, [DEP-1/2](../../spec/71-deployment.md)): MCP
Streamable HTTP on `/{endpoint}/mcp`, OAuth/`.well-known` routes, REST `/api/v1`, and probes `/healthz` and `/readyz`
([ARC-11](../../spec/01-architecture.md)); the `/metrics` route ARC-11 reserves is not built yet (§11).

## Out of scope

Billing, identity provision, container discovery, storefront — application layer ([spec/00](../../spec/00-overview.md)
boundary table); dropped metamcp features per the [decision log](../../spec/README.md).
