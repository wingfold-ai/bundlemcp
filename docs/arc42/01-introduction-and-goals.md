# 1. Introduction and Goals

bundlemcp is a self-hostable **MCP bundling gateway**: it registers upstream
MCP servers, composes them into **bundles**, and exposes each bundle through
one or more **endpoints** shaped for the consuming client. Full vision:
[spec/00-overview](../../spec/00-overview.md).

## Requirements overview

- Bundle Streamable-HTTP MCP servers; serve bundles over Streamable HTTP with
  full protocol fidelity (progress, cancellation, sampling/elicitation relay).
- Per-client endpoint shaping: claude.ai OAuth profile, ChatGPT re-annotation
  profile, API-key access — one bundle, many surfaces.
- Everything manageable via UI **and** an equivalent service-authenticated
  REST API.
- Consumable by an application layer (application-layer: billing via metering hook,
  registrar via management API) yet fully usable standalone with any OIDC IdP.

## Quality goals (top 3)

| # | Quality | Statement |
|---|---|---|
| 1 | **Resilience** | Restarts are non-events: sessions survive gateway restarts; no `404 Session not found` storms (the metamcp failure this project exists to fix). |
| 2 | **Scalability** | Any replica serves any session — no sticky sessions, no process-local state a request depends on ([ARC-9](../../spec/01-architecture.md)). |
| 3 | **Integrability** | Clean contracts for the application layer: management API, metering hook, token introspection ([spec/40](../../spec/40-management-api.md), [spec/31](../../spec/31-middleware.md)). |

Full quality tree: [§10](10-quality-requirements.md).

## Stakeholders

| Stakeholder | Expectation |
|---|---|
| Operator/admin (the maintainer) | Stable self-hosted gateway in a familiar stack (Python/Nuxt) |
| application-layer (application layer) | Registration API, metering hook, introspectable identity |
| MCP clients (claude.ai, ChatGPT, scripts) | Standards-compliant OAuth/API-key access, working long calls |
| Upstream server authors | Faithful proxying; forwarded identity (`X-MCP-User`, headers) |
