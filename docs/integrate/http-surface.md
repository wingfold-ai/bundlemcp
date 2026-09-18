# HTTP surface reference

Every route the gateway serves, by prefix. All of them live on the one port the gateway listens on; the reverse proxy
needs no path-based routing.

## MCP endpoints

| Method | Path | Notes |
|---|---|---|
| `POST` | `/{endpoint}/mcp` | JSON-RPC over Streamable HTTP for every supported MCP revision. |
| `GET` | `/{endpoint}/mcp` | Server-to-client event stream for handshake-era sessions. Requires `Mcp-Session-Id`; 405 without one. |
| `DELETE` | `/{endpoint}/mcp` | Ends a handshake-era session. Requires `Mcp-Session-Id`; 405 without one. |

Responses:

| Status | When |
|---|---|
| `200` | A JSON-RPC result, as JSON or as an SSE stream. A `tools/call` is always streamed. |
| `202` | A client's JSON-RPC *response* to a server request, accepted on a session. |
| `204` | `DELETE` ended the session. |
| `400` | A JSON-RPC error, including a malformed envelope. See [Request envelope](#request-envelope). |
| `401` | Missing or invalid credentials, with a `WWW-Authenticate` challenge. |
| `404` | An unknown or disabled endpoint, or a session id the gateway does not hold. |
| `405` | `GET` or `DELETE` without `Mcp-Session-Id`, with `Allow: POST`. |
| `413` | A request body over 4 MiB, as plain text. |
| `429` | A rate limit, with `Retry-After`. |

CORS on these routes is the same app-wide policy as `/api/v1`: origins are allow-listed from `BUNDLEMCP_WEB_ORIGINS`,
credentials are permitted, and `Mcp-Session-Id` is the one exposed response header. A browser MCP client on an origin
that is not listed receives no CORS headers, so it cannot read the `WWW-Authenticate` challenge. Browser-based clients
therefore need their origin added to `BUNDLEMCP_WEB_ORIGINS`; clients that are not browsers are unaffected.

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
| `POST` | `/oauth/register` | RFC 7591 dynamic client registration; public clients, redirect URIs must be https or localhost. Rate-limited per IP. |
| `GET` | `/oauth/authorize` | Authorization code with S256 PKCE. Accepts `resource` (RFC 8707) naming the endpoint. Redirects to the identity provider when no browser session exists. Client ids that are `https://` URLs are resolved as client ID metadata documents. |
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

These pages carry hardening headers (CSP, `frame-ancestors 'none'`).

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
| Request body | 4 MiB, rejected with `413` before the body is read |
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
