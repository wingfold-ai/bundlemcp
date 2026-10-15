# bundles Specification

## Purpose

Composing upstreams into one virtual MCP server, and curating what it presents. A bundle combines several upstreams
under one set of prefixed, collision-free tool names and routes each call back to its owner. Per bundle, an admin
decides which tools are shown and how: enable flags, name, title, description and annotation overrides. A bundle can
also carry prompts and resources of its own, written by an admin and served without contacting any upstream, beside the
members' prompts and resources, which pass through live. The catalogue overview a user reads before connecting belongs
here too.

Where a bundle is reachable, by whom and with which client quirks is the endpoints slice.

It merges what were separate specs until 2026-10-13: Bundles, Tool curation, Bundle prompts and resources.

## Requirements

### Requirement: BND-1 Bundle identity and instructions
A bundle MUST have a unique slug-safe `name`, a `description`, and a set of member servers, which the gateway orders by
server name wherever order matters. The `description` is served as the MCP `instructions` field of the virtual server.

#### Scenario: Description is served as instructions
- **WHEN** a client initializes against an endpoint of the bundle (or calls `server/discover`)
- **THEN** the result's `instructions` field carries the bundle's `description`

#### Scenario: Members are listed in name order
- **WHEN** `GET /api/v1/bundles/{name}/upstreams` is called for a bundle with members `zeta` and `alpha`
- **THEN** `alpha` is listed before `zeta`

### Requirement: BND-2 Prefixed tool names
Tool naming: every exposed tool MUST be `<server_name>__<tool_name>` (double underscore separator). Server names are
slug-safe and MUST NOT contain `__` ([ARC-19](../architecture/spec.md)), so parsing is unambiguous even when the
upstream tool name itself contains `__`: **split on the first `__`** — everything after it is the tool name. The
combination is guaranteed unique because `(server, tool)` is unique. Prefixing happens before overrides
([bundles](../bundles/spec.md)) are applied.

#### Scenario: Tools are listed with their server prefix
- **WHEN** a bundle has member `weather` with upstream tool `forecast`
- **THEN** `tools/list` on its endpoint lists `weather__forecast`

#### Scenario: Upstream double underscores survive
- **WHEN** member `weather` has upstream tool `get__hourly`
- **THEN** it is presented as `weather__get__hourly` and a call to that name reaches upstream tool `get__hourly`

### Requirement: BND-3 Call routing
Call routing MUST parse the prefix (first-`__` rule, or resolve an override name via its `BundleTool` mapping first —
[BND-14](../bundles/spec.md)), resolve the member server, verify the tool is enabled in this bundle, and forward
the call with the original (un-prefixed, un-overridden) tool name.

#### Scenario: A prefixed call reaches the owning upstream
- **WHEN** a client calls `tools/call` with name `weather__forecast`
- **THEN** the gateway calls tool `forecast` on member `weather`

#### Scenario: An override name routes back
- **WHEN** a tool has `override_name: get_weather` in the bundle and a client calls `get_weather`
- **THEN** the gateway calls the original upstream tool name on its member

#### Scenario: Unknown or disabled tool is rejected
- **WHEN** a client calls a tool name that is unknown or disabled in the bundle
- **THEN** the gateway answers a JSON-RPC `Invalid params` error `Unknown tool: …`, records a denied audit entry, and no
  upstream is contacted

### Requirement: BND-4 Disabled membership
`BundleServer.enabled=false` MUST remove all of a server's tools from the bundle's `tools/list` and block calls to them,
without deleting the membership or its `BundleTool` curation.

#### Scenario: Disabling a member hides and blocks its tools
- **WHEN** membership `b1`/`weather` is set to `enabled: false`
- **THEN** no `weather__*` tool is listed on `b1`'s endpoints and a call to one is rejected as unknown

#### Scenario: Re-enabling restores curation
- **WHEN** the membership is enabled again
- **THEN** the tools reappear with their previous `BundleTool` overrides and enable flags

### Requirement: BND-6 Management API and UI
Bundle CRUD + membership management MUST be available in the management API and UI; members are addressed as
`/bundles/{name}/upstreams/{upstream_name}` ([UPS-16](../upstreams/spec.md)).

#### Scenario: Adding and removing a member
- **WHEN** `PUT /api/v1/bundles/b1/upstreams/weather` is called with `{"enabled": true}` and later
  `DELETE /api/v1/bundles/b1/upstreams/weather`
- **THEN** `weather` is first a member of `b1` and then no longer is

#### Scenario: Path and body name must agree
- **WHEN** `PUT /api/v1/bundles/b1` is called with a body whose `name` is `b2`
- **THEN** the response is `422`

### Requirement: BND-7 Changes apply live
Changes to a bundle (membership, enable flags, overrides) MUST take effect for new requests without a gateway restart;
live sessions pick up changes on their next `tools/list`, and the gateway SHALL send a
`notifications/tools/list_changed` on every open stream that watches the bundle (a handshake client's GET stream, a
stateless client's `subscriptions/listen` stream), on whichever replica holds it.

#### Scenario: A curation change is visible on the next list
- **WHEN** a tool is disabled in bundle `b1`
- **THEN** the next `tools/list` on any endpoint of `b1` omits it, without a restart

#### Scenario: Open streams are told to re-list
- **WHEN** a client holds an open stream on an endpoint of `b1` and a member of `b1` is enabled or disabled
- **THEN** the client receives `notifications/tools/list_changed` on that stream

### Requirement: BND-8 Prompt and resource passthrough
Resources and prompts of member servers MUST be **uncurated passthrough** (tools are the curated surface); they are
fetched **live** from members per request and are not cached ([upstreams](../upstreams/spec.md)). Only
members whose capabilities snapshot ([UPS-22](../upstreams/spec.md)) advertises the capability a method belongs to
are asked — `prompts` for `prompts/*`, `resources` for `resources/*`, `completions` for `completion/complete` — so a
member without it, or one never successfully discovered, is not contacted and contributes nothing
([ADR-0043](../../../docs/adr/0043-contact-upstreams-only-with-a-reason.md)). Routing rules:

- **Prompts** carry a name, so they are **always prefixed** `<server_name>__<prompt_name>` (BND-2 scheme);
  `prompts/get` and completion prompt-refs de-prefix on the first `__` to find the owning member.
- **Resources** are keyed by opaque URI, not a prefixable name, so URIs are passed through **unchanged**.
  `resources/list` (and `resources/templates/list`) merge members' entries verbatim, de-duplicating by URI (first
  enabled member in server-name order wins, collisions logged). `resources/read`, `resources/subscribe`, and
  resource-template completions resolve the owning member by **fan-out** — trying enabled members in server-name order
  and taking the first that owns the URI.
- Completions are routed per [PROT-9](../protocol/spec.md).

Prompts and resources authored on the bundle itself, served beside this passthrough, are specified in
[bundles](../bundles/spec.md).

#### Scenario: Member prompts are prefixed and de-prefixed
- **WHEN** member `weather` offers prompt `daily` and a client calls `prompts/list` then `prompts/get` with
  `weather__daily`
- **THEN** the list shows `weather__daily` and the get is forwarded to `weather` as `daily`

#### Scenario: Prompt of an unknown member is rejected
- **WHEN** a client calls `prompts/get` with `nosuch__daily` and the bundle has no enabled member `nosuch` that
  advertises `prompts`
- **THEN** the gateway answers a JSON-RPC `Invalid params` error `unknown prompt: …` and contacts no upstream

#### Scenario: A member without the capability is not contacted
- **WHEN** a member's capability snapshot does not advertise `resources` and a client calls `resources/list`
- **THEN** that member receives no request

#### Scenario: Resource URIs pass through unchanged
- **WHEN** a member lists resource `file:///a.txt` and a client reads it
- **THEN** the URI is listed and read verbatim, routed to the first member that owns it

### Requirement: BND-9 Advertised capabilities
The capability set the bundle advertises at `initialize` MUST be computed per
[PROT-11](../protocol/spec.md).

#### Scenario: Capabilities come from the members' snapshots
- **WHEN** a client initializes against an endpoint of a bundle whose only member advertises `prompts`
- **THEN** the advertised capabilities include `prompts`, computed from the stored snapshot without contacting the
  member

### Requirement: BND-10 Name is the natural key
Bundle `name` MUST be the natural key for bootstrap upserts ([MGMT-9](../management/spec.md)): a bundle is created or
updated by its name. The API offers no rename for a bundle; the name in the path and body of `PUT
/api/v1/bundles/{name}` must agree, so a different name is a different bundle.

#### Scenario: Upsert by name updates in place
- **WHEN** `PUT /api/v1/bundles/b1` is called twice with different descriptions
- **THEN** one bundle `b1` exists, carrying the second description

### Requirement: BND-11 Catalogue overview
A bundle MUST also have an `overview`: a long-form, admin-managed description written for the person browsing the
catalogue, separate from `description` because that one is sent to a model as the MCP `instructions` (BND-1) and must
stay short. The catalogue shows the overview together with the tools the bundle serves, after curation
([BND-14](../bundles/spec.md)), so a user can see what they are connecting before they connect it. Each tool is
shown by its title and description, the two fields written for a reader; the prefixed name (BND-2) is how a model
addresses the tool, so it is not shown unless the tool has no title and nothing else identifies it. Both are readable
only through an endpoint the caller could actually use; a bundle with no OAuth endpoint is reported as not found rather
than forbidden.

#### Scenario: Signed-in users see the catalogue
- **WHEN** a signed-in non-admin user opens the catalogue
- **THEN** it lists the bundles reachable through an enabled OAuth endpoint, with their overview and curated tools

#### Scenario: A bundle without an OAuth endpoint is not found
- **WHEN** a signed-in user requests the catalogue tools of a bundle that has no OAuth endpoint
- **THEN** the response is `404`, not `403`

#### Scenario: Anonymous callers are refused
- **WHEN** the catalogue is requested without a signed-in user
- **THEN** the request is refused as unauthenticated

### Requirement: BND-12 Per-bundle tool curation record
Each `(bundle, tool)` pair SHALL have `enabled` (default true) and optional overrides for `name`, `title`,
`description`, `annotations` ([domain model](../architecture/spec.md), `BundleTool`). A tool without a stored curation
record SHALL behave as enabled with no overrides.

#### Scenario: Uncurated tool is enabled and unchanged
- **GIVEN** a bundle whose member upstream `echo` offers tool `say` and no curation record exists for it
- **WHEN** an admin lists the bundle's tools through the management API
- **THEN** `say` is reported with `enabled: true`, presented name `echo__say`, and no overrides

#### Scenario: Curation stores enable flag and overrides
- **WHEN** an admin sets `enabled`, `override_name`, `override_title`, `override_description` and
  `override_annotations` for a tool in a bundle
- **THEN** the curation record for that `(bundle, tool)` pair carries those values
- **AND** the same tool in another bundle is unaffected

### Requirement: BND-13 Disabled tools are hidden and rejected
Disabled tools MUST be absent from `tools/list` **and** rejected on `tools/call` with a standard MCP error —
enforcement in both paths, as the first stage of the endpoint's tool pipeline, ahead of the profile transform
([EP-13](../endpoints/spec.md)) and the per-tool overrides, whose output backs both paths.

#### Scenario: Disabled tool is hidden from the list
- **GIVEN** tool `echo__say` is disabled in the bundle
- **WHEN** a client calls `tools/list` on an endpoint of the bundle
- **THEN** `echo__say` is not in the result

#### Scenario: Disabled tool is rejected on call
- **GIVEN** tool `echo__say` is disabled in the bundle
- **WHEN** a client calls `tools/call` with name `echo__say`
- **THEN** the gateway answers with a JSON-RPC invalid-params error (`-32602`) naming the unknown tool
- **AND** no upstream call is made

#### Scenario: A disabled tool never reaches the profile transform
- **GIVEN** tool `echo__say` is disabled in a bundle served through a `write_as_read`-profile endpoint
- **WHEN** a client lists tools
- **THEN** `echo__say` is absent, and no override name of `echo__say` is presented either

### Requirement: BND-14 Name overrides and routing back
Name overrides SHALL replace the prefixed name (`server__tool` → `override_name`); the router MUST map override names
back to the origin upstream/tool on call. Override names MUST be unique within a bundle among the bundle's other
override names (validated on write).

#### Scenario: Override name is presented and routes to the origin tool
- **GIVEN** tool `echo__say` has `override_name` `speak` in the bundle
- **WHEN** a client lists tools and then calls `speak`
- **THEN** the list contains `speak` and not `echo__say`
- **AND** the call is executed by tool `say` on upstream `echo`

#### Scenario: Duplicate override name is rejected
- **GIVEN** a tool in the bundle already has `override_name` `speak`
- **WHEN** an admin sets `override_name` `speak` on a different tool of the same bundle
- **THEN** the management API rejects the write with `409 Conflict`

### Requirement: BND-15 Annotation overrides as a shallow merge
Annotation overrides SHALL be a shallow merge over the upstream annotations (setting a key to `null` removes it). This
is the same mechanism the `write_as_read` profile uses programmatically ([endpoint profiles](../endpoints/spec.md));
explicit per-tool overrides MUST win over profile rewrites.

#### Scenario: Override merges and removes keys
- **GIVEN** an upstream tool annotated `{"readOnlyHint": false, "openWorldHint": true}`
- **WHEN** the bundle overrides annotations with `{"readOnlyHint": true, "openWorldHint": null}`
- **THEN** the tool is presented with `{"readOnlyHint": true}`

#### Scenario: Explicit override wins over the chatgpt profile
- **GIVEN** a tool with an annotation override `{"readOnlyHint": false}` served through a
  `write_as_read`-profile endpoint
- **WHEN** a client lists tools
- **THEN** the tool's `readOnlyHint` is `false`, while `destructiveHint` is still rewritten to `false` by the profile

### Requirement: BND-16 Curation UI
The bundle detail page SHALL list all member tools with an enable toggle and inline editing of the override name and
override title, and SHALL flag tools whose name, title or description is overridden and tools whose membership is
disabled.

#### Scenario: Admin toggles and renames a tool in the UI
- **WHEN** an admin opens a bundle's detail page
- **THEN** every member tool appears as a curation row with its presented name `server__tool`
- **AND** unticking the enable toggle or entering an override name and saving updates the tool's curation

#### Scenario: Overridden tool is flagged
- **GIVEN** a tool with an override title
- **WHEN** the bundle detail page is shown
- **THEN** the tool's row carries an "overridden" badge

### Requirement: BND-17 Curation through the management API
All curation operations MUST be available via the management API: listing a bundle's member tools with their curation
state, and setting a tool's enable flag and overrides.

#### Scenario: Curation round trip over the API
- **WHEN** an admin sends `PUT /api/v1/bundles/{name}/tools/{tool_id}` with `enabled: false`
- **THEN** `GET /api/v1/bundles/{name}/tools` reports that tool with `enabled: false`

### Requirement: BND-18 Bundle prompts
A bundle SHALL have zero or more **bundle prompts**. Each has a `name`, an optional `title` and `description`, a list
of `arguments` (each with `name` matching `^[a-zA-Z0-9_-]+$` so a placeholder can name it, optional `description`,
`required` flag, and optional `values` — a closed list of suggestions), and an ordered list of at least one
`messages`. Natural key: `(bundle, name)`.

#### Scenario: Prompt round trip
- **WHEN** an admin `PUT`s a prompt with a title, two arguments and two messages on bundle `main`
- **THEN** `GET /api/v1/bundles/main/prompts/{name}` returns the same title, arguments and messages in order

#### Scenario: Prompt without messages is rejected
- **WHEN** an admin writes a prompt with an empty `messages` list
- **THEN** the write is rejected with a validation error

#### Scenario: Same name in two bundles
- **WHEN** bundles `a` and `b` each get a prompt named `review`
- **THEN** both are stored independently

### Requirement: BND-19 Bundle prompt names
A bundle prompt's `name` MUST match `^[a-zA-Z0-9_-]+$` and MUST NOT contain `__`. Member prompts are always presented
as `<server_name>__<prompt_name>` ([BND-8](../bundles/spec.md)), so an unprefixed name can never collide with one, and a
name without `__` routes to the bundle without a lookup in any member.

#### Scenario: Name with the prefix separator is rejected
- **WHEN** an admin writes a bundle prompt named `echo__review`
- **THEN** the write is rejected with a validation error

### Requirement: BND-20 Messages, placeholders and embedded resources
A message SHALL have a `role` (`user` or `assistant`) and content that is either **text** or a reference to one of the
same bundle's resources (BND-23), which `prompts/get` embeds as an MCP embedded resource. Text may contain
`{{argument}}` placeholders. Substitution is plain text replacement, with no expressions, loops or escapes, and the
substituted value MUST be inserted verbatim, never re-scanned for placeholders. A write MUST be rejected when a
placeholder names an undeclared argument or a resource reference names a resource the bundle does not have. For the
same reason deleting a resource that a prompt embeds MUST be refused (`409`), naming the prompts that embed it.

#### Scenario: Substituted value is not re-scanned
- **GIVEN** a prompt with text `Hello {{name}}` and arguments `name` and `other`
- **WHEN** `prompts/get` is called with `name` = `{{other}}`
- **THEN** the rendered text is `Hello {{other}}`

#### Scenario: Undeclared placeholder is rejected
- **WHEN** an admin writes a prompt whose text uses `{{missing}}` without declaring `missing`
- **THEN** the write is rejected naming the placeholder

#### Scenario: Embedded resource cannot be deleted
- **GIVEN** prompt `review` embeds bundle resource `style`
- **WHEN** an admin deletes resource `style`
- **THEN** the API answers 409 naming prompt `review`

### Requirement: BND-21 Required arguments
`prompts/get` for a bundle prompt MUST reject a missing required argument with `-32602`, naming it. An optional
argument that is not supplied SHALL be substituted with the empty string.

#### Scenario: Missing required argument
- **WHEN** a client calls `prompts/get` for a bundle prompt without its required argument `topic`
- **THEN** the gateway answers with error `-32602` whose message names `topic`

#### Scenario: Missing optional argument
- **WHEN** a client omits an optional argument used as `{{tone}}`
- **THEN** the placeholder renders as the empty string

### Requirement: BND-22 Completions from suggested values
`completion/complete` with a prompt ref to a bundle prompt MUST be answered by the gateway from the argument's `values`:
case-insensitive prefix match on the partial value, at most 100 results, `hasMore` set when more matched. An argument
without `values` completes to an empty list. No member is contacted ([PROT-9](../protocol/spec.md)).

#### Scenario: Prefix completion
- **GIVEN** a bundle prompt argument with `values` `["Python", "PHP", "Rust"]`
- **WHEN** a client requests completion for that argument with partial value `p`
- **THEN** the result is `["Python", "PHP"]` with `hasMore: false` and no upstream is contacted

#### Scenario: Argument without values
- **WHEN** a client requests completion for an argument without `values`
- **THEN** the result is an empty list

### Requirement: BND-23 Bundle resources
A bundle SHALL have zero or more **bundle resources**. Each has a `name` (natural key `(bundle, name)`, matching
`^[a-zA-Z0-9_-]+(/[a-zA-Z0-9_.-]+)*$` so it can be organised in folders), an optional `title` and `description`, a
`mime_type`, and text `content`. Accepted MIME types MUST be text only: `text/markdown` (the default), `text/plain`,
`text/csv`, `application/json` and `application/yaml`. Binary content is out of scope.

#### Scenario: Folder name round trip
- **WHEN** an admin `PUT`s resource `guides/style.md` on bundle `main`
- **THEN** `GET /api/v1/bundles/main/resources/guides/style.md` returns it with `mime_type` `text/markdown`

#### Scenario: Non-text MIME type is rejected
- **WHEN** an admin writes a resource with `mime_type` `image/png`
- **THEN** the write is rejected with a validation error

### Requirement: BND-24 Bundle resource URIs
A bundle resource SHALL be presented under the URI `bundle://resources/<name>`. The URI deliberately carries no bundle
name: a client only ever sees one bundle per endpoint, and a rename of the bundle ([BND-10](../bundles/spec.md))
therefore does not change the URIs its prompts and saved conversations refer to. Member resource URIs pass through
unchanged (BND-8); a member URI in the `bundle:` scheme is shadowed by the bundle and the collision logged.

#### Scenario: URI carries no bundle name
- **WHEN** a client lists resources on an endpoint of bundle `main` that owns resource `style`
- **THEN** the resource is listed as `bundle://resources/style`

#### Scenario: Member URI in the bundle scheme is shadowed
- **GIVEN** a member upstream that lists a resource with a `bundle://` URI
- **WHEN** a client lists resources
- **THEN** that member entry is left out and a warning is logged

### Requirement: BND-25 Served without upstream contact
Bundle prompts and resources MUST be served from Postgres without contacting any upstream: `prompts/list`,
`prompts/get`, `resources/list`, `resources/read` and completions for bundle prompts never open an upstream connection
on their behalf. The bundle's view, loaded with its tools on every request, SHALL carry their listing — names,
descriptions, arguments, MIME types and sizes, never message text or content; `prompts/get` and `resources/read` read
the one entry they need by natural key. That keeps up to 4 MiB of content out of every request that does not ask for
it.

#### Scenario: prompts/get renders without a member
- **GIVEN** a bundle prompt and a member upstream that is unreachable
- **WHEN** a client calls `prompts/get` for the bundle prompt
- **THEN** the rendered messages are returned and no upstream connection is opened

### Requirement: BND-26 Merging with member passthrough
`prompts/list` and `resources/list` MUST return the bundle's own entries first, in name order, then the member entries
per BND-8. `prompts/get` with a name without `__` and `resources/read` with a `bundle://` URI MUST be answered by the
bundle alone; an unknown one is not-found without falling through to the members. `resources/templates/list` is
unchanged: bundle resources are concrete, never templates.

#### Scenario: Own entries first
- **GIVEN** a bundle with prompts `b` and `a` and a member offering prompt `x`
- **WHEN** a client calls `prompts/list`
- **THEN** the result lists `a`, `b`, then `echo__x`

#### Scenario: Unknown unprefixed prompt does not fall through
- **WHEN** a client calls `prompts/get` with name `nope`
- **THEN** the gateway answers not-found and no member is asked

#### Scenario: Unknown bundle URI does not fall through
- **WHEN** a client calls `resources/read` with `bundle://resources/nope`
- **THEN** the gateway answers not-found and no member is asked

### Requirement: BND-27 Capability aggregation
Capability aggregation ([PROT-11](../protocol/spec.md)): the bundle MUST advertise `prompts` when it owns
at least one prompt or a member advertises prompts, `resources` likewise, and `completions` when a bundle prompt
argument has `values` or a member advertises completions. An endpoint over a bundle with no member upstreams at all can
therefore serve prompts and resources.

#### Scenario: Bundle without members
- **GIVEN** a bundle with no members that owns one prompt and one resource
- **WHEN** a client initializes
- **THEN** the capabilities include `prompts` and `resources`, and `prompts/list` returns the prompt

#### Scenario: No completions without suggested values
- **GIVEN** a bundle whose prompts have no argument `values` and no member advertising completions
- **WHEN** a client initializes
- **THEN** `completions` is not advertised

### Requirement: BND-28 Change notification
Creating, changing or deleting a bundle prompt or resource MUST invalidate the bundle ([BND-7](../bundles/spec.md)).
Live clients SHALL receive `notifications/prompts/list_changed` or `notifications/resources/list_changed` on the stream
the client opened for notifications: the GET stream for handshake clients, `subscriptions/listen` for modern clients.
For modern clients this means the gateway acknowledges `promptsListChanged` and `resourcesListChanged`
([PROT-17](../protocol/spec.md)) for changes to bundle-owned entries; member changes are still not
delivered until upstream pooling lands. `listChanged: true` is advertised for prompts and resources whenever the bundle
owns any.

#### Scenario: Handshake client is notified
- **GIVEN** a handshake-era client with an open GET stream
- **WHEN** an admin changes a bundle prompt
- **THEN** the stream delivers `notifications/prompts/list_changed`

#### Scenario: Modern client subscription is acknowledged
- **WHEN** a modern client calls `subscriptions/listen` asking for `promptsListChanged` and `resourcesListChanged`
- **THEN** both are acknowledged and a later bundle resource write delivers `notifications/resources/list_changed`

### Requirement: BND-29 Cache hints
Cache hints ([PROT-16](../protocol/spec.md)): list results MUST keep the list TTL. `resources/read` of a
bundle resource MUST be `public` with the same TTL, because its content is identical for every caller.

#### Scenario: Bundle resource read is publicly cacheable
- **WHEN** a modern client reads a bundle resource
- **THEN** the result's cache hint is `public` with the list TTL

### Requirement: BND-30 Profiles do not rewrite
Endpoint profiles ([endpoint profiles](../endpoints/spec.md)) MUST NOT rewrite bundle prompts or resources.

#### Scenario: chatgpt endpoint serves prompts unchanged
- **GIVEN** a `write_as_read`-profile and a `default`-profile endpoint over the same bundle
- **WHEN** a client calls `prompts/get` for a bundle prompt on each
- **THEN** both return identical messages

### Requirement: BND-31 Management API and UI
Bundle prompts and resources MUST be managed by admins only, through the management API under the bundle — `GET`, `PUT`
(idempotent upsert by name) and `DELETE` on `/api/v1/bundles/{bundle}/prompts/{name}` and
`/api/v1/bundles/{bundle}/resources/{name}`, and paginated `GET` on the two collections — and in the admin UI on the
bundle's detail page. The UI SHALL preview a prompt rendered with sample arguments and a resource rendered as Markdown.

#### Scenario: Idempotent upsert and delete
- **WHEN** an admin `PUT`s the same prompt twice and then `DELETE`s it twice
- **THEN** both `PUT`s succeed with the same stored result and both `DELETE`s answer 204

#### Scenario: Unknown bundle
- **WHEN** an admin lists prompts of a bundle that does not exist
- **THEN** the API answers 404

#### Scenario: UI preview
- **WHEN** an admin edits a prompt on the bundle detail page and enters sample argument values
- **THEN** the preview shows the messages with the samples substituted

### Requirement: BND-32 Bootstrap carries prompts and resources
Bootstrap ([management](../management/spec.md)) MUST carry each bundle's prompts and resources inside the bundle entry,
upserted by natural key. An entry absent from the document is not deleted.

#### Scenario: Bootstrap applies resources before the prompts that embed them
- **GIVEN** a bootstrap document whose bundle entry has a prompt embedding a resource defined in the same entry
- **WHEN** bootstrap runs
- **THEN** both are stored and the prompt's reference is valid

### Requirement: BND-33 Limits
Limits MUST be validated on write: at most 100 prompts and 200 resources per bundle, 64 KiB of message text per
prompt, 256 KiB per resource, and 4 MiB of resource content per bundle. A write over a limit MUST be rejected with a
message that names the limit; nothing is truncated.

#### Scenario: Oversized resource is rejected
- **WHEN** an admin writes a resource of more than 256 KiB (measured in UTF-8 bytes)
- **THEN** the write is rejected with a message naming the 256 KiB limit

#### Scenario: Replacing an entry does not double-count
- **GIVEN** a bundle close to the 4 MiB total
- **WHEN** an admin replaces an existing resource with one of the same size
- **THEN** the write succeeds

### Requirement: BND-34 Content is not secret
Content is not secret, and the API MUST say so: it is served to every caller of every endpoint of the bundle, and to
the model. It MUST be logged by size, never by value.

#### Scenario: Write is logged by size
- **WHEN** an admin writes a bundle resource
- **THEN** the log records the bundle, the resource name and its size in bytes, never its content

### Requirement: BND-35 Not audited
Reading a bundle prompt or resource over MCP MUST NOT be audited ([OPS-1](../operations/spec.md) covers tool calls
only). A management write is logged as a configuration change (BND-34).

#### Scenario: prompts/get leaves no audit record
- **WHEN** a client calls `prompts/get` and `resources/read` for bundle-owned entries
- **THEN** no audit record is written

### Requirement: BND-36 Catalogue listing
The catalogue ([BND-11](../bundles/spec.md)) MUST list a bundle's own prompts and resources by title and description,
so a user sees what context the bundle offers before connecting it.

#### Scenario: Catalogue shows titles only
- **WHEN** a user opens a bundle in the catalogue
- **THEN** its prompts and resources are listed by title and description, without message text or content

## Out of scope

### Bundles

- Nested bundles (a bundle containing a bundle).
- Per-bundle tool renaming beyond overrides.

### Tool curation

- Editing tool **input schemas** (only name/title/description/annotations).

### Bundle prompts and resources

- Binary resources, resource templates and resource subscriptions for bundle resources (the content changes only on an
  admin write, which BND-28 already announces).
- Prompt logic beyond placeholder substitution: conditionals, loops, includes of other prompts.
- Per-endpoint or per-user variants of a bundle's prompts and resources.
- Bundle-owned **tools** (code the gateway would run). Tools stay upstream.

## Notes

### Bundles

Origin: metamcp carry-over (metamcp: "namespaces"). Prior art:
`../metamcp/apps/backend/src/lib/metamcp/metamcp-proxy.ts`, `utils.ts` (sanitizeName), `tool-name-parser.ts`.

BND-8/BND-9 ([ADR-0021](../../../docs/adr/0021-mcp-surface-completion.md)): prompts/resources/completions are live
passthrough with no cache or curation tables; the fan-out lives in `api/mcp/dispatch/handlers/member_fanout.py`.
Capability aggregation reads the per-server `capabilities` snapshot captured at discovery
([upstreams](../upstreams/spec.md)). Passthrough was kept in v1 for consistency with the full-fidelity proxy
decision ([protocol](../protocol/spec.md),
[ADR-0008](../../../docs/adr/0008-full-bidirectional-proxy.md)).

`tools/call` resolves the presented name by matching it against the bundle view's presented tools, each held under its
override name or prefixed name; this is equivalent to the first-`__` parse of BND-3.

### Tool curation

Origin: metamcp carry-over. Prior art:
`../metamcp/apps/backend/src/lib/metamcp/metamcp-middleware/filter-tools.functional.ts`, `tool-overrides.functional.ts`,
`namespace_tool_mappings`.

The profile rewrite and the per-tool overrides are applied together when the endpoint's bundle view is built, so
`tools/list` and `tools/call` see the same presented tool set.

### Bundle prompts and resources

The bundle's `description` stays the short always-on `instructions` ([BND-1](../bundles/spec.md)); prompts and resources
hold the longer material a client pulls in on demand. Serving them without an upstream contact means they cost nothing
for an upstream that scales to zero ([ADR-0043](../../../docs/adr/0043-contact-upstreams-only-with-a-reason.md)).
Rationale and alternatives: [ADR-0044](../../../docs/adr/0044-bundle-owned-prompts-and-resources.md).

Open questions:

- Whether the URI scheme should be `bundle:` or a less generic, gateway-specific one such as `bundlemcp:`, given that
  clients may show it to users.
- Whether a bundle prompt should be able to embed a **member** resource by URI (fetched live at `prompts/get`), which
  would reintroduce an upstream contact on a path BND-25 keeps upstream-free.
- Whether management writes need a durable change history (who changed which prompt, when) beyond the configuration
  log; no other configuration entity has one today.
