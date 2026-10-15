# Bundles and tool curation

A bundle composes any number of registered servers into one virtual MCP server and decides how their tools are
presented. Endpoints then expose the bundle to clients.

The examples assume:

```bash
API=https://gw.example.com/api/v1
AUTH="Authorization: Bearer $SERVICE_KEY"
```

## Creating a bundle

```bash
curl -s -X PUT $API/bundles/assistant -H "$AUTH" -H "Content-Type: application/json" -d '{
  "name": "assistant",
  "description": "Weather, notes and calendar for the personal assistant",
  "overview": "Everything the assistant needs for day-to-day planning.\n\nForecasts come from the weather server, notes and calendar from your own Nextcloud. Connecting this bundle does not give it access to anything you have not connected yourself."
}'
```

A bundle carries **two** descriptions, and they have different readers. Getting
them the wrong way round is the common mistake:

| Field | Written for | Where it appears |
|---|---|---|
| `description` | The **model** | The MCP `instructions` field of the virtual server. Keep it short and functional: what the bundle is for and how its tools relate. |
| `overview` | A **person** | The catalogue entry a user reads before connecting. Long-form plain text, paragraphs separated by blank lines. |

Write `description` for the model that will read it on every session, and
`overview` for the human deciding whether to connect at all. Neither is
required.

The catalogue shows the overview alongside the tools the bundle serves after
curation, so a user can see what they are connecting before they connect it.
Tools are listed by title and description — the two fields written for a reader
— rather than by their prefixed name, which is how a model addresses them.

A bundle is only readable this way through an endpoint the reader could actually
use: a bundle with no OAuth endpoint answers **not found** rather than
forbidden, so a user cannot learn that a bundle exists if they have no way in.

## Members

Add a server to the bundle with `PUT /api/v1/bundles/{name}/upstreams/{server_name}`:

```bash
curl -s -X PUT $API/bundles/assistant/upstreams/weather -H "$AUTH" \
  -H "Content-Type: application/json" -d '{"enabled": true}'
```

The same route with `"enabled": false` **hides** every tool of that server from the bundle without removing the
membership or its per-tool curation. `DELETE` on the route removes the membership.

`GET /api/v1/bundles/{name}/upstreams` lists members with their health, so you can see at a glance which upstream is
down.

Members are **ordered**. A new member joins at the end, and the list above comes back in that order. The order decides
who answers first wherever more than one member could: the first member listing a resource URI is the one that serves
it. Set it with the whole list:

```bash
curl -s -X PUT $API/bundles/assistant/upstreams:order -H "$AUTH" \
  -H "Content-Type: application/json" -d '{"upstreams": ["weather", "calendar"]}'
```

The list must name every member exactly once, or the request answers `422` and nothing changes. A bootstrap document's
`upstreams` list puts the members it names first, in its order. The bundle page has up and down buttons for the same.

Do not add an upstream whose URL is one of this gateway's own endpoints: nothing refuses that self-reference yet, and
a call through it re-enters the gateway until a timeout stops it.

## How tools are named

Every tool of a member is presented as `<server_name>__<tool_name>`. Because server names never contain `__`, the
gateway splits a presented name on the first `__` to find the owning server, and the pair is always unique. The
`weather` server's `forecast` tool is `weather__forecast` in every bundle.

A member's prompts follow the same rule. Its resources are keyed by URI, which is passed through unchanged; on a
collision the first enabled member in member order wins. The bundle's own prompts and resources are named differently;
see below.

## Curating tools

`GET /api/v1/bundles/{name}/tools` lists every tool the bundle could serve, with the upstream definition, the current
overrides, and `presented_name`, the name clients actually see.

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
| `override_name` | Replaces the whole presented name. Must match `[a-zA-Z0-9_-]+` and differ from every other name the bundle presents, override or prefixed `server__tool`; a clash answers `409` naming the tool that holds the name. |
| `override_title` | Replaces the display title. |
| `override_description` | Replaces the description the model reads. This is the most useful override: tailor what the model is told about the tool to the bundle's purpose. |
| `override_annotations` | Shallow-merged over the upstream annotations. Set a key to `null` to remove it. |

Curation is **per bundle**: the same server can present differently in two bundles. Explicit annotation overrides also
win over the `write_as_read` profile's rewrite, so you can keep one tool truthfully marked destructive on a ChatGPT
endpoint if you accept that ChatGPT may then refuse it.

The PUT replaces the tool's whole curation: a field left out is cleared. Send every override you want to keep.

Presented names stay unique when the bundle's prefixed names change, too. Adding a member, or renaming a member
upstream, answers `409` when one of its tools would be presented under a name an override already holds; rename or
clear the override first. Only discovery cannot be refused: if an upstream adds a tool whose prefixed name an override
already holds, the override keeps the name, the new tool is not served, and the gateway logs
`bundle.presented_name_collision`.

The listing also reports `override_annotations` and `stale`. A stale tool is one its upstream no longer lists
([stale tools](./servers#stale-tools)); it is not served, but its curation is kept for when it comes back.

The bundle page in the UI shows the same table with enable toggles and inline editing of every override, name, title,
description and annotations (as JSON). Saving a row sends all of them, so it never clears an override set through the
API. Rows are flagged when overridden, when their member is disabled, and when stale.

## The bundle's own prompts and documents {#bundle-prompts-and-documents}

Tools come from the members, but the context that tells a model how to use them for this bundle's purpose — worked
examples, a house style, the conventions of the domain — is written on the bundle itself. A bundle can own **prompts**
(message templates a user picks in their client) and **resources** (documents the client reads into the conversation).
The gateway stores them with the bundle and serves them without contacting any upstream, so they cost nothing for an
upstream that scales to zero, and a bundle with no members at all can still serve them.

The bundle's `description` stays the short note sent on every session; prompts and resources hold the longer material a
client pulls in when it needs it.

::: warning Not secret
Every caller of every endpoint of the bundle can read its prompts and resources, and so can the model. Never put a
credential or anything private in them.
:::

### Resources

```bash
curl -s -X PUT $API/bundles/charts/resources/guides/style -H "$AUTH" -H "Content-Type: application/json" -d '{
  "name": "guides/style",
  "title": "House chart style",
  "mime_type": "text/markdown",
  "content": "# House style\n\n- Revenue is always blue.\n- Label every axis, with units."
}'
```

A resource name may be organised in folders with `/`, as above. Clients read it as `bundle://resources/<name>` — here
`bundle://resources/guides/style`. The URI carries no bundle name, so renaming the bundle does not change it. The
content is text: `text/markdown` (the default), `text/plain`, `text/csv`, `application/json` or `application/yaml`.

### Prompts

```bash
curl -s -X PUT $API/bundles/charts/prompts/plot -H "$AUTH" -H "Content-Type: application/json" -d '{
  "name": "plot",
  "title": "Plot a series",
  "description": "Draw one series in the house style",
  "arguments": [
    {"name": "series", "required": true},
    {"name": "kind", "values": ["bar", "line", "area"]}
  ],
  "messages": [
    {"role": "user", "text": "Plot {{series}} as a {{kind}} chart."},
    {"role": "user", "resource": "guides/style"}
  ]
}'
```

- **Names have no server prefix.** Clients see `plot`, not `something__plot`. A bundle prompt name may not contain `__`,
  so it can never collide with a member's prefixed prompt.
- **Placeholders are plain substitution.** `{{series}}` is replaced with the value the client supplies; an optional
  argument left out becomes the empty string, and a missing required one is refused with an error naming it. There are
  no expressions or loops, and a value is inserted as written, never expanded again.
- **A message can embed a resource** of the same bundle instead of carrying text; the client receives the document in
  full.
- **`values` are completions.** A client that offers completion suggests them as the user types (case-insensitive
  prefix match).

A write is rejected, with a message saying why, when a placeholder names an argument that is not declared or a message
embeds a resource the bundle does not have. A resource a prompt embeds cannot be deleted until the prompt stops
embedding it.

### Routes and limits

| Method | Route | |
|---|---|---|
| `GET` | `/bundles/{name}/prompts`, `/bundles/{name}/resources` | Paginated, in name order. |
| `GET` `PUT` `DELETE` | `/bundles/{name}/prompts/{prompt}` | `PUT` creates or replaces by name. |
| `GET` `PUT` `DELETE` | `/bundles/{name}/resources/{resource}` | The resource name may contain `/`. |

A bundle holds at most **100 prompts** and **200 resources**, a prompt at most **64 KiB** of message text, a resource at
most **256 KiB**, and all of a bundle's resources together at most **4 MiB**. A write over a limit is refused with a
message naming it; nothing is truncated.

The bundle page in the admin UI edits both, previews a prompt rendered with sample arguments, and previews a resource as
Markdown. The catalogue lists them by title and description, so a user sees what context the bundle offers before
connecting it. A [bootstrap document](../self-hosting/bootstrap.md) can carry them inside the bundle entry.

### What a client sees

`prompts/list` and `resources/list` return the bundle's own entries first, in name order, then the members'. A
`prompts/get` for a name without `__`, and a `resources/read` of a `bundle:` URI, are answered by the bundle alone: an
unknown one is not found, and no member is asked. A member resource whose URI happens to use the `bundle:` scheme is
hidden behind the bundle's own. Endpoint profiles do not rewrite bundle prompts or resources, and reading them is not
written to the audit log, which records tool calls.

## Changes are live

Membership, enable flags, overrides, prompts and resources take effect for new requests immediately, on every replica,
without a restart. Sessions that support it receive a `notifications/tools/list_changed` so the client refreshes its
tool list, and a `notifications/prompts/list_changed` or `notifications/resources/list_changed` when the bundle's own
prompts or resources change.

## Renaming and deleting

Bundle names are the natural key for bootstrap and for the API. Renaming a bundle makes external automation keyed on the
old name treat it as a new bundle; endpoints are unaffected because they reference the bundle by id. The UI warns before
a rename.

`DELETE /api/v1/bundles/{name}` deletes the bundle **and every endpoint that serves it**. Disable the endpoints first if
you want a reversible step.
