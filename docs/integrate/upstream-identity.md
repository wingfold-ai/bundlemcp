# Identity for upstream servers

An MCP server behind the gateway usually wants to know **who** is calling:
to keep per-user state, apply quotas, or scope data. The gateway offers two
mechanisms with different trust levels, and one route for verifying.

This page is the upstream half of a bigger picture; for how the caller got
*into* the gateway in the first place, see
[Authentication](/guide/authentication).

## `X-MCP-User`: trusted on the internal network

When a server's `send_identity_header` is on — the default for a server on
the gateway's own network, off for public hosts — every request the gateway
sends it carries:

```
X-MCP-User: <sub>
```

where `sub` is the user's id for OAuth callers and `api_key:<id>` for API-key
callers. The gateway strips any `X-MCP-User` a client sent, so the header can
only come from the gateway. On an open (`none`) endpoint the header is
omitted.

This is a plain header, not a signed assertion. It is safe exactly when the
server is only reachable through the gateway, which is the case on a compose
or cluster network. Do not trust it on a server that is also reachable from
the internet.

A server that keys its state by `X-MCP-User` needs no OAuth handling at all.
The `hyperframes` server in the reference stack works this way.

## Delegated token plus introspection: verifiable, and bound to you

For servers that must verify the caller, register them with
`auth_mode: delegated_token`. On every call the gateway sends
`Authorization: Bearer bmcp_dt_…`, a token it issued for this caller that is
valid for five minutes and **only at your server**: its audience is your
server's URL. Verify it at the introspection route (below, with a
`service`-kind API key):

```json
{
  "active": true,
  "sub": "…",
  "aud": "http://weather-mcp:8080/mcp",
  "token_use": "delegated",
  "act": { "sub": "endpoint:main" },
  "client_id": "bundlemcp-delegation",
  "email": "…",
  "exp": 1757340300
}
```

Check that `aud` is your own URL; `sub` is the caller (a user id or
`api_key:<id>`), `act.sub` the endpoint the call came through. This is token
exchange: the caller's token never leaves the gateway, so a compromised or
curious upstream holds nothing that would open the caller's endpoint.
Anonymous callers (open endpoints) get no token.

## Forwarded bearer plus introspection: legacy

The older way forwards the client's own bearer and lets the server ask the
gateway whether it is valid. It works, but the bearer was issued for the
gateway endpoint, and passing it on is the token passthrough the MCP
authorization spec forbids; the UI and API flag it (`forwards_caller_token`).
Prefer a delegated token for new servers.

1. Register the server with `forward_headers: {"authorization": "authorization"}`.
   The gateway then passes the caller's `Authorization` header through on
   every call.
2. Give the server a `service`-kind API key so it can call the introspection
   route. Introspection is never anonymous.
3. In the server, on each request, `POST` the received bearer to
   `<public url>/oauth/introspect`:

```bash
curl -s https://gw.example.com/oauth/introspect \
  -u "bundlemcp:bmcp_sk_<service key>" \
  -d "token=<the forwarded bearer>"
```

```json
{ "active": true, "sub": "…", "client_id": "…", "exp": 1757340000, "scope": "…", "aud": "…" }
```

The service key is accepted as the RFC 7662 client secret in HTTP Basic
authentication, with any client id. A bearer that was itself an **API key**
introspects as active with `sub` `api_key:<id>`, so a server written for
introspection serves API-key callers without a second code path.

`sub` is stable per user for the deployment's lifetime; use it as your
per-user key. The `seo-gsc` server in the reference stack works this way and
stores per-user Google tokens keyed by `sub`.

## Tool discovery of an introspecting server

When the gateway probes a server to discover its tools, there is no caller,
so there is no bearer to forward and no delegated token to issue. If the
server refuses unauthenticated requests, give it a static credential for that
path (it works the same with `auth_mode: delegated_token`):

```json
{
  "forward_headers": { "authorization": "authorization" },
  "static_headers":  { "authorization": "Bearer bmcp_sk_<a service key>" }
}
```

The static header is sent when nothing is forwarded, and the forwarded
header overrides it at call time. The server sees a service key during
discovery, which introspects as active.

## Session binding

When headers are forwarded, the gateway keys its upstream connections by the
forwarded values, not just by `sub`. User A's connection never serves user
B's request, and the same user presenting different credentials on two
endpoints gets two upstream bindings.

## Headers that are never forwarded

`host`, `content-length`, `cookie`, `x-api-key`, `mcp-session-id`, and
anything starting with `sec-` or `proxy-` are refused both at write time and
at runtime.

## Per-user upstream OAuth

Identity also flows the other way when the gateway holds OAuth tokens for a
server on behalf of each user (`identity_mode: per_user`). The server then
receives its own provider's bearer for that user and needs neither of the
mechanisms above. See [Servers](/manage/servers#upstream-oauth).
