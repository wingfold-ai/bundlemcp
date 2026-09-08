# Servers

A server is an upstream MCP server the gateway connects to over Streamable
HTTP. Register it once; bundles reference it by name.

Everything on this page is available in the admin UI under **Servers** and
through the management API. The API examples assume:

```bash
API=https://gw.example.com/api/v1
AUTH="Authorization: Bearer $SERVICE_KEY"
```

## Registering a server

`PUT /api/v1/servers/{name}` creates or updates a server by name. The path
name and the body name must match.

```bash
curl -s -X PUT $API/servers/weather -H "$AUTH" -H "Content-Type: application/json" -d '{
  "name": "weather",
  "description": "Forecasts and current conditions",
  "url": "http://weather-mcp:8080/mcp"
}'
```

The gateway immediately probes the URL, negotiates the protocol revision,
runs `tools/list` and stores the tools. The response is the server including
`health_status`, `protocol_version` and `capabilities`.

::: tip Registering a server that is not up yet
A failed probe does not reject the request. The server is stored with
`health_status: error` and `last_error` explaining why, and it is probed
again on the next refresh or the next live call. This is what lets a
discovery loop converge by repeatedly `PUT`ting desired state.
:::

### Fields

| Field | Default | Meaning |
|---|---|---|
| `name` | required | Letters, digits, `_` and `-`. No double underscore: `__` separates server from tool in presented names. |
| `url` | required | The Streamable HTTP URL, usually ending in `/mcp`. Must resolve to an address the egress policy allows. |
| `description` | none | Free text, shown in the UI. |
| `auth_mode` | `none` | `none`, `static_headers` or `upstream_oauth`. |
| `static_headers` | `{}` | Headers sent on every request to the server. |
| `forward_headers` | `{}` | Client headers to pass through, incoming name → upstream name. |
| `send_identity_header` | `true` | Inject `X-MCP-User` with the caller's identity. |
| `identity_mode` | `shared` | `shared` or `per_user`; only meaningful with upstream OAuth. |
| `protocol_mode` | `auto` | `auto`, `legacy`, or a pinned revision such as `2026-07-28`. |
| `transport` | omitted | Accepted for compatibility; only `streamable-http` is valid. |
| `force` | `false` | Acknowledge a rename that would otherwise be rejected. |

## Authenticating to the server

### Static headers

For servers that expect a fixed credential, set `auth_mode: static_headers`
and the headers to send:

```json
{
  "name": "crm",
  "url": "https://crm.example.com/mcp",
  "auth_mode": "static_headers",
  "static_headers": { "authorization": "Bearer s3cr3t" }
}
```

Header values are **write-only**. Responses list `static_header_names`
only, the values never leave the gateway and never appear in logs. Sending
the server again without `static_headers` keeps the stored values; send a
new value to replace one.

### Upstream OAuth

Some servers are themselves OAuth-protected and expect a bearer obtained
from their authorization server. Set `auth_mode: upstream_oauth` and the
gateway performs that OAuth flow, stores the tokens encrypted, refreshes them
on expiry, and retries a call once after a refresh.

This needs `BUNDLEMCP_TOKEN_ENCRYPTION_KEYS` to be set; until it is, the
server's upstream OAuth status reports `configured: false`.

1. Register the server with `auth_mode: upstream_oauth`.
2. Store the client the gateway should present to the upstream:

   ```bash
   curl -s -X PUT $API/servers/crm/upstream-oauth -H "$AUTH" -H "Content-Type: application/json" -d '{
     "client_id": "bundlemcp",
     "client_secret": "…",
     "authorization_url": "https://auth.crm.example.com/authorize",
     "token_url": "https://auth.crm.example.com/token"
   }'
   ```

   `authorization_url` and `token_url` may be omitted when the upstream
   publishes OAuth metadata the gateway can discover from its 401 challenge.
   The client secret is write-only; the status route reports only whether
   one is stored.
3. Connect an account. From the server's page in the UI click **Connect**, or
   open `<public url>/oauth/upstream/crm/connect` in a browser while signed in
   as an admin. The gateway sends you through the upstream's consent and
   stores the resulting tokens.
4. Check `GET /api/v1/servers/crm/upstream-oauth`: `shared.connected` is
   `true`, and `account_hint` shows a masked account identifier.

`DELETE /api/v1/servers/crm/upstream-oauth/token` disconnects the shared
account.

#### Shared versus per-user identity

`identity_mode` decides whose account the gateway uses:

- **`shared`** (default): one connection, established by an admin as above,
  serves every caller. This is right for service accounts.
- **`per_user`**: every caller connects their own account. When a user calls
  a tool without a stored token, the call fails with a structured MCP error
  carrying a connect URL (`…/oauth/upstream/crm/connect?as=me`). The user
  opens it, signs in to the gateway if needed, completes the upstream
  consent, and retries.

A `per_user` server can only be served by endpoints that identify callers:
the gateway refuses to put such a server in a bundle exposed by a `none`
endpoint, and refuses the endpoint change that would create that situation.

Tokens are never returned by any API. The UI shows connection status
(connected, expired, invalid) and the account hint only.

## Forwarding headers and identity

Two separate mechanisms carry the caller to the upstream:

- **`forward_headers`** passes selected client headers through. The common
  case is `{"authorization": "authorization"}` so the upstream receives the
  gateway-issued bearer and can verify it against the gateway's introspection
  route. `host`, `cookie`, `content-length`, `x-api-key`, `mcp-session-id`
  and anything `sec-*` or `proxy-*` can never be forwarded.
- **`send_identity_header`** injects `X-MCP-User: <sub>`, where `sub` is the
  user id or `api_key:<id>`. A client-sent `X-MCP-User` is always stripped.
  On a `none` endpoint the header is omitted.

Details for the server side are in
[Identity for upstream servers](/integrate/upstream-identity).

## Protocol negotiation

`protocol_mode` controls how the gateway talks to the server:

| Value | Behaviour |
|---|---|
| `auto` | Probe the modern `server/discover` first, fall back to the `initialize` handshake. |
| `legacy` | Always use the handshake. For upstreams whose tools need server-initiated requests such as elicitation or sampling over a session. |
| `YYYY-MM-DD` | Pin one modern revision. |

The negotiated revision is stored as `protocol_version` so you can see which
servers still speak the handshake era.

## Tools and health

`GET /api/v1/servers/{name}/tools` lists the cached tools with their input
schema, annotations and `last_seen_at`. `POST /api/v1/servers/{name}:refresh-tools`
re-probes and re-discovers; the result reports how many tools were
discovered and how many definitions changed.

Tools that disappear upstream stay in the cache, marked by an old
`last_seen_at`, so a bundle's curation of them survives a temporary outage.

`health_status` is `ok`, `error` or `unknown`. It turns `error` after
`server_error_attempts` consecutive failures (a runtime setting, default 3)
and returns to `ok` on the next successful connection.

## Renaming

The name is part of every presented tool name, so renaming a server that is
a member of any bundle changes what every connected client sees. The rename
route refuses unless you acknowledge that:

```bash
curl -s -X POST "$API/servers/weather:rename?new_name=forecast&force=true" -H "$AUTH"
```

## Deleting

`DELETE /api/v1/servers/{name}` removes the server, its cached tools and its
bundle memberships. Endpoints of those bundles keep serving the remaining
members.

## Reaching the server

The gateway connects to the URL you give it from inside its own network. On
the compose stack that means service names such as `http://weather-mcp:8080/mcp`.
Loopback and cloud metadata addresses are refused by the egress policy;
private ranges are allowed. See
[Network egress](/self-hosting/deploy#network-egress).

Servers that only speak stdio are wrapped in a small HTTP sidecar first:
[stdio servers behind a sidecar](/connect/stdio-sidecar).
