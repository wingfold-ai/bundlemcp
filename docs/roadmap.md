---
title: Roadmap
description: Where bundlemcp is heading, from the v0.4 public preview to v1.0 and beyond.
sidebar: false
aside: false
# The stations of the line below. Themes, never dates: this list changes only at releases.
stations:
  - title: Now
    tag: v0.4 public preview
    state: reached
    themes:
      - title: Bundles and tool curation
        note: Compose servers into one bundle; rename, describe or hide each tool.
        link: /manage/bundles
      - title: An endpoint per client
        note: claude.ai, ChatGPT and scripts, each with its own profile.
        link: /manage/endpoints
      - title: One login through your OIDC provider
        note: OAuth 2.1 for clients, OIDC for the admin UI.
        link: /self-hosting/identity-provider
      - title: Per-user upstream credentials
        link: /guide/authentication
      - title: Audit log
        link: /manage/audit
      - title: Export, import and bootstrap
        link: /manage/export-import
      - title: Metering hook
        note: Let an application layer meter and bill tool calls.
        link: /integrate/metering-hook
      - title: Replicas and calm restarts
        note: Sessions live in Valkey; any replica serves any call.
        link: /self-hosting/operations
  - title: In progress
    tag: open changes
    state: current
    changes: true
  - title: Next
    tag: v0.5
    subtitle: Tool integrity
    state: planned
    themes:
      - title: Detect and warn
        note: Notice when an upstream changes a tool's description or schema.
      - title: Review before serving
        note: A changed tool waits for an admin before clients see it.
      - title: Temporary deactivation
        note: Take a tool or server out of service without deleting it.
  - title: Then
    tag: v1.0
    state: planned
    themes:
      - title: metamcp importer
        note: Bring servers, namespaces and endpoints over in one step.
      - title: The 1.0 scope
        note: The API, settings and behaviour that 1.0 commits to keep.
  - title: Later
    tag: ideas
    state: later
    themes:
      - title: ChatGPT search and fetch profile
      - title: PyPI package
      - title: Metrics
---

# Roadmap

bundlemcp is the control point between your AI clients and your MCP servers: one login, curated tools, nothing
changes behind your back. This page is where it is heading. It lists themes, not dates, and changes when a release
moves one of them.

<RoadmapLine :stations="$frontmatter.stations" />

**In progress** is built from the changes open in the repository's `openspec/changes/` folder, with how many of their
tasks are done. Every change starts as a written proposal there before any code is written, so this station is
never out of date.

## What bundlemcp won't do

Some features of metamcp, the project bundlemcp replaces, were left out on purpose: stdio and SSE transports (wrap a
stdio server in a [sidecar](/connect/stdio-sidecar) instead), an OpenAPI REST bridge, API keys in query parameters,
per-user resource ownership, admin tools over MCP, local password accounts, translations and a marketplace page. The
reasons for each are in the
[decision log](https://github.com/wingfold-ai/bundlemcp/blob/main/openspec/README.md#decision-log--deliberately-dropped-from-metamcp).
A dropped feature comes back only with new evidence.

## Have a say

Ideas and use cases are welcome in the
[Ideas category of GitHub Discussions](https://github.com/wingfold-ai/bundlemcp/discussions/categories/ideas). A theme
that many people ask for moves up the line.
