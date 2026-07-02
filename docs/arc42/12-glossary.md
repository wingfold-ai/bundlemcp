# 12. Glossary

| Term | Definition |
|---|---|
| **MCP** | Model Context Protocol — the protocol between AI clients and tool servers |
| **Streamable HTTP** | Current MCP transport: POST for messages, GET for the server→client event stream, `Mcp-Session-Id` header |
| **Upstream (server)** | A registered external MCP server bundlemcp connects to ([spec/10](../../spec/10-server-registry.md)) |
| **Bundle** | Composition of upstream servers into one virtual MCP server; tools prefixed `server__tool` ([spec/12](../../spec/12-bundles.md)) — metamcp called this a *namespace* |
| **Endpoint** | Public URL `/{name}/mcp` serving one bundle with its own auth modes, profile, and limits ([spec/14](../../spec/14-endpoints.md)) |
| **Profile** | Built-in per-endpoint preset shaping auth + tool surface: `default`, `claude`, `chatgpt` ([spec/15](../../spec/15-endpoint-profiles.md)) |
| **Session** | Client↔gateway MCP session, persisted as a Redis record — "data, not an object" ([spec/30](../../spec/30-session-management.md)) |
| **Binding** | A session's lazy attachment to one upstream session per member server, identity-keyed when credentials are forwarded (SES-6) |
| **Metering hook** | The pre/post tool-call extension point where an application layer plugs billing ([spec/31](../../spec/31-middleware.md)) |
| **DCR** | Dynamic Client Registration, RFC 7591 — clients self-register with the OAuth server |
| **Resource indicator** | RFC 8707 `resource` parameter binding a token to one endpoint (audience) |
| **Introspection** | RFC 7662 `POST /oauth/introspect` — upstreams/app layer resolve a bearer to `sub` + audience |
| **`X-MCP-User`** | Gateway-injected header carrying the resolved caller identity to upstreams ([spec/24](../../spec/24-identity-forwarding.md)) |
| **STP event** | Cross-replica config-invalidation message on Redis pub/sub ([spec/33](../../spec/33-state-propagation.md)) |
| **Application layer** | A system built on bundlemcp (ultra-mcp: Keycloak, billing, registrar, storefront) |
| **ADR** | Architecture Decision Record ([docs/adr](../adr/README.md)) |
| **LikeC4** | Diagram-as-code DSL/toolchain rendering the model in [docs/likec4](../likec4/) |
