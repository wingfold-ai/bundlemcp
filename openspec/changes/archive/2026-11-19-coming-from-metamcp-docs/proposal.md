# Proposal

## Why

People who run metamcp are the most likely first users of bundlemcp, and today nothing on bundlemcp.dev tells them how
their setup maps over, what they would lose or how to move it. The README names metamcp in one table row, and the
decision log that explains what was left out sits in the repository, not on the site. Without a page to point at,
answering a metamcp user in an issue or discussion means rewriting the same explanation each time.

## What Changes

- A new guide page, **Coming from metamcp** (`/guide/coming-from-metamcp`), in the Guide section of the sidebar after
  "bundlemcp vs. FastMCP". It has four parts:
  - **How the concepts map:** metamcp's MCP servers, namespaces, endpoints, tool overrides, API keys and middleware,
    each with the bundlemcp concept it becomes (upstreams, bundles with curation, endpoints with profiles, API keys,
    endpoint profiles), and what is different about it.
  - **What bundlemcp leaves out, and what to do instead:** each metamcp feature from the decision log that a metamcp
    user would miss, with the replacement where one exists. For example, stdio servers run behind a Streamable-HTTP
    sidecar, and query-parameter API keys become an `Authorization` header.
  - **Moving a setup over:** a manual migration. Write the servers, bundles and endpoints as a bootstrap document, then
    apply it at startup or through import. A worked example takes a small metamcp setup to its bootstrap document.
    The importer on the roadmap is named as the future one-step route.
  - **What you gain:** a short list of what bundlemcp adds over metamcp (restart-safe sessions, replicas, per-client
    endpoint profiles, per-user upstream OAuth, the audit log and the metering hook), each linking its docs page.
- The page states the metamcp release it was compared against, and links metamcp's own documentation for anything it
  says about metamcp.
- The README's metamcp row and the roadmap's "What bundlemcp won't do" section link the new page.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `documentation`: adds DOC-18 (a page for metamcp users).

## Impact

- New `docs/guide/coming-from-metamcp.md`, plus `docs/snippets/metamcp-migration.yaml` (the worked example). The
  page includes the example, and a test in `packages/bundlemcp/tests/infrastructure/test_bootstrap.py` applies it.
  The page gets a sidebar entry in `docs/.vitepress/config.ts`.
- Links from `README.md` (the metamcp row) and `docs/roadmap.md` ("What bundlemcp won't do").
- `CONTRIBUTING.md`: the release checklist adds a check of the page against the current metamcp release.
- No gateway behaviour changes. No ADR: the page documents decisions already recorded in the decision log.
- Second-brain task "Write the "Coming from metamcp" docs page for bundlemcp". No GitHub issue.
