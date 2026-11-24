---
description: "Create and manage bundlemcp API keys for scripts, CI, automation platforms, server-to-server callers and
  the management API."
---

# API keys

API keys authenticate anything that cannot do an OAuth flow: scripts, CI, automation platforms, server-to-server
callers, and the management API itself.

## Two kinds

| Kind | May call |
|---|---|
| `endpoint` | MCP endpoints that list `api_key` in their `auth_modes`, restricted to the endpoints in its scope. |
| `service` | Everything an `endpoint` key can, plus the management API under `/api/v1`. |

Use `service` keys for automation that configures the gateway and for upstream servers that call the introspection
route, limited to the [scopes](#scopes) each one needs. Hand out `endpoint` keys to anything that only needs to use
tools.

## Scopes

A service key can be limited to scopes. Without scopes it may do everything, as every service key could before scopes
existed. With scopes, it may call only what they open; every other route answers 403.

| Scope | Opens |
|---|---|
| `introspect` | Token introspection, `POST /oauth/introspect`. |
| `read` | Reading bundles (members, tools, curation, prompts, resources), endpoints and profiles, upstreams (tools, upstream-OAuth status), API keys and runtime settings. |
| `bundles:write` | Changing bundles: create, rename, delete, members and their order, tool curation, member-prompt and member-resource curation, bundle prompts and resources. |
| `endpoints:write` | Changing endpoints: create, rename, delete. |
| `upstreams:write` | Changing upstream servers: create, rename, delete, inspect, import from `server.json`, refresh tools, and upstream-OAuth settings, connect and token deletion. |
| `keys:manage` | Creating, activating, deactivating and deleting API keys, but only service keys whose scopes the caller itself holds. |
| `mcp` | Calling tools on endpoints that accept API keys. A scoped key without it never authenticates an MCP call. |

Audit records, configuration export and import, the inspector, live logs, users, changing runtime settings, `/metrics`
and the `/api/v1/me` routes are for administrators and service keys without scopes only.

Two examples: a server that only verifies forwarded bearers needs `introspect`; a job that copies bundles and gives
them endpoints needs `read`, `bundles:write` and `endpoints:write`.

```bash
curl -s https://gw.example.com/api/v1/api-keys \
  -H "Authorization: Bearer $SERVICE_KEY" -H "Content-Type: application/json" \
  -d '{"name": "edge-filter", "kind": "service", "scopes": ["introspect"]}'
```

Scopes cannot be changed on an existing key: create a new key and delete the old one. An endpoint key takes no scopes,
and an unknown scope is refused with 422.

Keys are created by administrators only. A person using an endpoint does not get a key: they connect their MCP client
through OAuth, and the call is attributed to them. Keys identify a script or a service, never a person; see
[Authentication](/guide/authentication) for how the kinds of credential fit together, and
[Administrators and users](/guide/authentication#administrators-and-users) for what each role may do.

## Creating a key

From **API keys** in the UI, or:

```bash
curl -s -X POST https://gw.example.com/api/v1/api-keys \
  -H "Authorization: Bearer $SERVICE_KEY" -H "Content-Type: application/json" \
  -d '{"name": "nightly-report", "kind": "endpoint", "endpoint_ids": ["<endpoint id>"]}'
```

The response is the only time the value is shown:

```json
{
  "id": "…",
  "name": "nightly-report",
  "kind": "endpoint",
  "key": "bmcp_sk_…",
  "key_prefix": "bmcp_sk_3f9a",
  "endpoint_ids": ["…"],
  "is_active": true
}
```

Only a hash and the display prefix are stored. A lost key is replaced, not recovered.

`endpoint_ids` scopes an `endpoint` key to specific endpoints; an empty list means every endpoint. Endpoint ids come
from `GET /api/v1/endpoints`. In the admin UI the **API keys** page shows an endpoint picker for an `endpoint` key: tick
the endpoints it may call, or none for every endpoint. The list shows each key's scope.

## Using a key

Against an MCP endpoint, either header works:

```bash
curl https://gw.example.com/assistant-ci/mcp \
  -H "Authorization: Bearer bmcp_sk_…" …
curl https://gw.example.com/assistant-ci/mcp \
  -H "X-API-Key: bmcp_sk_…" …
```

Against the management API, only `Authorization: Bearer` with a `service` key. Keys are never accepted in a query
parameter.

The caller identity of a key is `api_key:<id>`. That is what appears in audit records, what the metering hook receives,
what `X-MCP-User` carries upstream, and what the introspection route reports for the key.

## Deactivating, re-activating and deleting

`POST /api/v1/api-keys/{id}:deactivate` keeps the record but stops accepting the key, and
`POST /api/v1/api-keys/{id}:activate` accepts it again; `DELETE /api/v1/api-keys/{id}` removes it. All three take
effect on every replica within the cross-replica signalling budget, not after a cache expiry. The **API keys** page
offers *Deactivate* on an active key and *Re-activate* on an inactive one.

`last_used_at` is maintained coarsely (at most about once a minute per key) so you can spot keys nobody uses before
revoking them.

## The first service key

A fresh gateway has no keys and no admin session, so the management API would be unreachable headlessly.
`BUNDLEMCP_INITIAL_SERVICE_KEY` solves that: at start-up, if no service key exists at all, the gateway stores the value
of that variable as a `service` key named `initial-service-key`. As long as at least one service key exists, active or
deactivated, the variable is ignored.

### Do I need to replace it?

Not necessarily. The initial key is an ordinary service key and keeps working. Its only weakness is where its value
lives: in your deployment configuration, for as long as the variable is set, readable by anyone who can read that
configuration. Replace it if:

- the value was ever written somewhere more people can read than should administer the gateway — committed to a
  repository, pasted into a ticket, printed in CI logs; or
- you want the key your automation uses to be one that appears in no configuration file.

If neither applies, keeping it is fine.

### How to replace it

1. Create a new key with kind **service**: on the **API keys** page, or with
   `POST /api/v1/api-keys` and `{"name": "automation", "kind": "service"}` (see [Creating a key](#creating-a-key)).
   Copy the value; it is shown once.
2. Switch your scripts and automation to the new key, and check that they work.
3. Delete the key named `initial-service-key`: **Delete** on the **API keys** page, or
   `DELETE /api/v1/api-keys/{id}` with the id from `GET /api/v1/api-keys`.
4. Remove `BUNDLEMCP_INITIAL_SERVICE_KEY` from your configuration. While another service key exists it is ignored, but
   the gateway checks it at every start: if one day no service key is left, it would bring the old value back.

## Limits

Keys have no expiry date and no per-key rate limit. Use the endpoint's `per_client` limit, where the key is the client,
and revoke keys on a schedule of your own.
