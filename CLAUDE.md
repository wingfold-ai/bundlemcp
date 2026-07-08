# bundlemcp

> Self-hostable MCP bundling gateway — a focused Python/Nuxt rewrite of the
> bundling core of metamcp.

## Project Overview

bundlemcp registers upstream MCP servers (Streamable HTTP only), composes them
into **bundles**, and exposes each bundle through one or more **endpoints**
shaped for the consuming client (claude.ai OAuth profile, ChatGPT re-annotation
profile, API-key access for scripts). It is designed to be consumed by an
application layer (application-layer adds Keycloak, billing, discovery) but is fully
usable standalone with any OIDC provider.

The `/spec` folder is the source of truth: [spec/README.md](spec/README.md) is
the index, each numbered file is an atomic spec with testable requirement IDs
(`SRV-1`, `EP-3`, …). The decision log in spec/README.md lists deliberately
dropped metamcp features — do not reintroduce them without new evidence.

## Architecture

<!-- High-level structure: key components, how they fit together, where things live. -->

## Development

<!-- How to set up, run, and build the project locally. -->

## Testing

<!-- How to run the tests and what's expected before a change is considered done. -->

## Conventions

<!-- Code style, naming, commit/branch conventions, and any project-specific rules. -->

## Git & Commit Attribution

Commits and PRs must land in the user's name, never Claude's. The standing
rules — no `Co-Authored-By: Claude` trailer, no "Generated with Claude Code"
line, commit/PR behavior, and the security guardrails — are documented in:

@.claude/docs/git-attribution.md

Read and follow that file whenever you commit, push, or open a pull request.
