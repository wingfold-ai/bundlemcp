# 61 — Documentation & onboarding

**Status:** Accepted · **Origin:** new

## Summary

User-facing documentation is a deliverable with an owner, not an afterthought.
This spec owns everything a new operator or integrator reads; architecture
documentation (arc42/ADR/LikeC4) is owned by
[62-architecture-documentation.md](62-architecture-documentation.md) and
reuses the same LikeC4 diagrams.

## Requirements

- **DOC-1** Repository `README.md`: what bundlemcp is (one screen), quickstart
  (clone → `docker compose up` → log in via the dev IdP → demo bundle works),
  links into `docs/` and `spec/`.
- **DOC-2** `docs/` contains operator/integrator guides:
  - **connect-claude.md** — creating a claude-profile endpoint and adding it
    to claude.ai (OAuth flow walkthrough incl. consent screen).
  - **connect-chatgpt.md** — chatgpt-profile endpoint setup + the re-annotation
    warning explained ([PROF-3](15-endpoint-profiles.md)).
  - **connect-scripts.md** — API-key access for scripts/automations.
  - **stdio-sidecar.md** — wrapping a stdio MCP server in a Streamable-HTTP
    sidecar with a compose snippet (the [SRV-7](10-server-registry.md)
    deliverable).
  - **deploy.md** — production deployment: public URL, reverse proxy,
    backups (fed by [71-deployment.md](71-deployment.md)).
  - **integrate.md** — for application layers: management API, metering hook,
    introspection contract ([31](31-middleware.md)/[40](40-management-api.md)).
- **DOC-3 Demo seed:** the dev compose stack ships a demo bootstrap file
  ([41-bootstrap.md](41-bootstrap.md)) registering a small example MCP server
  container, one bundle, and one `default`-profile endpoint — a fresh install
  is never empty and the quickstart has something to click.
- **DOC-4** Docs use the LikeC4-rendered context/deployment views from
  `docs/likec4/` ([ADOC-3](62-architecture-documentation.md)) instead of
  hand-drawn diagrams.
- **DOC-5** Docs are updated in the same PR as the behavior they describe;
  stale docs are a review blocker, same status as failing tests.

## Out of scope

- Hosted docs site/theming (plain Markdown in-repo for v1).
- i18n of docs (decision log).

## Open questions

- Which tiny example MCP server to ship for DOC-3 (a purpose-built
  `examples/echo-mcp` container is likely simplest) — decide at
  implementation.
