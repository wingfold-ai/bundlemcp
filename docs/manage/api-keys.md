# API keys

API keys authenticate anything that cannot do an OAuth flow: scripts, CI,
automation platforms, server-to-server callers, and the management API
itself.

## Two kinds

| Kind | May call |
|---|---|
| `endpoint` | MCP endpoints that list `api_key` in their `auth_modes`, restricted to the endpoints in its scope. |
| `service` | Everything an `endpoint` key can, plus the management API under `/api/v1`. |

Use `service` keys for automation that configures the gateway and for
upstream servers that call the introspection route. Hand out `endpoint` keys
to anything that only needs to use tools.

Keys are created by administrators only. A person using an endpoint does not
get a key: they connect their MCP client through OAuth, and the call is
attributed to them. Keys identify a script or a service, never a person; see
[Roles and identity](/guide/roles-and-identity).

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

Only a hash and the display prefix are stored. A lost key is replaced, not
recovered.

`endpoint_ids` scopes an `endpoint` key to specific endpoints; an empty list
means every endpoint. Endpoint ids come from `GET /api/v1/endpoints`.

## Using a key

Against an MCP endpoint, either header works:

```bash
curl https://gw.example.com/assistant-ci/mcp \
  -H "Authorization: Bearer bmcp_sk_…" …
curl https://gw.example.com/assistant-ci/mcp \
  -H "X-API-Key: bmcp_sk_…" …
```

Against the management API, only `Authorization: Bearer` with a `service`
key. Keys are never accepted in a query parameter.

The caller identity of a key is `api_key:<id>`. That is what appears in
audit records, what the metering hook receives, what `X-MCP-User` carries
upstream, and what the introspection route reports for the key.

## Deactivating and deleting

`POST /api/v1/api-keys/{id}:deactivate` keeps the record but stops accepting
the key; `DELETE /api/v1/api-keys/{id}` removes it. Both take effect on every
replica within the cross-replica signalling budget, not after a cache
expiry.

`last_used_at` is maintained coarsely (at most about once a minute per key)
so you can spot keys nobody uses before revoking them.

## The first service key

A fresh gateway has no keys and no admin session, so the management API
would be unreachable headlessly. `BUNDLEMCP_INITIAL_SERVICE_KEY` solves the
bootstrap problem: on the first boot with no service key present, the
gateway stores the hash of that value as a `service` key. Once any service
key exists the variable is ignored, so create your real keys through the
API and retire the initial one.

## Limits

Keys have no expiry date and no per-key rate limit. Use the endpoint's
`per_client` limit, where the key is the client, and revoke keys on a
schedule of your own.
