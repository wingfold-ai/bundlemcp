# Management API

Everything the admin UI does goes through a versioned REST API under
`/api/v1`. The UI has no privileged side channel, so whatever you can click
you can script: a registrar that discovers containers and registers them, a
CI job that provisions endpoints, a dashboard that reads audit records.

## Documentation and types

| | |
|---|---|
| Interactive docs | `<public url>/api/v1/docs` |
| OpenAPI document | `<public url>/api/v1/openapi.json` |

Every request and response is a Pydantic model with described fields, so the
OpenAPI document is complete enough to generate a client. The admin UI's
TypeScript types are generated from it with `openapi-typescript`; do the
same in your language of choice.

## Authentication

Two credentials are accepted on every route:

- a **service API key** in `Authorization: Bearer bmcp_sk_…`;
- the **admin session cookie** a browser holds after logging in. Cookie
  calls from a browser must come from an origin in `BUNDLEMCP_WEB_ORIGINS`.

`GET /api/v1/me` reports which one authenticated the call, and is the one
route that answers a signed-in **non-admin** user too (with
`is_admin: false`), so a UI can render a "no access" page. Everything else
answers 401 without a credential and 403 for a non-admin user.

Endpoint-kind API keys are refused here; only `service` keys manage the
gateway.

## Conventions

**Resources are addressed by name.** Servers, bundles and endpoints use
their unique name in the path, not an id. Ids still exist and appear in
responses; API keys, users and consents are addressed by id.

**`PUT` is an idempotent upsert.** `PUT /api/v1/servers/{name}` creates the
server if it is missing and updates it otherwise; the path name and the body
`name` must match. Repeating the call with the same body changes nothing.
This is what lets a discovery loop converge by repeatedly putting desired
state, and it is why bootstrap files share the same schemas.

**Renames are explicit actions.** Changing a name changes tool prefixes or
public URLs, so it is a `POST …:rename?new_name=…` that refuses unless
`force=true` acknowledges the consequence.

**Lists are paginated.** `offset` and `limit` query parameters, default 50,
maximum 500. Responses have the shape
`{"items": [...], "total": n, "offset": o, "limit": l}`, ordered by creation
time then id, so paging is stable while resources are added.

**Errors are structured.** Validation failures answer 422 with the field
path and message; domain-rule violations (a reserved endpoint name, a
profile that forbids the given auth modes, a `per_user` server behind an
open endpoint) answer 4xx with a message that names the rule.

**Secrets are write-only.** Static header values, upstream OAuth client
secrets and API key values are accepted on write and never returned; key
values appear once, in the creation response.

## Routes

### Servers

| Method | Path | |
|---|---|---|
| `GET` | `/servers` | List. |
| `GET` | `/servers/{name}` | Read, including health and capabilities. |
| `PUT` | `/servers/{name}` | Upsert; probes and discovers tools, never blocks on a failed probe. |
| `DELETE` | `/servers/{name}` | Delete with tools and memberships. |
| `POST` | `/servers/{name}:rename?new_name=&force=` | Rename. |
| `POST` | `/servers/{name}:refresh-tools` | Re-probe and re-discover; returns counts. |
| `GET` | `/servers/{name}/tools` | The cached tools. |
| `GET` | `/servers/{name}/upstream-oauth` | Upstream OAuth status. |
| `PUT` | `/servers/{name}/upstream-oauth` | Set the upstream OAuth client. |
| `DELETE` | `/servers/{name}/upstream-oauth/token` | Disconnect the shared account. |

### Bundles

| Method | Path | |
|---|---|---|
| `GET` | `/bundles` | List. |
| `GET` | `/bundles/{name}` | Read. |
| `PUT` | `/bundles/{name}` | Upsert name and description. |
| `DELETE` | `/bundles/{name}` | Delete, together with its endpoints. |
| `GET` | `/bundles/{name}/servers` | Members with health. |
| `PUT` | `/bundles/{name}/servers/{server_name}` | Add or update a membership (`enabled`). |
| `DELETE` | `/bundles/{name}/servers/{server_name}` | Remove a membership. |
| `GET` | `/bundles/{name}/tools` | Every tool with its curation and presented name. |
| `PUT` | `/bundles/{name}/tools/{tool_id}` | Enable, disable, override. |

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
| `GET` | `/me` | Who is calling. |

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
    put(f"/api/v1/servers/{container.name}", {
        "name": container.name,
        "url": container.url,
        "description": container.labels.get("description"),
        "send_identity_header": True,
    })
put("/api/v1/bundles/fleet", {"name": "fleet", "description": "Every discovered server"})
for container in discover_mcp_containers():
    put(f"/api/v1/bundles/fleet/servers/{container.name}", {"enabled": True})
put("/api/v1/endpoints/fleet", {
    "name": "fleet", "bundle_name": "fleet", "profile": "claude", "auth_modes": ["oauth"],
})
```

Run it on a timer. Servers that are not up yet are stored with an error
status and probed again; nothing in the loop needs to wait.

The API never deletes what you do not ask it to delete, so a registrar that
wants to prune stale servers lists them and deletes explicitly.

## Browser callers

The API sets CORS headers only for origins in `BUNDLEMCP_WEB_ORIGINS`, and
cookie-authenticated mutations must present a matching `Origin` or
`Referer`. A browser application on another origin cannot use the admin
cookie; give it a service key on a backend instead.
