# Bundles and tool curation

A bundle composes any number of registered servers into one virtual MCP
server and decides how their tools are presented. Endpoints then expose the
bundle to clients.

The examples assume:

```bash
API=https://gw.example.com/api/v1
AUTH="Authorization: Bearer $SERVICE_KEY"
```

## Creating a bundle

```bash
curl -s -X PUT $API/bundles/assistant -H "$AUTH" -H "Content-Type: application/json" -d '{
  "name": "assistant",
  "description": "Weather, notes and calendar for the personal assistant"
}'
```

The `description` is served to clients as the MCP `instructions` field of
the virtual server, so write it for the model that will read it: what the
bundle is for and how the tools relate.

## Members

Add a server to the bundle with `PUT /api/v1/bundles/{name}/servers/{server_name}`:

```bash
curl -s -X PUT $API/bundles/assistant/servers/weather -H "$AUTH" \
  -H "Content-Type: application/json" -d '{"enabled": true}'
```

The same route with `"enabled": false` **hides** every tool of that server
from the bundle without removing the membership or its per-tool curation.
`DELETE` on the route removes the membership.

`GET /api/v1/bundles/{name}/servers` lists members with their health, so you
can see at a glance which upstream is down.

A bundle cannot contain one of this gateway's own endpoints as a member;
that self-reference is rejected when the membership is created.

## How tools are named

Every tool of a member is presented as `<server_name>__<tool_name>`. Because
server names never contain `__`, the gateway splits a presented name on the
first `__` to find the owning server, and the pair is always unique. The
`weather` server's `forecast` tool is `weather__forecast` in every bundle.

Prompts follow the same rule. Resources are keyed by URI, which is passed
through unchanged; on a collision the first enabled member wins.

## Curating tools

`GET /api/v1/bundles/{name}/tools` lists every tool the bundle could serve,
with the upstream definition, the current overrides, and `presented_name`,
the name clients actually see.

`PUT /api/v1/bundles/{name}/tools/{tool_id}` sets the curation of one tool:

```bash
curl -s -X PUT $API/bundles/assistant/tools/$TOOL_ID -H "$AUTH" -H "Content-Type: application/json" -d '{
  "enabled": true,
  "override_name": "get_forecast",
  "override_description": "Seven-day forecast for a city. Prefer this over current_conditions for planning questions.",
  "override_annotations": { "readOnlyHint": true }
}'
```

| Field | Effect |
|---|---|
| `enabled: false` | The tool is absent from `tools/list` and a call to it is rejected with an MCP error. |
| `override_name` | Replaces the whole presented name. Must be unique within the bundle, including against other servers' prefixed names, and match `[a-zA-Z0-9_-]+`. |
| `override_title` | Replaces the display title. |
| `override_description` | Replaces the description the model reads. This is the most useful override: tailor what the model is told about the tool to the bundle's purpose. |
| `override_annotations` | Shallow-merged over the upstream annotations. Set a key to `null` to remove it. |

Curation is **per bundle**: the same server can present differently in two
bundles. Explicit annotation overrides also win over the `chatgpt` profile's
rewrite, so you can keep one tool truthfully marked destructive on a ChatGPT
endpoint if you accept that ChatGPT may then refuse it.

The bundle page in the UI shows the same table with enable toggles and
inline override editing, and flags tools that are overridden or stale.

## Changes are live

Membership, enable flags and overrides take effect for new requests
immediately, on every replica, without a restart. Sessions that support it
receive a `notifications/tools/list_changed` so the client refreshes its
tool list.

## Renaming and deleting

Bundle names are the natural key for bootstrap and for the API. Renaming a
bundle makes external automation keyed on the old name treat it as a new
bundle; endpoints are unaffected because they reference the bundle by id.
The UI warns before a rename.

`DELETE /api/v1/bundles/{name}` deletes the bundle **and every endpoint that
serves it**. Disable the endpoints first if you want a reversible step.
