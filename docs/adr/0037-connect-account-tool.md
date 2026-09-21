# ADR-0037: A gateway-provided connect-account tool for per-user upstreams

**Status:** accepted · **Date:** 2026-09-21 · **Amends:** [ADR-0017](0017-upstream-oauth-encryption.md)

## Context

ADR-0017 resolved how a `per_user` upstream asks a user to connect their
account: a structured MCP error carrying the connect URL, returned when the
user calls one of that server's tools. That assumes the user has a tool to
call.

On a live deployment they did not. A bundle's tools come from the discovery
cache, and discovery probed upstreams with static headers only, so an
OAuth-protected server listed nothing. With no tools listed there was nothing
to call, no error, and no URL: the user could never connect, so discovery
could never succeed. Fixing discovery to send a connected account's token
(spec 23 UPO-9) breaks the loop only after the first user connects; the first
user, and every later user of a per-user server, still needs a way in that
does not depend on the server's own tools.

## Decision drivers

- **Works in every client.** claude.ai and other MCP clients reliably list and
  call tools; support for URL-mode elicitation or out-of-band prompts is not
  something the gateway can count on.
- **No upstream involvement.** The way in must work before the gateway has any
  credential for the upstream.
- **Per caller.** Whether the prompt is needed depends on who is asking, not on
  the bundle.

## Decision

- For each enabled member server that requires a per-user token, a signed-in
  caller with no valid connection to it sees an extra tool,
  `<server>__connect_account`, after the bundle's tools. It takes no arguments
  and is annotated read-only.
- Calling it returns the connect URL (`/oauth/upstream/<server>/connect?as=me`)
  as a normal result, with an instruction to re-list tools after signing in.
  No upstream is reached and the metering hook is not consulted; the call is
  audited as a success against the server.
- It is not listed once the caller holds a valid connection, but stays
  callable, so a user can connect a different account. It never shadows an
  upstream tool that already presents the same name. API-key and anonymous
  callers are not offered it, since a per-user connection is keyed by a user.
- The structured connect error of ADR-0017 stays for calls to the server's own
  tools. URL-mode elicitation remains a possible later addition.
- A completed connect triggers discovery and invalidates the server's bundles,
  so a live client is told to re-list and sees the real tools in place of the
  connect tool.

## Consequences

- `tools/list` is now per caller for bundles with per-user servers: one token
  lookup per such server per listing.
- A client that ignores `tools/list_changed`, or caches the list for its
  advertised lifetime, shows the connect tool until it lists again; the tool's
  result tells the user to refresh.
- The name `connect_account` under a server prefix is reserved in practice;
  an upstream tool of that name wins.
