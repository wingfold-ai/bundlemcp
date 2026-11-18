# Proposal

## Why

bundlemcp goes public as the v0.4.0 preview, and nobody outside the maintainers can see where it is heading.
New visitors need one place that says what works today, what is being built and what is deliberately left out. If
that place is the docs site, it is versioned with the code and needs no GitHub Projects board that drifts from it.

## What Changes

- A new page, `https://bundlemcp.dev/roadmap`, linked from the site's top navigation. It is the project's only roadmap.
- The page draws the roadmap as a line of stations: **Now** (v0.4 public preview), **In progress**, **Next** (v0.5
  tool integrity), **Then** (v1.0) and **Later**. Each station holds coarse themes, never dates.
  - Each **Now** theme links its docs page.
  - **In progress** is generated when the site is built, from the active changes in `openspec/changes/`: each shows its
    name, the first sentence of its proposal's "Why" and how many of its tasks are checked. While the repository is
    private, these entries are plain text.
- Below the line, in plain Markdown so the site search finds it:
  - "What bundlemcp won't do" links the decision log.
  - "Have a say" points to GitHub Discussions (Ideas), linked once the repository is public.
- The roadmap changes only at releases. `CONTRIBUTING.md` says that the pull request which completes a roadmap theme
  moves it on the page, and checking the roadmap page becomes part of how a release happens.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `documentation`: adds DOC-16, the public roadmap page and its build-time "In progress" station.

## Impact

- `docs/roadmap.md` (new page) and `docs/.vitepress/config.ts` (navigation and a Vite plugin).
- `docs/.vitepress/theme/`: a new `RoadmapLine.vue` component, registered in `index.ts`.
- `docs/.vitepress/roadmap-changes.ts` (new): reads `openspec/changes/` at build time.
- `CONTRIBUTING.md`: the release section.
- No gateway code, API or dependency change. No ADR: the change makes no architectural decision.
- Resolves no GitHub issue. It is the "Publish the roadmap page" task of the clean-state milestone.
