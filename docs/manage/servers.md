# Upstream servers

An upstream server is an MCP server the gateway connects to over Streamable HTTP and forwards calls to. Register it
once; bundles reference it by name. The admin UI lists them on the **Upstream servers** page, and the management API
addresses them under `/api/v1/upstreams`. For what each setting is for, in plain terms, see
[Upstream server settings](/guide/upstream-server-settings).

Everything on this page is available in the admin UI under **Upstream servers** and through the management API. The API
examples assume:

```bash
API=https://gw.example.com/api/v1
AUTH="Authorization: Bearer $SERVICE_KEY"
```

## Which settings a server needs

Most of a server's configuration is a fact about the server, and the gateway asks the server instead of you. Only one
question is really yours: **where does the credential come from?**

| Answer | When | Settings |
|---|---|---|
| **No credential needed** | The server answers anyone who can reach it. | `auth_mode: none` |
| **A key or token you enter** | The server's docs give you an API key or personal access token. Every caller shares it. | `static_headers`, e.g. `{"x-api-key": "…"}` |
| **Each user signs in with their own account** | The server is OAuth-protected and should see each person as themselves (Linear, Notion, GitHub-style). | `auth_mode: upstream_oauth`, `identity_mode: per_user` |
| **One shared account, signed in once** | OAuth-protected, but a single service account should serve everyone. | `auth_mode: upstream_oauth`, `identity_mode: shared` |
| **One shared machine account** | OAuth-protected and the provider issued you a client id and secret for machine access (client credentials). | as above, plus a client with `grant_type: client_credentials` |
| **A token the gateway issues per caller** | Your own server on the gateway's network wants to know who is calling and verify it. | `auth_mode: delegated_token` |

The admin UI asks exactly this question, with the answer the server gave already selected. Everything else — forwarded
headers, the identity header, the protocol pin — sits under *Advanced* because the defaults are right for almost every
server.

## Inspecting a server before registering it

`POST /api/v1/upstreams:inspect` contacts a URL the way discovery would and reports what it found. Nothing is stored.

```bash
curl -s -X POST $API/upstreams:inspect -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"url": "https://mcp.example.com/mcp"}'
```

The answer's `connection_state` is one of:

| State | What the server did | What to do |
|---|---|---|
| `ready` | Answered as an MCP server. | Register it; `server_info` and `tool_names` show what it is. |
| `oauth_required` | Refused with an OAuth challenge, or publishes OAuth metadata. | Choose whose account to use; `oauth` shows the issuer, the scopes and how the gateway identifies itself there. |
| `credential_required` | Refused, with no OAuth metadata anywhere. | It wants an API key or token header. Try one with `"headers": {...}` — it is used for that probe only, never stored or echoed. |
| `not_mcp` | Answered, but not as Streamable HTTP MCP (404/405, a web page). | The gateway already retried with `/mcp` appended; `suggested_url` names it when that worked. |
| `unreachable` | No connection (DNS, refused, TLS, timeout). | Check the URL. A server that is not up yet can still be registered. |
| `egress_denied` | The address is outside what the gateway may reach. | See [Network egress](/self-hosting/deploy#network-egress). |

`suggestion` is a ready-to-submit body for `PUT /upstreams/{name}`: a name derived from the server's own `serverInfo`,
its description, the detected `auth_mode`, and `per_user` for an OAuth server (a person's own account is the safe
default; switch to `shared` for a service account).

A registry `server.json` can seed the same flow: `POST /api/v1/upstreams:from-server-json` with `{"document": {...}}`
returns a draft with the first `streamable-http` remote's URL and the headers its publisher declared (name, description,
required, secret), so you know which credential to enter. It fetches nothing.

## Registering a server

`PUT /api/v1/upstreams/{name}` creates or updates a server by name. The path name and the body name must match.

```bash
curl -s -X PUT $API/upstreams/weather -H "$AUTH" -H "Content-Type: application/json" -d '{
  "name": "weather",
  "description": "Forecasts and current conditions",
  "url": "http://weather-mcp:8080/mcp"
}'
```

The gateway immediately probes the URL, negotiates the protocol revision, runs `tools/list` and stores the tools. The
response is the server including `health_status`, `protocol_version` and `capabilities`.

An upstream that belongs to no bundle may have any URL. Once it is a member, its URL cannot be changed to one of this
gateway's own MCP endpoints: the update answers `409` and the stored URL stays as it was (see
[Bundles](/manage/bundles#members) for the rule).

::: tip Registering a server that is not up yet
A failed probe does not reject the request. The server is stored with `health_status: error` and `last_error` explaining
why, and it is probed again on the next refresh or the next live call. This is what lets a discovery loop converge by
repeatedly `PUT`ting desired state.
:::

### Changing a server's URL

Credentials never follow a server to a new URL, so pointing an upstream elsewhere costs its connections:

- **Another resource** (a different scheme, host, port or path; the host's letter case and a trailing slash do not
  count): every stored upstream OAuth token of the server is deleted, shared and per user. Users connect their accounts
  again, and `per_user` callers get the connect tool back. A client the gateway registered or identified itself is
  deleted too, so the next connect discovers the new resource's authorization server. A client you stored keeps its id
  and grant but forgets the remembered endpoints. The audit log records it as a `management` record with action
  `upstream.credentials_revoked`.
- **Another origin** (scheme, host or port): the same write must carry the values of the server's static headers again,
  or it answers `409` and nothing changes. The secret of a client you stored is cleared; store it again with
  `PUT /api/v1/upstreams/{name}/upstream-oauth`. An import cannot keep a header value with a placeholder across such a
  move.

A new path on the same host keeps the static header values and the client secret, but still disconnects the accounts.

### Fields

| Field | Default | Meaning |
|---|---|---|
| `name` | required | Letters, digits, `_` and `-`. No double underscore: `__` separates server from tool in presented names. |
| `url` | required | The Streamable HTTP URL, usually ending in `/mcp`. Must resolve to an address the egress policy allows. |
| `description` | none | Free text, shown in the UI. |
| `auth_mode` | `none` | `none`, `static_headers`, `upstream_oauth` or `delegated_token`. `none` and `static_headers` are settled by whether static headers are stored, so you never need to pick between them. |
| `static_headers` | `{}` | Headers sent on every request to the server. |
| `forward_headers` | `{}` | Client headers to pass through, incoming name → upstream name. Denied headers are rejected with 422. |
| `send_identity_header` | derived | Inject `X-MCP-User` with the caller's identity. Omitted on create: on for a host on the gateway's own network (dotless names, `.local`, `.internal`, `.svc`, private addresses), off for public hosts. Omitted on update: unchanged. |
| `identity_mode` | `shared` | `shared` or `per_user`; only meaningful with upstream OAuth. |
| `protocol_mode` | `auto` | `auto`, `session`, or a pinned revision such as `2026-07-28`; `legacy` is a deprecated alias of `session`, read back as `session`. Omitted on update: unchanged. |
| `listing_snapshot` | `auto` | `auto`, `shared` or `live`: whether prompt and resource lists are served from what discovery stored ([Prompt and resource lists](#prompt-and-resource-lists)). Omitted on update: unchanged. Changing it does not probe the server. |
| `transport` | omitted | Accepted for compatibility; only `streamable-http` is valid. |
| `force` | `false` | Acknowledge a rename that would otherwise be rejected. |

## Authenticating to the server

### Static headers

For servers that expect a fixed credential, set `auth_mode: static_headers` and the headers to send:

```json
{
  "name": "crm",
  "url": "https://crm.example.com/mcp",
  "auth_mode": "static_headers",
  "static_headers": { "authorization": "Bearer s3cr3t" }
}
```

Header values are **write-only**. Responses list `static_header_names` only, the values never leave the gateway and
never appear in logs. Sending the server again without `static_headers` keeps the stored values; send a new value to
replace one.

### Upstream OAuth

Some servers are themselves OAuth-protected and expect a bearer obtained from their authorization server. Set
`auth_mode: upstream_oauth` and the gateway performs that OAuth flow, stores the tokens encrypted, refreshes them on
expiry, and retries a call once after a refresh.

This needs `BUNDLEMCP_TOKEN_ENCRYPTION_KEYS` to be set; until it is, the server's upstream OAuth status reports
`configured: false`.

1. Register the server with `auth_mode: upstream_oauth`.
2. Usually skip this step. The gateway identifies itself the way the MCP authorization spec orders it:
   - a client you stored (below) always wins;
   - otherwise, when the authorization server accepts **client metadata documents** and the gateway is served over
     https, the gateway's client id is its own document, `<public url>/oauth/upstream/client.json` (nothing is
     registered);
   - otherwise, when it offers **dynamic client registration**, the gateway registers itself as a public web client
     (PKCE, no secret) with `<public url>/oauth/upstream/callback` as its redirect URI, and keeps that registration
     bound to the authorization server's issuer — if the server later moves to another authorization server, the
     registration and its tokens are dropped and the gateway registers again;
   - otherwise you store a client. `POST /upstreams:inspect` tells you in advance
     (`oauth.client_identification: preregistered_required`).

   To store the client the gateway should present to the upstream:

   ```bash
   curl -s -X PUT $API/upstreams/crm/upstream-oauth -H "$AUTH" -H "Content-Type: application/json" -d '{
     "client_id": "bundlemcp",
     "client_secret": "…",
     "authorization_url": "https://auth.crm.example.com/authorize",
     "token_url": "https://auth.crm.example.com/token"
   }'
   ```

   `authorization_url` and `token_url` may be omitted when the upstream publishes OAuth metadata the gateway can
   discover. It looks where the MCP authorization spec says: the `resource_metadata` URL in the server's 401
   `WWW-Authenticate` header, then `/.well-known/oauth-protected-resource` with the server's path appended (for
   `https://crm.example.com/mcp`, `…/.well-known/oauth-protected-resource/mcp`), then at the origin; the authorization
   server it names is read through RFC 8414 or OpenID Connect metadata. A stored client always wins over registration.
   The client secret is write-only; the status route reports only whether one is stored.

3. Connect an account. From the server's page in the UI click **Connect**, or open
   `<public url>/oauth/upstream/crm/connect` in a browser while signed in as an admin. The gateway sends you through the
   upstream's consent and stores the resulting tokens. Finish the connect in the same browser, still signed in as an
   admin: the gateway refuses a return from the upstream that arrives in a browser without that session, and nothing
   is connected.
4. Check `GET /api/v1/upstreams/crm/upstream-oauth`: `shared.connected` is `true`, and `account_hint` shows a masked
   account identifier.

Every authorization, token and refresh request names the server as the RFC 8707 `resource`, so the token is issued for
that server only. The gateway refuses an authorization server that does not offer PKCE (`S256`) or whose metadata names
a different issuer than the one it was fetched for.

#### Client credentials

For a shared server whose provider issued a client for machine access, store the client with
`grant_type: client_credentials` and its secret. The gateway then obtains tokens with the client credentials grant (the
MCP OAuth Client Credentials extension) — no browser sign-in — and simply requests a new token when one expires. Connect
it right away with `POST /api/v1/upstreams/{name}/upstream-oauth:connect`, or let the first call do it. Such a client
only works with `identity_mode: shared`.

#### When a server asks for more permission

A server may accept the token but refuse one operation with `403 insufficient_scope` and the scope it needs. The gateway
does not retry blindly: it remembers the scope, and the caller gets an error with the reconnect link. The next connect
requests the original scopes plus the new ones; the status route lists them as `step_up_scopes`.

Tool discovery uses the connection: the shared one, or for a `per_user` server any user's working one. Until an account
is connected the server has no tools in the cache, and discovery reports it as not connected rather than failing. Every
completed connect triggers discovery, and when the tools change the server's bundles are invalidated so connected
clients re-list them.

`DELETE /api/v1/upstreams/crm/upstream-oauth/token` disconnects the shared account.

#### Shared versus per-user identity

`identity_mode` decides whose account the gateway uses:

- **`shared`** (default): one connection, established by an admin as above, serves every caller. This is right for
  service accounts.
- **`per_user`**: every caller connects their own account. A signed-in user who has not connected yet sees an extra
  tool, `crm__connect_account`, in the endpoint's tool list. Calling it returns the connect URL
  (`…/oauth/upstream/crm/connect?as=me`); it reaches no upstream and is not metered. The user opens the link, signs in
  to the gateway if needed, completes the upstream consent, and re-lists tools: the connect tool is gone and the
  server's tools are there. Calling one of the server's tools without a stored token fails with a structured MCP error
  carrying the same URL. API-key callers are not offered the connect tool, because a per-user connection belongs to a
  user. The connect must be finished in the browser and under the gateway account that opened the link. A link
  forwarded to someone else stores nothing for either of them, so a user's upstream account cannot end up connected to
  another person's gateway account.

One account per person per server: the stored token is used for every MCP client that person connects with. A `per_user`
server can only be served by endpoints that identify callers: the gateway refuses to put such a server in a bundle
exposed by a `none` endpoint, and refuses the endpoint change that would create that situation. How this fits with the
caller identity is on
[Authentication](/guide/authentication#upstream-identity-how-the-gateway-reaches-an-upstream-server).

Tokens are never returned by any API. The UI shows connection status (connected, expired, invalid) and the account hint
only.

## Forwarding headers and identity

Two separate mechanisms carry the caller to the upstream:

- **`auth_mode: delegated_token`** gives the upstream a token of its own on every call: short-lived (five minutes),
  issued by the gateway for the caller, with the server's URL as its audience. The upstream verifies it at the gateway's
  introspection route and learns `sub`, `email`, `aud`, the endpoint the call came through (`act.sub`) and, for a
  user, their identity provider subject (`oidc_iss`, `oidc_sub`). This is the
  token-exchange pattern, and the recommended way for your own servers to learn who is calling.
- **`forward_headers`** passes selected client headers through. `{"authorization": "authorization"}` forwards the
  caller's own gateway token, which the upstream can also introspect — but that token was issued for the gateway
  endpoint, and passing it on is the token passthrough the MCP authorization spec forbids an MCP server to accept. It
  keeps working for trusted internal servers; the API reports it as `forwards_caller_token` and the UI marks it. Prefer
  `delegated_token`. `host`, `cookie`, `content-length`, `x-api-key`, `mcp-session-id` and anything `sec-*` or `proxy-*`
  can never be forwarded, and are rejected when the server is saved.
- **`send_identity_header`** injects `X-MCP-User: <sub>`, where `sub` is the user id (or the identity provider subject
  with `BUNDLEMCP_IDENTITY_SUBJECT=oidc`) or `api_key:<id>`. A client-sent
  `X-MCP-User` is always stripped. On a `none` endpoint the header is omitted.

Details for the server side are in
[Identity for upstream servers](/integrate/upstream-identity).

## Protocol negotiation

`protocol_mode` controls how the gateway talks to the server:

| Value | Behaviour |
|---|---|
| `auto` | Probe the modern `server/discover` first, fall back to the `initialize` handshake. |
| `session` | Always use the handshake and its session (`legacy`, the former name, is accepted as a deprecated alias). Only for a server that speaks both eras but serves server-initiated requests (elicitation, sampling) on the handshake path only. |
| `YYYY-MM-DD` | Pin one modern revision. |

The negotiated revision is stored as `protocol_version` so you can see which servers still speak the handshake era.

## Connections and sessions

The gateway keeps upstream MCP sessions open and reuses them, so most calls skip the upstream's `initialize`. A
session is reused only for a request that would have opened the same one: the same server configuration and, unless
the server is identity-free, the same caller with the same forwarded headers. A server is identity-free when it
forwards no headers, is not sent the identity header, and uses neither per-user OAuth nor delegated tokens; turning
off `send_identity_header` lets callers share its sessions.

A client that holds a session (the `initialize` handshake) gets an upstream session of its own on each server, which
any replica continues. When the server forgets it — after a restart, say — the gateway opens a new one and retries the
call once, without charging it twice. A tool call is retried only when the server cannot have run it. Changing a
server's URL, headers or authentication closes its sessions on every replica.

While a session is open the gateway also hears what the server says between calls: tool, prompt and resource list
changes, resource updates and log messages reach the clients that asked for them. The caps and idle timeout are
`upstream_sessions_max`, `upstream_sessions_per_server_max` and `upstream_session_idle_timeout`
([Configuration](/self-hosting/configuration)); `BUNDLEMCP_UPSTREAM_POOLING_ENABLED=false` opens a connection per
request instead.

## Tools and health

`GET /api/v1/upstreams/{name}/tools` lists the cached tools with their input schema, annotations, `stale` flag and
`last_seen_at`. `POST /api/v1/upstreams/{name}:refresh-tools` re-probes and re-discovers; the result reports how many
tools were discovered and how many changed: new, redefined, gone stale or back again. A discovery that finds exactly
what is cached writes no tool and tells no client to re-list. Discoveries of one server never overlap, on any replica: a
refresh that arrives while another discovery of that server is running (the background probe a save started, say)
waits for it to finish, then probes and reports against what it stored. A discovery stores only what it found out —
capabilities, negotiated revision, health and connection state — onto the server as it is stored when the probe
answers, so a rename or a configuration change you save while it runs is kept.

When the upstream advertises prompts or resources, the same discovery also lists its prompts, resources and resource
templates, to the last page. Their names, URIs, titles and descriptions are cached for per-bundle curation
([Bundles](/manage/bundles#curating-members-prompts-and-resources)). Each whole listing is also stored as the server
listed it, which is what clients are served (see [Prompt and resource lists](#prompt-and-resource-lists)). Neither
holds prompt messages or resource content. A listing that fails leaves both as they were. One longer than 500
entries is cached cut to 500, is not served from storage, and is logged as `discovery.listing_truncated`. A discovery
that finds a listing changed tells the clients of the server's bundles to list prompts or resources again.

Creating a server probes it in the background. Updating one probes it only when the update changes how the upstream is
reached — `url`, `static_headers`, `forward_headers`, `auth_mode`, `identity_mode`, `send_identity_header` or
`protocol_mode` — or when its last probe failed. Re-sending an unchanged definition to a working server only writes the
database, so deploy tooling can re-apply its full config without waking every upstream.

The gateway also re-discovers every server on its own every `BUNDLEMCP_DISCOVERY_REFRESH_INTERVAL` seconds: every 30
minutes when the variable is unset, never when it is `0`. A server you registered before its upstream was reachable
therefore gets its tools without a manual refresh, and a server whose tools change is picked up within one interval. Use
the refresh endpoint when you do not want to wait.

### Prompt and resource lists {#prompt-and-resource-lists}

`prompts/list`, `resources/list` and `resources/templates/list` are answered from the listing discovery stored, without
contacting the server, when every caller may be shown that listing. A server that scales to zero then stays asleep
while a client connects and lists everything; only `tools/call`, `prompts/get`, `resources/read` and completions wake
it. When the stored listing may not be shared, the server is asked live, with the caller's headers, as before.

`listing_snapshot` decides when a listing may be shared:

| Value | Shared when |
|---|---|
| `auto` (default) | The server marked the listing `cacheScope: public`; never when it marked it `private`. Without a scope (servers before revision 2026-07-28): when nothing the server is sent depends on the caller, meaning no `forward_headers`, no `send_identity_header`, and no per-user or delegated tokens. |
| `shared` | Always. For a server that lists the same for everyone but is sent the caller's identity, or that marks every result `private` by default. |
| `live` | Never; the server is always asked. |

Two common cases need `shared`:

- **Servers on the gateway's own network** get `send_identity_header` by default, so under `auto` their unscoped
  listings are not shared.
- **FastMCP and other MCP Python SDK servers** on revision 2026-07-28 mark every list `private` unless their author
  sets a scope (`FastMCP(cache_ttl=..., cache_scope="public")`).

A stored listing is replaced by the server's next discovery, or right away when the server sends
`notifications/prompts/list_changed` or `notifications/resources/list_changed` on a pooled session. A server whose
lists change without telling the gateway is served its old listing until then. After upgrading to a version with
stored listings, existing servers are listed live until their next discovery; run `:refresh-tools` once per server, or
wait for the periodic refresh.

### Stale tools

A tool that the latest successful discovery no longer listed is **stale**. It stays in the cache with every bundle's
curation of it, but no endpoint serves it: it is absent from `tools/list`, and a call to it is rejected as an unknown
tool without reaching the upstream. If a later discovery lists it again it is served again, with its curation. A failed
probe makes nothing stale, so an outage never hides tools.

Stale tools are flagged in both tool lists and in the UI. To delete them for good, refresh and prune:

```bash
curl -s -X POST "$API/upstreams/weather:refresh-tools?prune=true" -H "$AUTH"
```

The probe runs first; only if it succeeds are the server's stale tools deleted, together with their curation in every
bundle, and the result reports how many in `pruned`. A failed probe deletes nothing. The upstream page offers the same
as **Refresh & prune** once the server has stale tools, and asks for confirmation with the list of tools it will
delete.

`health_status` is `ok`, `error` or `unknown`. While a member is `error`, every `tools/list` on its bundles still lists
its cached tools, and counts as degraded in `bundlemcp_tools_list_degraded_total` with a `tools_list.degraded` warning.
It turns `error` after `server_error_attempts` (default 3) consecutive connection failures, with the last one's message
in `last_error`, and returns to `ok` on the next answer from the upstream. Discovery probes, the periodic refresh and
live `tools/call` requests all count: a call counts as a failure when the upstream could not be reached or answered with
something that is not MCP, and as a success when it got any MCP answer, a tool error included. A refused credential, a
timeout and a cancelled call count as neither. The count is shared by every gateway replica, so failures seen on
different replicas add up, and a change to `server_error_attempts` applies from the next failure without a restart.

`connection_state` says *why*, and is updated on every probe: the states of
[inspection](#inspecting-a-server-before-registering-it), plus `account_required` (upstream OAuth is set up but nobody
has connected) and `insufficient_scope`. When the state contradicts the configuration — `oauth_required` on a server
without OAuth, `credential_required` on one that sends no credential — `configuration_mismatch` names the change, and
the UI offers it as a button. A server that sends a key and is refused stays `credential_required`: the gateway never
reads a rejected key as a reason to start OAuth.

## Renaming

The name is part of every presented tool name, so renaming a server that is a member of any bundle changes what every
connected client sees. The rename route refuses unless you acknowledge that:

```bash
curl -s -X POST "$API/upstreams/weather:rename?new_name=forecast&force=true" -H "$AUTH"
```

## Deleting

`DELETE /api/v1/upstreams/{name}` removes the server, its cached tools and its bundle memberships. Endpoints of those
bundles keep serving the remaining members. A delete sent while a discovery of the server is running, on any replica,
waits for that discovery to finish (at most one probe timeout, 60 seconds), then removes the server with everything the
discovery cached. A deleted server never comes back from a discovery that started before the delete.

## Reaching the server

The gateway connects to the URL you give it from inside its own network. On the compose stack that means service names
such as `http://weather-mcp:8080/mcp`. Loopback and cloud metadata addresses are refused by the egress policy; private
ranges are allowed. See
[Network egress](/self-hosting/deploy#network-egress).

Servers that only speak stdio are wrapped in a small HTTP sidecar first:
[stdio servers behind a sidecar](/connect/stdio-sidecar).
