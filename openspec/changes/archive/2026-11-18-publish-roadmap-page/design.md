# Design

## Context

The docs site is VitePress (`docs/.vitepress/`). It already has three things this change reuses:

- **Custom Vue components in the theme.** `HomePipeline.vue` is a hand-drawn diagram that follows the brand tokens in
  `custom.css`.
- **A build-time Vite plugin**, `requirements-ledger.ts`. It reads `openspec/` through `tools/spec_ledger.py` and
  serves the result as `/requirements.json`.
- **`repository-links.ts`**, which decides whether a link into the repository is kept, from `DOCS_REPOSITORY_PUBLIC`
  (DOC-14).

The gateway's layer rules do not apply: everything here lives in `docs/` and `CONTRIBUTING.md`.

## Goals / Non-Goals

**Goals:**

- The page reads as a journey at a glance, in light and dark mode. On a phone it turns into a vertical line.
- Editing a theme means editing Markdown frontmatter; no Vue code changes.
- In progress can never drift from `openspec/changes/`.

**Non-Goals:**

- Dates, quarters, owners or per-theme status: the page stays coarse (see the proposal).
- A GitHub Projects board, or voting on the page itself.
- Listing requirement codes per theme; that is the Requirements page's job.

## Decisions

### A custom component, not LikeC4 or Mermaid

**Decision.** `RoadmapLine.vue` draws the stations as a metro line. Filled dots mark stations that are reached or
underway (Now, In progress), hollow dots the planned ones (Next, Then), and a dashed segment leads to Later. Under each
dot is a column of theme cards. Below 1200 px, where five columns no longer fit, the line runs vertically and the cards
follow their dot.

**Why not LikeC4.** LikeC4 is the single source for architecture diagrams (DOC-9). A roadmap in it would be read as
architecture, could only show the In progress station by generating `.c4` source, and would load the roughly 1 MB
web component on a text page.

**Why not Mermaid.** A Mermaid `timeline` would add a dependency, does not follow the brand styling, and cannot link a
theme to its docs page.

**Decision.** The component takes the stations as props, so it draws whatever the page passes in.

### Stations live in the page's frontmatter

**Decision.** `docs/roadmap.md` holds the stations in YAML frontmatter. Each station has a title, a tag (`v0.4`,
`v0.5`, `v1.0`) and a list of themes; a theme has a title, an optional one-line note and an optional link. The page
body passes `$frontmatter.stations` to the component.

**Why.** A release edits one YAML list next to the prose it belongs with.

**Alternative.** A separate `roadmap.ts` data file. Rejected: it moves the content out of the page that shows it.

The text under the line ("What bundlemcp won't do", "Have a say") is ordinary Markdown, so local search indexes it and
`unlinkRepository` handles the Discussions link like any other link into the repository (DOC-14).

### In progress comes from a virtual module

**Decision.** `roadmap-changes.ts` exports a Vite plugin that provides `virtual:roadmap-changes`. At build time it
reads every directory in `openspec/changes/` except `archive/` and returns, for each:

- its `name`;
- `why`: the first sentence of the first paragraph under `## Why` in `proposal.md`, with Markdown links reduced to
  their text;
- `done` and `total`: checked and all checkbox lines in `tasks.md`, counted the way OpenSpec counts them;
- `url`: a link to the proposal on GitHub, or `null` unless `repositoryPublic`.

The component imports it, so the list is in the page's HTML and needs no fetch. A few short lines do not justify the
separate request that the 0.7 MB ledger needs. The plugin watches `openspec/changes/` in the dev server.

**Alternative.** Extending `tools/spec_ledger.py`. Rejected: it is about requirements, and these fields come from a
change's prose and tasks, not from its delta specs.

### The release step lives in CONTRIBUTING.md

**Decision.** A paragraph after the numbered steps of "How a release happens": the pull request that finishes a
roadmap theme moves it on `docs/roadmap.md`, and a `feat` or breaking release is the moment to check that the page
still holds. Releases are automated, so there is no separate checklist to edit.

## Risks / Trade-offs

- **The first sentence of a proposal can be long or full of jargon.** The card truncates it at about 160 characters
  and the full sentence goes in its `title` attribute. Proposals are written for readers already (CONTRIBUTING.md).
- **A theme moves late.** The page then lags the release. The CONTRIBUTING.md step and the clean-state review mitigate
  it. A CI check would need machine-readable themes and is not worth it.
- **Vertical on a phone means a long page.** Five short stations stay well within a normal docs page.
- **No active change on the day of going public.** The empty state ("Nothing in flight right now; see Next") is
  designed rather than left blank.
