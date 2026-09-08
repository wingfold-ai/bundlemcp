# Identity for upstream servers

An MCP server behind the gateway usually wants to know **who** is calling:
to keep per-user state, apply quotas, or scope data. The gateway offers two
mechanisms with different trust levels, and one route for verifying.

## `X-MCP-User`: trusted on the internal network

When a server's `send_identity_header` is on (the default), every request the
gateway sends it carries:

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

## Forwarded bearer plus introspection: verifiable

For servers that must verify the caller, forward the client's bearer and let
the server ask the gateway whether it is valid:

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

When the gateway probes a server to discover its tools, there is no caller
and no bearer to forward. If the server refuses unauthenticated requests,
give it a static credential for that path:

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
