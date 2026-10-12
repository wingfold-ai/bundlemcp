# ADR-0044: Bundles own prompts and resources, served by the gateway

**Status:** proposed · **Date:** 2026-10-12 · **Amends:** [ADR-0021](0021-mcp-surface-completion.md)

## Context

A bundle's tools come from its member servers, and its prompts and resources do too: they pass through live and
uncurated ([BND-8](../../spec/12-bundles.md), ADR-0021). That made sense while a bundle was only a way to put several
servers behind one URL. It falls short once the same server is reused for different purposes.

The example that prompted this: one Python-execution server sits in a bundle for chart rendering and in another for
bookkeeping. The tools are identical in both. What differs is the context a model needs to use them well: in one
bundle, how charts should look and which libraries to use; in the other, rounding rules and the chart of accounts. The
server cannot provide this, because it does not know which bundle it is serving. The bundle's `description` is sent as
MCP `instructions` on every connection, so it has to stay short ([BND-1](../../spec/12-bundles.md)) and cannot hold
reference material.

MCP already has the two shapes this material takes: prompts, which a user picks as a starting point, and resources,
which a client reads into the conversation. What is missing is a place to author them per bundle.

## Decision drivers

- The context belongs to the bundle's purpose, so it is authored and versioned with the bundle, not with a server.
- Serving it must not contact an upstream: connecting a client to a bundle should not wake servers that scale to zero
  (ADR-0043).
- No new protocol surface: clients already understand MCP prompts and resources.
- It must fit the existing config model: management API, admin UI, bootstrap and export all keyed by natural keys.

## Decision

- **Two new config entities**, `BundlePrompt` and `BundleResource`, stored in Postgres with the bundle and loaded into
  the cached bundle view next to its tools. They are specified in
  [spec 17](../../spec/17-bundle-prompts-resources.md).
- **Bundle prompts are unprefixed.** Member prompts are always `<server>__<prompt>`, and a bundle prompt name may not
  contain `__`, so the two can never collide and the router knows from the name alone where a prompt lives.
- **Bundle resources live under `bundle://resources/<name>`.** The URI carries no bundle name, so renaming the bundle
  does not break references to it.
- **Templates are substitution only.** `{{argument}}` placeholders, replaced verbatim. A message can also embed one of
  the bundle's resources, which keeps long reference text in one place.
- **Served without any upstream.** Bundle entries come first in the lists, answer their own `get` and `read`, and
  complete prompt arguments from a declared value list. Capability aggregation counts them, so a bundle with no members
  can still offer prompts and resources.
- **Edits announce themselves.** A change invalidates the bundle like a tool-curation change, and the gateway sends the
  prompts or resources `list_changed` it could not send for member changes before.
- **Curation of member prompts and resources is a separate decision.** It needs prompt and resource discovery, which
  does not exist today. Spec 17 lists it as an optional requirement, not part of this decision.

## Alternatives considered

- **A sidecar MCP server per bundle that serves the context.** Works today with no gateway change, but it is one more
  deployable per bundle, one more upstream to wake, and the content lives outside the bundle's configuration.
- **Longer bundle descriptions.** The description is sent on every connection as `instructions`; making it long costs
  context in every conversation, whether or not the material is needed.
- **Override member prompts per bundle, like tools.** Only adjusts what a member already offers. A tool-only server
  offers nothing to adjust.
- **A template language (Jinja or similar).** More expressive, but it turns admin-authored text into code the gateway
  evaluates on every request. Plain substitution covers the cases at hand.

## Consequences

**Positive:**

- One server can serve several bundles, each with its own guidance, without any change to the server.
- The context is part of the bundle's config: exported, bootstrapped and edited in the same place as its tools.
- Prompts and resources become available on bundles whose members offer none, and cost no upstream contact.

**Trade-offs:**

- The gateway now stores and serves content, not only configuration. Size limits per entry and per bundle keep that
  bounded, but the bundle view a replica caches grows with it.
- Anything authored here reaches every caller of the bundle and the model. It is not a place for secrets, and the UI has
  to say so.
- The `bundle://` scheme is a convention of this gateway; a client that persists URIs ties them to it.
