# Design

## Context

The site is VitePress (`docs/`). The Guide section already has a comparison page, `guide/bundlemcp-vs-fastmcp.md`,
which sets the tone: when each fits, then a short table. The decision log in `openspec/README.md` lists what was
dropped from metamcp, but only the roadmap links it, and only when the repository is public. Configuration moves into
bundlemcp in one of three ways: the admin UI, the management API, or a bootstrap document (`self-hosting/bootstrap.md`).
The same document can also be imported (`manage/export-import.md`). No metamcp checkout is in this repository, so
anything the page says about metamcp has to come from metamcp's own documentation.

## Goals / Non-Goals

**Goals:**

- A metamcp user can tell within one page whether their setup fits bundlemcp, and how to move it.
- The worked example is a real document that CI applies, so it cannot drift from the bootstrap format.

**Non-Goals:**

- No importer, script or converter. The importer is a roadmap theme; this page only points at it.
- No feature-by-feature review of metamcp beyond what a migrating user needs. The decision log stays the record of why.

## Decisions

### The worked example is a file the page includes

The example bootstrap document lives in `docs/snippets/metamcp-migration.yaml`. The page includes it with VitePress's
code import (`<<< @/snippets/metamcp-migration.yaml`), and an infrastructure test applies that same file with the
bootstrap runner against sqlite and fakeredis, as `test_bootstrap.py` already does for its documents.

*Alternative:* a YAML block written inline in the Markdown, with the test extracting the block. That needs a Markdown
parser in the test and breaks when the block is reworded. A file included by the page has one source and needs no
parsing.

### The example mirrors a small but typical metamcp setup

The example uses three servers, chosen so that each migration case appears once:

- a Streamable HTTP server, which maps directly;
- a stdio server, which moves behind a sidecar and is registered by the sidecar's URL;
- a server with a static API-key header.

It also has one namespace with two tool overrides and one tool turned off, which becomes a bundle with curation. Its
two endpoints become an `oauth_only` endpoint for claude.ai and an `api_key` endpoint for scripts. Each part of the
document carries a comment naming the metamcp setting it replaces.

### Claims about metamcp are pinned to a release

The page opens with a note naming the metamcp release it was compared against, and links metamcp's documentation from
the mapping table. Each claim about metamcp is checked against that release's documentation while the page is written,
not from memory.

*Alternative:* describe metamcp without a version. That reads as timeless, and is wrong the first time metamcp changes.

### Where it sits and who links it

The page goes into the Guide section, after "bundlemcp vs. FastMCP", because both pages answer "how does this compare
to what I know". Two pages link to it:

- the README's metamcp row, the first place a metamcp user lands;
- the roadmap's "What bundlemcp won't do" section, which already links the decision log.

The page links the decision log with a plain link to its repository URL, as the roadmap does. The site's
repository-link rule keeps or drops it with the repository's visibility (DOC-14); the repository is public, so the link
is live.

No code layer is touched; the only new code is a test in `packages/bundlemcp/tests/infrastructure/`.

## Risks / Trade-offs

- [metamcp changes after the page is written] → The release note at the top says what the page compared against. The
  page is listed for review on each bundlemcp minor release, alongside the roadmap check in CONTRIBUTING.
- [The page reads as criticism of metamcp] → It credits metamcp for the product shape (as the README does), and states
  differences as trade-offs: what bundlemcp leaves out is listed as plainly as what it adds.

## Migration Plan

Docs only; it ships with the next docs publish after merge. Rolling back means reverting the page and its links.
