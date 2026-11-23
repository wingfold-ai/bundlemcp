# Proposal

## Why

Search engines and AI assistants are a quiet way for people to find bundlemcp: someone searches "mcp gateway" or
"mcp oauth", or asks an assistant which MCP gateway to use. Today 34 of the site's 37 pages share one site-wide meta
description, so a search result for the quickstart reads the same as one for the audit log, and the description names
neither the terms people search for nor what the page is about. Assistants have no compact entry point to the site:
there is no `llms.txt`.

## What Changes

- Every page of the documentation site gets its own meta description, written for the searches it answers. The home
  page title leads with "MCP gateway". Search volumes and the page each term maps to are in the keyword research note
  kept outside the repository (November 2026: "mcp gateway" about 2,400 a month in the US, "mcp authentication" 590,
  "mcp oauth" 320, "claude custom connector" 260, "metamcp" 210).
- The site-wide description, the fallback for any page without one, names any MCP client rather than two.
- The build writes `/llms.txt`, an index of every page in sidebar order with its title, URL and description, and
  `/llms-full.txt`, the Markdown of every page in the same order, following the llms.txt convention.
- A hermetic test fails when a page has no description or one that is too long for a search result.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `documentation`: adds DOC-20 (every page has its own description) and DOC-21 (an llms.txt index of the site).

## Impact

- `description:` frontmatter on every page under `docs/` that the site publishes; `docs/index.md` also gets a `title`.
- `docs/.vitepress/config.ts`: the site description, and a `buildEnd` step from the new `docs/.vitepress/llms-txt.ts`.
- `docs/README.md`: the publishing section names the two files.
- Tests under `packages/bundlemcp/tests/infrastructure/`.
- No gateway behaviour changes. No ADR.
