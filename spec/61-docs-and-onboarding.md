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
- **DOC-2** `docs/` is a VitePress site (`docs/.vitepress/`, built with
  `npm run build` in `docs/`, validated in CI) whose pages are the
  operator/integrator guides, grouped by reader task:
  - **guide/** — what bundlemcp is, the compose quickstart, core concepts.
  - **self-hosting/** — production deployment (public URL, reverse proxy,
    upgrades, backups — fed by [71-deployment.md](71-deployment.md)), the
    full `BUNDLEMCP_*` and runtime-config reference, identity provider setup,
    the bootstrap file, day-two operations.
  - **manage/** — servers, bundles and tool curation, endpoints, API keys,
    users and consents, the audit log; each page shows the UI path and the
    equivalent management-API calls.
  - **connect/** — **claude.md** (claude-profile endpoint + OAuth walkthrough
    incl. consent), **chatgpt.md** (chatgpt profile + the re-annotation
    warning, [PROF-3](15-endpoint-profiles.md)), **scripts.md** (API-key
    access for scripts/agents), **stdio-sidecar.md** (wrapping a stdio MCP
    server in a Streamable-HTTP sidecar with a compose snippet — the
    [SRV-7](10-server-registry.md) deliverable).
  - **integrate/** — for application layers: the management API, the metering
    hook, identity forwarding + introspection for upstream servers
    ([31](31-middleware.md)/[40](40-management-api.md)), and the full HTTP
    surface reference.
  Pages document only shipped behaviour; reserved-but-unbuilt surfaces
  (metrics, live logs, inspector, export/import) are named as such in one
  place rather than described as if they existed.
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

- Theming beyond VitePress's default theme; hosting is the operator's choice
  (the built site in `docs/.vitepress/dist` is static).
- Rendering `docs/arc42`, `docs/adr` and `docs/likec4` inside the site — they
  are contributor material that links into `spec/` and stays on GitHub
  ([62-architecture-documentation.md](62-architecture-documentation.md)).
- i18n of docs (decision log).

## Open questions

- ~~Which tiny example MCP server to ship for DOC-3.~~ **Resolved:**
  `examples/echo-mcp`, a three-tool FastMCP server including an annotated
  write tool so the chatgpt profile has something to re-annotate.
- ~~Plain Markdown vs. a docs site.~~ **Resolved (2026-09):** VitePress,
  because the guides need navigation, search and a home page to be usable by
  someone who has not read the repo; the Markdown source stays reviewable in
  PRs, which keeps DOC-5 enforceable.
