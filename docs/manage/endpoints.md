# Endpoints

An endpoint is a public URL that serves one bundle over Streamable HTTP. Create several for the same bundle to give each
kind of client its own surface: OAuth for claude.ai, re-annotated tools for ChatGPT, an API key for scripts, each with
its own rate limits.

The examples assume:

```bash
API=https://gw.example.com/api/v1
AUTH="Authorization: Bearer $SERVICE_KEY"
```

## URL

Every endpoint is served at:

```
<BUNDLEMCP_PUBLIC_URL>/<endpoint_name>/mcp
```

`POST` carries JSON-RPC. Handshake-era clients additionally use `GET` for the server-to-client stream and `DELETE` to
end a session, both with an `Mcp-Session-Id`; without one they answer 405. There is no `/sse` route and no REST bridge.

The endpoint page in the UI shows this URL with a copy button and the setup instructions for each client type.

## Creating an endpoint

In the UI an endpoint is created on the page of the bundle it exposes: open the bundle, and its **Endpoints** card lists
the existing ones and holds the create form. The **All endpoints** overview under Bundles shows every public URL across
bundles. Through the API:

```bash
curl -s -X PUT $API/endpoints/assistant -H "$AUTH" -H "Content-Type: application/json" -d '{
  "name": "assistant",
  "bundle_name": "assistant",
  "profile": "claude",
  "auth_modes": ["oauth"]
}'
```

| Field | Default | Meaning |
|---|---|---|
| `name` | required | Slug-safe and globally unique; becomes the URL path segment. |
| `bundle_name` | required | The bundle to serve. |
| `profile` | `default` | `default`, `claude` or `chatgpt`. |
| `auth_modes` | required | Non-empty list of `oauth`, `api_key`, `none`. |
| `allow_unauthenticated` | `false` | Must be `true` when `auth_modes` is `["none"]`. |
| `rate_limit` | none | See below. |
| `enabled` | `true` | A disabled endpoint answers 404 and keeps its configuration. |
| `force` | `false` | Acknowledge a rename. |

Reserved names are rejected: `api`, `oauth`, `.well-known`, `healthz`, `readyz`, `metrics`, `docs`, `login`, `consent`,
`static`.

## Auth modes

A request is accepted if it satisfies **any** listed mode.

| Mode | The client sends | Identity |
|---|---|---|
| `oauth` | `Authorization: Bearer <token issued by this gateway>` | The user's id |
| `api_key` | `Authorization: Bearer bmcp_sk_…` or `X-API-Key: bmcp_sk_…` | `api_key:<key id>` |
| `none` | nothing | anonymous |

When a request carries both a valid OAuth bearer and an API key, OAuth wins and that identity is used everywhere: rate
limiting, audit, metering, identity forwarding.

Endpoints that accept `oauth` appear in the users' catalogue, since a person can connect to them with their gateway
identity; endpoints that accept only `api_key` are for automation and stay out of it. See
[Authentication](/guide/authentication#caller-identity-who-is-calling-the-gateway).

An OAuth token is bound to the endpoint it was issued for. Presenting it at another endpoint fails with a 401 and the
same `WWW-Authenticate` challenge an unauthenticated request gets, which sends the client to re-authorise for that
endpoint.

Unauthenticated requests receive a 401 with a `WWW-Authenticate` challenge pointing at
`/.well-known/oauth-protected-resource/<name>/mcp`, which is how claude.ai discovers where to register and authorise.

`none` is only valid on its own, requires `allow_unauthenticated: true`, and cannot serve a bundle that contains a
`per_user` upstream OAuth server.

## Profiles

| Profile | Allowed `auth_modes` | Effect |
|---|---|---|
| `default` | any valid combination | Passthrough. |
| `claude` | exactly `["oauth"]` | Passthrough; guarantees the OAuth discovery surface claude.ai requires. See [claude.ai](/connect/claude). |
| `chatgpt` | must contain `oauth` or `api_key` | Presents every tool as read-only. See [ChatGPT](/connect/chatgpt). |

`GET /api/v1/endpoints/profiles` returns the list with a description and, for `chatgpt`, a warning the UI displays on
the endpoint page.

A profile is applied when the gateway builds the tools an endpoint serves, in this order: tools the bundle disabled
are removed first, then the profile reshapes what is left, then the bundle's per-tool overrides are applied. Because
the overrides come last, an explicit annotation override wins over the profile — for example a tool you mark
`readOnlyHint: false` stays marked that way on a `chatgpt` endpoint. `tools/list` and `tools/call` use the same result,
so a tool that is not listed cannot be called either.

::: warning The chatgpt profile changes what clients are told, not what tools do
A tool that deletes records is still called and still deletes. Only the annotations shown to ChatGPT say
`readOnlyHint: true`. The audit log records every call normally.
:::

## Rate limits

`rate_limit` holds two optional limits and two flags:

```json
{
  "rate_limit": {
    "endpoint":   { "limit": 3000, "window_seconds": 60 },
    "per_client": { "limit": 120,  "window_seconds": 60 },
    "include_initialize_list": false,
    "fail_closed": false
  }
}
```

| Field | Meaning |
|---|---|
| `endpoint` | Requests per window across all callers. |
| `per_client` | Requests per window per caller, keyed by OAuth user, else API key, else client IP on a `none` endpoint. |
| `include_initialize_list` | Count `initialize` and `tools/list` too. Off by default so client startup is never throttled. |
| `fail_closed` | Deny requests while Valkey is unreachable. Off by default: availability over throttling. |

Counting happens in Valkey with fixed windows and holds across replicas. A rejected request gets HTTP 429 with
`Retry-After`. Rejections are counted in metrics and logs, not in the audit log.

Omit `rate_limit` entirely for an unlimited endpoint.

## One bundle, several endpoints

The pattern the profile system exists for:

```bash
for spec in 'assistant claude ["oauth"]' 'assistant-gpt chatgpt ["oauth"]' 'assistant-ci default ["api_key"]'; do
  set -- $spec
  curl -s -X PUT $API/endpoints/$1 -H "$AUTH" -H "Content-Type: application/json" \
    -d "{\"name\":\"$1\",\"bundle_name\":\"assistant\",\"profile\":\"$2\",\"auth_modes\":$3}"
done
```

Three URLs, one curated tool set, three different contracts with clients.

## Renaming and disabling

Renaming changes the public URL and breaks every connected client. The rename route refuses unless forced:

```bash
curl -s -X POST "$API/endpoints/assistant:rename?new_name=helper&force=true" -H "$AUTH"
```

Prefer `enabled: false` to take an endpoint offline: it answers 404, keeps its configuration, and can be switched back
on.

`DELETE /api/v1/endpoints/{name}` removes the endpoint. OAuth tokens bound to it stop working.
