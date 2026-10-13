# Management API

Everything the admin UI does goes through a versioned REST API under `/api/v1`. The UI has no privileged side channel,
so whatever you can click you can script: a registrar that discovers containers and registers them, a CI job that
provisions endpoints, a dashboard that reads audit records.

## Documentation and types

| | |
|---|---|
| Interactive docs | `<public url>/api/v1/docs` |
| OpenAPI document | `<public url>/api/v1/openapi.json` |

Every request and response is a Pydantic model with described fields, so the OpenAPI document is complete enough to
generate a client. The admin UI's TypeScript types are generated from it with `openapi-typescript`; do the same in your
language of choice.

## Authentication

Two credentials are accepted on every route:

- a **service API key** in `Authorization: Bearer bmcp_sk_…`;
- the **admin session cookie** a browser holds after logging in. Cookie calls from a browser must come from an origin in
  `BUNDLEMCP_WEB_ORIGINS`.

`GET /api/v1/me` reports which one authenticated the call. It and the other `/api/v1/me/…` routes answer a signed-in
**non-admin** user too, which is all the web app needs to show them the catalogue.

Everything else requires an administrator, and the status codes are worth reading carefully because they are not the
obvious split:

| Status | When |
|---|---|
| `401` | No credential, an invalid credential, **or a signed-in user who is not an administrator** |
| `403` | An endpoint-kind API key, or a cookie-authenticated mutation from a disallowed origin |

A non-administrator therefore gets `401`, not `403`. If you are building a UI, do not treat `401` on `/api/v1` as
"session expired" — call `GET /api/v1/me`, which answers for any signed-in user, to tell "not logged in" from "logged
in, not an administrator". [Error responses](/integrate/errors) has the full table.

Endpoint-kind API keys are refused here; only `service` keys manage the gateway.

## Conventions

**Resources are addressed by name.** Servers, bundles and endpoints use their unique name in the path, not an id. Ids
still exist and appear in responses; API keys, users and consents are addressed by id.

**`PUT` is an idempotent upsert.** `PUT /api/v1/upstreams/{name}` creates the server if it is missing and updates it
otherwise; the path name and the body `name` must match. Repeating the call with the same body changes nothing. This is
what lets a discovery loop converge by repeatedly putting desired state, and it is why bootstrap files share the same
schemas.

**Renames are explicit actions.** Changing a name changes tool prefixes or public URLs, so it is a
`POST …:rename?new_name=…` that refuses unless `force=true` acknowledges the consequence.

**Top-level collections are paginated; nested ones are not.** `offset` and `limit` query parameters, default 50, maximum
500, with the shape `{"items": [...], "total": n, "offset": o, "limit": l}`, ordered by creation time then id, so paging
is stable while resources are added. That covers `/upstreams`, `/upstreams/{name}/tools`, `/bundles`, `/endpoints`,
`/api-keys`, `/users` and `/audit-records`.

These return a **bare JSON array** with no envelope, so a client that unwraps `.items` unconditionally breaks on them:

| Route | Returns |
|---|---|
| `GET /bundles/{name}/upstreams` | `[BundleMemberRead]` |
| `GET /bundles/{name}/tools` | `[BundleToolRead]` |
| `GET /endpoints/profiles` | `[EndpointProfileRead]` |
| `GET /users/{id}/consents` | `[ConsentRead]` |
| `GET /me/endpoints` | `[AvailableEndpointRead]` |
| `GET /me/bundles/{name}/tools` | `[CatalogueToolRead]` |
| `GET /me/bundles/{name}/prompts` | `[CataloguePromptRead]` |
| `GET /me/bundles/{name}/resources` | `[CatalogueResourceRead]` |

`GET /config` is a third shape again: a flat object of key → value.

**Errors are structured**, in four different shapes depending on what failed. [Error responses](/integrate/errors) is
the catalogue; the short version is that a domain-rule violation answers `{"detail": "<message>"}` naming the rule,
while request validation answers `422` with `detail` as a *list* of field errors.

## Stability

Within `/api/v1`:

- Routes and response fields are never removed or renamed. New optional request fields and new response fields may
  appear in any release, so treat unknown response fields as ignorable rather than erroring on them.
- A breaking change means a new prefix (`/api/v2`), not a change here.
- `METERING_PROTOCOL_VERSION` ([metering hook](/integrate/metering-hook)) moves independently of the gateway's own
  version.

There is no published release cadence or deprecation window yet — the gateway has no versioned releases at all (see
[Production deployment](/self-hosting/deploy#get-the-images)), so pin the commit or image digest you deployed and read
`git log` between upgrades.

**Secrets are write-only.** Static header values, upstream OAuth client secrets and API key values are accepted on write
and never returned; key values appear once, in the creation response.

## Routes

### Upstream servers

Upstream servers live under `/upstreams` (the short form of *upstream servers*), bundle members under
`/bundles/{name}/upstreams`.

| Method | Path | |
|---|---|---|
| `GET` | `/upstreams` | List. |
| `GET` | `/upstreams/{name}` | Read, including health and capabilities. |
| `PUT` | `/upstreams/{name}` | Upsert; probes and discovers tools, never blocks on a failed probe. |
| `DELETE` | `/upstreams/{name}` | Delete with tools and memberships. |
| `POST` | `/upstreams/{name}:rename?new_name=&force=` | Rename. |
| `POST` | `/upstreams/{name}:refresh-tools?prune=` | Re-probe and re-discover; returns counts. With `prune=true`, a successful probe also deletes the stale tools and their curation. |
| `GET` | `/upstreams/{name}/tools` | The cached tools, each flagged `stale` when its server no longer lists it. |
| `GET` | `/upstreams/{name}/upstream-oauth` | Upstream OAuth status. |
| `PUT` | `/upstreams/{name}/upstream-oauth` | Set the upstream OAuth client. |
| `DELETE` | `/upstreams/{name}/upstream-oauth/token` | Disconnect the shared account. |

### Bundles

| Method | Path | |
|---|---|---|
| `GET` | `/bundles` | List. |
| `GET` | `/bundles/{name}` | Read. |
| `PUT` | `/bundles/{name}` | Upsert name and description. |
| `DELETE` | `/bundles/{name}` | Delete, together with its endpoints. |
| `GET` | `/bundles/{name}/upstreams` | Members with health, in member order. |
| `PUT` | `/bundles/{name}/upstreams:order` | Set the member order; the list names every member once. |
| `PUT` | `/bundles/{name}/upstreams/{server_name}` | Add or update a membership (`enabled`); a new member is appended. |
| `DELETE` | `/bundles/{name}/upstreams/{server_name}` | Remove a membership. |
| `GET` | `/bundles/{name}/tools` | Every tool with its curation, presented name and staleness. |
| `PUT` | `/bundles/{name}/tools/{tool_id}` | Enable, disable, override. |
| `GET` | `/bundles/{name}/prompts` | The bundle's own prompts, paginated. |
| `GET` `PUT` `DELETE` | `/bundles/{name}/prompts/{prompt}` | Read, create or replace, delete one prompt. |
| `GET` | `/bundles/{name}/resources` | The bundle's own resources, paginated. |
| `GET` `PUT` `DELETE` | `/bundles/{name}/resources/{resource}` | Read, create or replace, delete one resource; the name may contain `/`. A resource a prompt embeds answers `409` to `DELETE`. |

### Endpoints

| Method | Path | |
|---|---|---|
| `GET` | `/endpoints` | List. |
| `GET` | `/endpoints/profiles` | The built-in profiles with descriptions and warnings. |
| `GET` | `/endpoints/{name}` | Read. |
| `PUT` | `/endpoints/{name}` | Upsert. |
| `DELETE` | `/endpoints/{name}` | Delete. |
| `POST` | `/endpoints/{name}:rename?new_name=&force=` | Rename. |

### Access

| Method | Path | |
|---|---|---|
| `GET` | `/api-keys` | List (prefixes only). |
| `POST` | `/api-keys` | Create; the value is in this response only. |
| `POST` | `/api-keys/{id}:deactivate` | Stop accepting a key. |
| `DELETE` | `/api-keys/{id}` | Delete. |
| `GET` | `/users` | List provisioned users. |
| `POST` | `/users/{id}:deactivate` | Revoke everything the user holds. |
| `GET` | `/users/{id}/consents` | The user's OAuth consents. |
| `DELETE` | `/users/{id}/consents/{consent_id}` | Revoke a consent and its tokens. |
| `GET` | `/me` | Who is calling. Answers for any signed-in user, admin or not. |
| `GET` | `/me/endpoints` | The catalogue: enabled endpoints accepting OAuth, with their URLs. Any signed-in user. |
| `GET` | `/me/bundles/{name}/tools` | The tools one catalogue bundle serves. Any signed-in user; 404 rather than 403 when no endpoint would let this caller reach the bundle. |
| `GET` | `/me/bundles/{name}/prompts`, `/me/bundles/{name}/resources` | The prompts and documents the bundle itself offers, by title and description. Same access rule as the tools. |

### Operations

| Method | Path | |
|---|---|---|
| `GET` | `/audit-records` | Filterable, paginated audit log. |
| `GET` | `/config` | Runtime settings in effect. |
| `PUT` | `/config/{key}` | Set one (`{"value": …}`), type-checked. |
| `DELETE` | `/config/{key}` | Reset one to its default. |

## A registrar loop

The upsert semantics make a reconciling registrar short. In pseudocode:

```python
for container in discover_mcp_containers():
    put(f"/api/v1/upstreams/{container.name}", {
        "name": container.name,
        "url": container.url,
        "description": container.labels.get("description"),
        "send_identity_header": True,
    })
put("/api/v1/bundles/fleet", {"name": "fleet", "description": "Every discovered server"})
for container in discover_mcp_containers():
    put(f"/api/v1/bundles/fleet/upstreams/{container.name}", {"enabled": True})
put("/api/v1/endpoints/fleet", {
    "name": "fleet", "bundle_name": "fleet", "profile": "oauth_only", "auth_modes": ["oauth"],
})
```

Run it on a timer. Servers that are not up yet are stored with an error status and probed again; nothing in the loop
needs to wait.

The API never deletes what you do not ask it to delete, so a registrar that wants to prune stale servers lists them and
deletes explicitly.

## Browser callers

The API sets CORS headers only for origins in `BUNDLEMCP_WEB_ORIGINS`, and cookie-authenticated mutations must present a
matching `Origin` or `Referer`. A browser application on another origin cannot use the admin cookie; give it a service
key on a backend instead.
