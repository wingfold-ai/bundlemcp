# Tasks

## 1. Client IP and forwarding headers (DEP-2) — exploitable today, lands first

- [x] 1.1 Rewrite `api/http/client_ip.py` to read `X-Forwarded-For` right to left from a trusted peer, skipping
  trusted-proxy entries and falling back to the leftmost entry when all are trusted; verify with unit tests citing DEP-2
  for the spoofed-leftmost case, multiple trusted hops, an empty list and a malformed entry
- [x] 1.2 Pass `proxy_headers=False` to uvicorn in `apps/gateway/main.py` and in the documented dev command, and verify
  with an ASGI test that a peer of `127.0.0.1` with no trusted proxies is not rewritten from XFF, and with a test citing
  DEP-2 that `X-Forwarded-Proto`/`X-Forwarded-Host` from a trusted peer leave the OAuth metadata on the public URL
- [x] 1.3 Update `docs/self-hosting/deploy.md`, `configuration.md`, `setups.md` and `troubleshooting.md` (proxies must
  append to XFF), and verify `python3 tools/check_docs_links.py` passes

## 2. AUTH-29 identity header strip

- [x] 2.1 Strip every forwarded header whose name equals `X-MCP-User` ignoring case in
      `api/mcp/protocol/header_forwarding.py`, and verify with a test citing AUTH-29 that a mapping
      `x-mcp-user → x-mcp-user` (and `x-client → X-Mcp-User`) never forwards the client's value, with
      `send_identity_header` on and off

## 3. Egress at connect time (SEC-2)

- [x] 3.1 Spike whether the `httpx2` client used by the MCP transport accepts a custom network backend (or transport)
  that dials a vetted address while keeping SNI on the hostname; record the outcome in the ADR draft
- [x] 3.2 Extend the policy with `fd00:ec2::254/128`, `0.0.0.0/8`, `::/128` and IPv4-mapped normalisation, and verify
  with unit tests citing SEC-2 for each form, including an allow entry still winning
- [x] 3.3 Implement the guarded backend in `infrastructure/egress/` (resolve once, judge every address, dial a vetted
  one, raise `EgressDenied` and log `egress.denied`), and verify with tests using a fake resolver that answers
  differently on each lookup (the rebinding scenario) and for an https URL that certificate verification still uses the
  hostname
- [x] 3.4 Route every gateway-initiated client through it: an `httpx_client_factory` in
  `infrastructure/fastmcp/client_factory.py` and one client builder for `infrastructure/httpx/` and
  `infrastructure/oidc/`, all with `trust_env=False`; verify with tests that a same-origin redirect from an upstream to
  a host resolving to a blocked address is refused, and run `uv run lint-imports`
- [x] 3.5 Write the ADR "Egress policy enforced at connect time" in `docs/adr/` (extends ADR-0032), add it to
  `docs/adr/README.md` and `docs/arc42/09-architecture-decisions.md`, and verify `python3 tools/check_adr_graph.py`
  passes
- [x] 3.6 Replace the pre-flight and redirect paragraph in `docs/self-hosting/deploy.md` with the connect-time
  behaviour, and update `packages/bundlemcp/bundlemcp/api/mcp/README.md`'s egress note; verify the docs link and
  symbol checks pass

## 4. Request and response size limits (SEC-7, EP-9)

- [x] 4.1 Add `max_request_bytes` (default 4194304) and `max_upstream_response_bytes` (default 16777216) to the runtime
  config registry with a 64 KiB to 64 MiB range check, and verify with domain tests that out-of-range values are
  refused with a message naming the key
- [x] 4.2 Give `RuntimeConfig` a non-loading snapshot accessor refreshed on invalidation, and verify with an application
  test that reading it never opens a unit of work
- [x] 4.3 Add the body-limit ASGI middleware for `/api/v1` and `/{endpoint}/mcp` (declared length refused before
  reading, streamed bodies counted), rendering a JSON-RPC error on MCP routes and the API error object on `/api/v1`;
  remove `MAX_PAYLOAD_BYTES` and `_is_oversized` from the router; verify with ASGI tests citing SEC-7 and EP-9 for
  declared, chunked and under-limit bodies on both surfaces, and that no unit of work is opened for a rejected request
- [x] 4.4 Wrap upstream response streams in a per-message byte counter in the MCP client factory and map the overflow to
  a structured MCP error in the tool-call pipeline; verify with a test against an in-process upstream returning a
  message over a lowered cap, citing SEC-7
- [x] 4.5 Update the size figures in `docs/self-hosting/deploy.md` (proxy limits, checklist, summary table),
  `troubleshooting.md` and `docs/integrate/http-surface.md`, and verify the docs checks pass

## 5. CORS on MCP endpoints (SEC-5)

- [x] 5.1 Replace the global CORS middleware in `main/app.py` with a path-scoped pair (MCP routes permissive without
  credentials, everything else the SEC-4 allow-list, also when no web origins are configured), and verify with ASGI
  tests citing SEC-5 and SEC-4 for a cross-origin POST, a preflight, a readable 401 challenge, and a non-allow-listed
  origin on `/api/v1`
- [x] 5.2 Add a test citing SEC-5 that an admin session cookie never authenticates a request to `/{endpoint}/mcp`
- [x] 5.3 Rewrite the CORS paragraph of `docs/integrate/http-surface.md` and verify the docs link check passes

## 6. Gates

- [ ] 6.1 Run `cd apps/web && npm run openapi` (the runtime config listing gains two keys) and verify the generated
  files are current
- [ ] 6.2 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .`, `uv run lint-imports` (delete
  `.import_linter_cache` first if modules moved), and `python3 tools/check_docs_links.py`, `check_docs_symbols.py`,
  `check_docs_settings.py`, `check_adr_graph.py`; all pass
- [ ] 6.3 Run `openspec validate --all --strict` and verify it passes
