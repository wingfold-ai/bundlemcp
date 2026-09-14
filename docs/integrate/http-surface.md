# HTTP surface reference

Every route the gateway serves, by prefix. All of them live on the one port
the gateway listens on; the reverse proxy needs no path-based routing.

## MCP endpoints

| Method | Path | Notes |
|---|---|---|
| `POST` | `/{endpoint}/mcp` | JSON-RPC over Streamable HTTP for every supported MCP revision. |
| `GET` | `/{endpoint}/mcp` | Server-to-client event stream for handshake-era sessions. Requires `Mcp-Session-Id`; 405 without one. |
| `DELETE` | `/{endpoint}/mcp` | Ends a handshake-era session. Requires `Mcp-Session-Id`; 405 without one. |

Responses: 401 with a `WWW-Authenticate` challenge for missing or invalid
credentials, 404 for an unknown or disabled endpoint, 429 with
`Retry-After` for rate limits.

CORS on these routes is permissive (the request origin is reflected, no
credentials) so browser-based MCP clients work; `Mcp-Session-Id` and
`WWW-Authenticate` are exposed.

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

Every authorization response, including error redirects, carries
`iss=<issuer>` (RFC 9207).

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
| `GET` | `/readyz` | Readiness: stores reachable, schema current. Unauthenticated. |

## Reserved names

Because endpoints are served at the root, these first path segments cannot
be endpoint names: `api`, `oauth`, `.well-known`, `healthz`, `readyz`,
`metrics`, `docs`, `login`, `consent`, `static`.

## Limits

| | Default |
|---|---|
| Access token lifetime | 1 hour |
| Refresh token lifetime | 7 days |
| Authorization code lifetime | 10 minutes, single use |
| Admin session maximum age | 12 hours |
| Auth-failure lockout | 20 failures per 300 s per IP |
