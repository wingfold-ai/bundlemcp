# 1. Introduction and Goals

bundlemcp is a self-hostable **MCP bundling gateway**: it registers upstream MCP servers, composes them into
**bundles**, and exposes each bundle through one or more **endpoints** shaped for the consuming client. Full vision:
[overview](../../openspec/README.md).

## Requirements overview

- Bundle Streamable-HTTP MCP servers; serve bundles over Streamable HTTP with full protocol fidelity (progress,
  cancellation, sampling/elicitation relay).
- Per-client endpoint shaping: claude.ai OAuth profile, ChatGPT re-annotation profile, API-key access — one bundle, many
  surfaces.
- Everything manageable via UI **and** an equivalent service-authenticated REST API.

## Quality goals (top 3)

| # | Quality | Statement |
|---|---|---|
| 1 | **Resilience** | Restarts are non-events: sessions survive gateway restarts; no `404 Session not found` storms (the metamcp failure this project exists to fix). |
| 2 | **Scalability** | Any replica serves any session — no sticky sessions, no process-local state a request depends on ([ARC-9](../../openspec/specs/architecture/spec.md)). |
| 3 | **Integrability** | Clean contracts for the application layer: management API, metering hook, token introspection ([management spec](../../openspec/specs/management/spec.md), [protocol spec](../../openspec/specs/protocol/spec.md)). |

Full quality tree: [§10](10-quality-requirements.md).

## Stakeholders

| Stakeholder | Expectation |
|---|---|
| Operator/admin (the maintainer) | Stable self-hosted gateway in a familiar stack (Python/Nuxt) |
| Application layer | Registration API, metering hook, introspectable identity |
| MCP clients (claude.ai, ChatGPT, scripts) | Standards-compliant OAuth/API-key access, working long calls |
| Upstream server authors | Faithful proxying; forwarded identity (`X-MCP-User`, headers) |
