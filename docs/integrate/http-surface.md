# HTTP surface reference

Every route the gateway serves, by prefix. All of them live on the one port the gateway listens on; the reverse proxy
needs no path-based routing.

## MCP endpoints

| Method | Path | Notes |
|---|---|---|
| `POST` | `/{endpoint}/mcp` | JSON-RPC over Streamable HTTP for every supported MCP revision. |
| `GET` | `/{endpoint}/mcp` | Server-to-client event stream for handshake-era sessions. Requires `Mcp-Session-Id`; 405 without one. |
| `DELETE` | `/{endpoint}/mcp` | Ends a handshake-era session. Requires `Mcp-Session-Id` (405 without one) and the endpoint's credential. |

Responses:

| Status | When |
|---|---|
| `200` | A JSON-RPC result, as JSON or as an SSE stream. A `tools/call` is always streamed. |
| `202` | A client's JSON-RPC *response* to a server request, accepted on a session. |
| `204` | `DELETE` ended the session. |
| `400` | A JSON-RPC error, including a malformed envelope. See [Request envelope](#request-envelope). |
| `401` | Missing or invalid credentials, with a `WWW-Authenticate` challenge carrying the endpoint's `resource_metadata`. A bearer that was presented and refused (issued for another endpoint, expired, revoked or unknown) adds `error="invalid_token"`, which tells an OAuth client to authorise again for this endpoint; a request with no credential gets the challenge without an error. |
| `403` | A browser request from an origin the endpoint does not allow, as a JSON-RPC error with `id: null`, before any credential is checked. |
| `404` | An unknown or disabled endpoint, or a session id the gateway does not hold for this endpoint and caller. |
| `405` | `GET` or `DELETE` without `Mcp-Session-Id`, with `Allow: POST`. |
| `413` | A request body over the limit (4 MiB by default), as a JSON-RPC error with `id: null`. |
| `429` | A rate limit, with `Retry-After`. |
| `503` | The live-state store (Valkey) is unreachable, with `Retry-After`. The session is kept; retry it. |

CORS on these routes follows each endpoint's [allowed browser origins](/manage/endpoints#browser-origins). For a request
whose `Origin` the endpoint allows (or the gateway's own), the response reflects it in `Access-Control-Allow-Origin`
(with `Vary: Origin`) and exposes `Mcp-Session-Id` and `WWW-Authenticate`, and an `OPTIONS` preflight is answered for
`GET`, `POST` and `DELETE` with the headers the MCP transport sends (`Authorization`, `Content-Type`, `Accept`,
`Mcp-Session-Id`, `MCP-Protocol-Version`, `Mcp-Method`, `Last-Event-ID`, `X-API-Key`), cacheable for ten minutes. A
request or preflight from any other origin gets `403` and no CORS headers. A request without an `Origin` (any client
that is not a browser) is not affected. Credentials are never allowed, and these routes never authenticate by cookie: a
caller presents a bearer token or an API key in a header. Answers given before the endpoint is resolved (`404` for an
unknown endpoint, a parse error, `413`) carry no CORS grant. `BUNDLEMCP_WEB_ORIGINS` governs `/api/v1` and the rest of
the gateway only.

## Request envelope

The gateway serves two MCP eras on the same URL and decides which one a POST belongs to from the request itself. This is
the part of the surface an SDK normally hides, so it matters only if you are building requests by hand.

| The request carries | Era | Session |
|---|---|---|
| `params._meta` with a protocol version | Stateless | None; each request stands alone |
| `Mcp-Session-Id`, from an earlier `initialize` | Session | Held in Valkey |
| Neither | — | Refused, `400` |

### Stateless requests

A stateless request repeats its context every time. Both `_meta` keys below are required, and three headers must mirror
the body exactly:

| Where | Key | Value |
|---|---|---|
| `params._meta` | `io.modelcontextprotocol/protocolVersion` | `2026-07-28` |
| `params._meta` | `io.modelcontextprotocol/clientCapabilities` | An object; `{}` is valid |
| `params._meta` | `io.modelcontextprotocol/clientInfo` | Optional `{"name":…,"version":…}` |
| Header | `MCP-Protocol-Version` | Equal to the `_meta` protocol version |
| Header | `Mcp-Method` | Equal to the body's `method` |
| Header | `Mcp-Name` | For `tools/call`, `prompts/get` and `resources/read` only: equal to the body's `name` (or `uri` for `resources/read`) |

A tool whose input schema annotates a property with `x-mcp-header` also expects that argument mirrored as
`Mcp-Param-<Name>`.

The mirrored headers exist so a proxy can route on them without parsing the body. They are checked, not merely read: any
disagreement with the body is refused rather than resolved in the body's favour.

```bash
V=2026-07-28
curl -s https://gw.example.com/assistant-ci/mcp \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -H "MCP-Protocol-Version: $V" \
  -H "Mcp-Method: tools/list" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{"_meta":{
        "io.modelcontextprotocol/protocolVersion":"'"$V"'",
        "io.modelcontextprotocol/clientCapabilities":{}}}}'
```

Errors from this validation are JSON-RPC errors with HTTP `400`:

| Code | Name | Cause |
|---|---|---|
| `-32602` | invalid params | `params._meta` is absent, not an object, or missing a required key |
| `-32020` | header mismatch | `MCP-Protocol-Version`, `Mcp-Method`, `Mcp-Name` or an `Mcp-Param-*` header disagrees with the body, or is absent |
| `-32022` | unsupported protocol version | The requested revision is not served; `data` lists `supported` and `requested` |
| `-32601` | method not found | Answered with HTTP `404` |

### Session requests

A session client opens with `initialize`, receives `Mcp-Session-Id`, and sends it on every later request; none of the
`_meta` or mirrored-header rules apply. Served revisions are `2025-11-25`, `2025-06-18` and `2025-03-26`, newest first.
Setting `BUNDLEMCP_LEGACY_PROTOCOL_ENABLED=false` serves the stateless era only.

Every official SDK speaks one era or the other, so the practical advice is to use one — see
[Scripts and CI](/connect/scripts).

## OAuth authorization server

| Method | Path | Notes |
|---|---|---|
| `GET` | `/.well-known/oauth-authorization-server` | RFC 8414 metadata. |
| `GET` | `/.well-known/oauth-protected-resource/{endpoint}/mcp` | Protected-resource metadata for one endpoint. |
| `POST` | `/oauth/register` | RFC 7591 dynamic client registration; public clients, redirect URIs must be https or localhost and on `BUNDLEMCP_DCR_ALLOWED_REDIRECT_URIS` when it is set. Rate-limited per IP unless every redirect URI is allow-listed, and capped by a global quota of unused clients; either limit answers `429` with `too_many_requests`. |
| `GET` | `/oauth/authorize` | Authorization code with S256 PKCE. Accepts `resource` (RFC 8707) naming the endpoint. Redirects to the identity provider when no browser session exists. Client ids that are `https://` URLs are resolved as client ID metadata documents, fetched from public addresses only, at most 16 KiB within 5 seconds; a URL that failed is refused for a minute without a new fetch. |
| `POST` | `/oauth/consent` | The consent form's submit. |
| `POST` | `/oauth/token` | `authorization_code` and `refresh_token` grants. Refresh tokens rotate; reuse of a rotated token revokes the whole family. |
| `POST` | `/oauth/introspect` | RFC 7662. Requires a service API key, as a bearer, in `X-API-Key`, or as the HTTP Basic client secret. |
| `POST` | `/oauth/revoke` | RFC 7009. The client may revoke only its own tokens. |

Every authorization response, including error redirects, carries `iss=<issuer>` (RFC 9207).

## Browser login and upstream connect

| Method | Path | Notes |
|---|---|---|
| `GET` | `/login?next=` | Starts the OIDC login; returns to `next` afterwards. |
| `GET` | `/login/callback` | The redirect URI to register with the identity provider. |
| `POST` | `/logout` | Ends the bundlemcp session. |
| `GET` | `/oauth/upstream/{server}/connect` | Starts the upstream OAuth flow for a server. Admins establish the shared connection; `?as=me` connects the signed-in user's own account on a `per_user` server. |
| `GET` | `/oauth/upstream/callback` | The redirect URI to register with upstream OAuth providers: `<public url>/oauth/upstream/callback`. |

These pages, and the consent page `GET /oauth/authorize` renders, carry hardening headers: a CSP with
`default-src 'none'`, `frame-ancestors 'none'` and `form-action 'self'`, plus `X-Frame-Options: DENY` and
`Cache-Control: no-store`. The consent page's `form-action` also names the redirect URI of the authorization it decides
(scheme, host, port and path), because browsers apply `form-action` to the redirect that delivers the code or
`access_denied` to the client. A redirect URI that cannot be written into a CSP (for example one whose path holds `;`
or `,`) keeps the page same-origin, and Approve or Deny then answers with a page linking to the client instead of a
redirect.

## Management API

| Path | Notes |
|---|---|
| `/api/v1/…` | See [Management API](/integrate/management-api). |
| `/api/v1/docs` | Interactive documentation. |
| `/api/v1/openapi.json` | The OpenAPI document. |

CORS on `/api/v1` is restricted to `BUNDLEMCP_WEB_ORIGINS`.

## Probes

| Method | Path | Notes |
|---|---|---|
| `GET` | `/healthz` | Liveness. Unauthenticated. |
| `GET` | `/readyz` | Readiness: Postgres answers a trivial query and Valkey answers a ping. Unauthenticated. |

## Reserved names

Because endpoints are served at the root, these first path segments cannot be endpoint names: `api`, `oauth`,
`.well-known`, `healthz`, `readyz`, `metrics`, `docs`, `login`, `consent`, `static`.

## Limits

| Limit | Default |
|---|---|
| Request body | 4 MiB (`max_request_bytes`), rejected with `413` before it is parsed, chunked bodies included |
| One upstream message | 16 MiB (`max_upstream_response_bytes`); a larger tool result is answered with an error |
| Single tool call | 60 s, raised to at most 1800 s by runtime configuration |
| Access token lifetime | 1 hour |
| Refresh token lifetime | 7 days |
| Authorization code lifetime | 10 minutes, single use |
| Admin session maximum age | 12 hours |
| Session idle expiry | 24 hours |
| Tool-list cache hint | 300 s |
| Auth-failure lockout | 20 failures per 300 s per IP |

## Next steps

- [Management API](/integrate/management-api) — the versioned REST surface.
- [Error responses](/integrate/errors) — every error shape the gateway emits.
- [Scripts and CI](/connect/scripts) — calling an endpoint with a key.
