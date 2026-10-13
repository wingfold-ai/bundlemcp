# Tasks

## 1. Spike and decision record

- [ ] 1.1 Spike against the pinned FastMCP/MCP SDK: continue an upstream session on a fresh transport from a stored
  `Mcp-Session-Id` without `initialize`, and read the related request id in client callbacks; record the result and
  verify both behaviours with a throwaway test against an in-process FastMCP server
- [ ] 1.2 Write the ADR (next free number in `docs/adr/`) for upstream session pooling, mark ADR-0012 superseded and
  ADR-0021 amended in their status lines and `docs/adr/README.md`, and verify `python3 tools/check_adr_graph.py` passes

## 2. Domain rules

- [ ] 2.1 Add `UpstreamSessionKey` with the config fingerprint and the identity-key rules of design D2, and
      `McpServer.is_identity_free`; verify with unit tests named for AUTH-31 and SES-6 (same user, two credentials → two
      keys; token refresh → same key; identity-free → `shared`)
- [ ] 2.2 Extend `UpstreamBinding` with upstream session id, protocol version, config fingerprint and identity key
  (optional, described fields) and verify a version-2 record written by the previous build still loads (DEP-6, SES-5)
- [ ] 2.3 Add `UpstreamRetryPolicy` and verify with unit tests citing SES-7 that `tools/call` retries on
  `session_expired` and `not_sent` only, reads on any transport loss, and never twice

## 3. The pool

- [ ] 3.1 Add the `UpstreamSessionPool` contract and the `PooledUpstreamSessions` adapter with leases, the lease-header
  auth flow (design D3) and failure classification; verify with infrastructure tests against in-process FastMCP servers
  that a second call reuses the session and that forwarded headers are injected per request (SES-6, AUTH-31)
- [ ] 3.2 Register `upstream_sessions_max`, `upstream_sessions_per_server_max` and `upstream_session_idle_timeout` in
  the config registry and implement LRU eviction, idle close and the per-call fallback; verify with tests citing SES-8
- [ ] 3.3 Add `BUNDLEMCP_UPSTREAM_POOLING_ENABLED` to `Settings` (described field) and verify that off restores the
  per-call factory path with the existing test suite green
- [ ] 3.4 Document the new config keys and setting in `docs/self-hosting/configuration.md` and verify
  `python3 tools/check_docs_settings.py` passes

## 4. Calls and bindings

- [ ] 4.1 Make `UpstreamCall` and `MemberFanout` lease from the pool, write the full binding through
  `SessionStore.set_binding`, and continue bound sessions on another replica; verify with an api test citing SES-5 and
  SES-6 that two app instances on one store send the same upstream session id and one `initialize`
- [ ] 4.2 Apply `UpstreamRetryPolicy` in both: re-initialize, rebind and retry once under the same idempotency key, and
  count final failures toward health status; verify with api tests citing SES-7 (upstream restarted between calls → one
  `pre_call`, one `post_call`, result returned; repeated failure → `-32000` and audit `error`)
- [ ] 4.3 End a binding's upstream sessions on `DELETE …/mcp` (SES-4) and verify with an api test that the upstream
  receives `DELETE` for each bound session

## 5. Invalidation

- [ ] 5.1 Wire `server` invalidation events and the reconnect flush to `pool.invalidate` / `pool.invalidate_all` in
  `main/`; verify with tests citing SES-9, SES-21 and UPS-6 that a URL or header change closes the transports on another
  app instance and the next call uses the new config

## 6. Between-call channel

- [ ] 6.1 Keep the standalone stream open on bound sessions and on sessions with subscribers, and add
  `UpstreamNotificationRouter` with the Valkey re-discovery gate; verify with api tests citing PROT-10 that a
  `tools/list_changed` between calls triggers one discovery across two app instances and reaches a GET stream and a
  `subscriptions/listen` stream
- [ ] 6.2 Fan `logging/setLevel` out to members that advertise logging on the bound sessions and deliver between-call
  log messages to the GET stream; verify with api tests citing PROT-7
- [ ] 6.3 Add the resource-subscription index, relay `resources/subscribe` and a new `resources/unsubscribe` handler,
  re-subscribe after a rebind, and deliver `notifications/resources/updated`; verify with api tests citing PROT-23
- [ ] 6.4 Honour `resourceSubscriptions` and member list changes on `subscriptions/listen`, unsubscribing upstream when
  the stream closes; verify with api tests citing PROT-17
- [ ] 6.5 Remove the `resources.subscribe_push_pooling_dependent` warning and the pooling-dependent residual notes in
  `packages/bundlemcp/bundlemcp/api/mcp/README.md`, and verify `rg pooling_dependent packages/` finds nothing

## 7. Documentation

- [ ] 7.1 Update arc42 §5, §6 (a runtime scenario for a call on a bound session and for a between-call notification),
  §8 and §11 (drop the pooling-dependent debt), and the LikeC4 model if a new element appears; verify
  `npx likec4 validate docs/likec4` and `python3 tools/check_docs_links.py` pass
- [ ] 7.2 Update `docs/manage/` or `docs/connect/` pages that state upstream connections are per call, and verify
  `rg -n "per.call" docs/` lists only historical ADR text

## 8. Gates

- [ ] 8.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .` and `uv run lint-imports` (delete
  `.import_linter_cache` first) and verify all pass
- [ ] 8.2 Run `python3 tools/check_docs_links.py`, `check_docs_symbols.py`, `check_docs_settings.py` and
  `check_adr_graph.py` and verify all pass
- [ ] 8.3 Run `cd apps/web && npm run openapi` if a DTO or route changed and verify `git diff --exit-code
  apps/web/openapi.json apps/web/types/api.d.ts` is clean afterwards
- [ ] 8.4 Run `openspec validate --all --strict` and verify it passes
