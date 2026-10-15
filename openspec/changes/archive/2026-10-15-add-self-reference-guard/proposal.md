# Proposal

## Why

A bundle accepts one of this gateway's own endpoints as a member upstream
([#104](https://github.com/wingfold-ai/bundlemcp/issues/104)). Nothing compares an upstream's URL with the gateway's
public URL, so in a real deployment (public URL on a public address, which the egress policy allows) a member that
carries a valid key for its own endpoint makes every tool call re-enter the gateway until a timeout stops it, each round
holding a request slot and writing an audit record. `docs/manage/bundles.md` already claims the self-reference is
rejected; it is not.

## What Changes

- Adding an upstream to a bundle is refused with `409` when the upstream's URL addresses an MCP endpoint of this
  gateway: same origin as `BUNDLEMCP_PUBLIC_URL` (host compared case-insensitively, default port made explicit,
  trailing slash ignored) and a path of the form `/{name}/mcp` under the public URL's path.
- Changing the URL of an upstream that is already a member of some bundle runs the same check, so a self-reference
  cannot be introduced after the membership exists.
- Bootstrap goes through the same service and is refused the same way.
- Documentation states what the guard covers and what it cannot: the gateway reached under another hostname (an
  internal service name, a second domain, a proxy) is not detectable from the URL alone.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `bundles`: adds BND-5, the self/circular reference guard (reserved, never implemented).

## Impact

- Code: a pure domain rule beside the server entity (`domain/servers/`), applied by the bundle membership use case and
  by the server upsert when the URL changes (`application/management/`); both services get the public base URL from
  the composition root.
- API: `PUT /api/v1/bundles/{name}/upstreams/{upstream}` and `PUT /api/v1/upstreams/{name}` gain a `409` answer; no
  DTO changes, so the OpenAPI document changes only if the response is documented.
- Docs: `docs/manage/bundles.md` (the current false claim is replaced by the actual rule and its limit).
- No ADR: this enforces an existing requirement, it does not make an architectural decision.
- Resolves GitHub issue #104.
