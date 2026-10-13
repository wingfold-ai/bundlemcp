## MODIFIED Requirements

### Requirement: BND-1 Bundle identity and instructions
A bundle MUST have a unique slug-safe `name`, a `description`, and an **ordered** set of member servers. The order is
admin-controlled: a new member is appended at the end, an admin can reorder the members through the management API and
UI, and a bootstrap document's member list sets the order of the members it names. Wherever member order matters
(BND-8) the gateway follows this order. The `description` is served as the MCP `instructions` field of the virtual
server.

#### Scenario: Description is served as instructions
- **WHEN** a client initializes against an endpoint of the bundle (or calls `server/discover`)
- **THEN** the result's `instructions` field carries the bundle's `description`

#### Scenario: Members are listed in name order
- **GIVEN** a bundle with members `zeta` and `alpha` that existed before member order was introduced
- **WHEN** the gateway is upgraded and `GET /api/v1/bundles/{name}/upstreams` is called
- **THEN** `alpha` is listed before `zeta`, the order the members were served in before the upgrade

#### Scenario: Members are listed in member order
- **GIVEN** a bundle to which `zeta` was added before `alpha`
- **WHEN** `GET /api/v1/bundles/{name}/upstreams` is called
- **THEN** `zeta` is listed before `alpha`

#### Scenario: An admin reorders the members
- **GIVEN** a bundle with members `zeta` and `alpha`, in that order
- **WHEN** an admin calls `PUT /api/v1/bundles/{name}/upstreams:order` with `{"upstreams": ["alpha", "zeta"]}`
- **THEN** `GET /api/v1/bundles/{name}/upstreams` lists `alpha` before `zeta`

#### Scenario: A reorder must name exactly the members
- **WHEN** an admin calls `PUT /api/v1/bundles/{name}/upstreams:order` with a list that omits a member, repeats one, or
  names an upstream that is not a member
- **THEN** the response is `422` and the order is unchanged

### Requirement: BND-8 Prompt and resource passthrough
Resources and prompts of member servers MUST be **uncurated passthrough** (tools are the curated surface); they are
fetched **live** from members per request and are not cached
([upstreams](../../../../specs/upstreams/spec.md)). Only members whose capabilities snapshot
([UPS-22](../../../../specs/upstreams/spec.md)) advertises the capability a method belongs to are asked — `prompts`
for `prompts/*`, `resources` for `resources/*`, `completions` for `completion/complete` — so a member without it, or one
never successfully discovered, is not contacted and contributes nothing
([ADR-0043](../../../../../docs/adr/0043-contact-upstreams-only-with-a-reason.md)). Routing rules:

- **Prompts** carry a name, so they are **always prefixed** `<server_name>__<prompt_name>` (BND-2 scheme);
  `prompts/get` and completion prompt-refs de-prefix on the first `__` to find the owning member.
- **Resources** are keyed by opaque URI, not a prefixable name, so URIs are passed through **unchanged**.
  `resources/list` (and `resources/templates/list`) merge members' entries verbatim, de-duplicating by URI (first
  enabled member in member order (BND-1) wins, collisions logged). `resources/read`, `resources/subscribe`, and
  resource-template completions resolve the owning member by **fan-out** — trying enabled members in member order and
  taking the first that owns the URI.
- Completions are routed per [PROT-9](../../../../specs/protocol/spec.md).

Prompts and resources authored on the bundle itself, served beside this passthrough, are specified in
[bundles](../../../../specs/bundles/spec.md).

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

#### Scenario: The first member in member order wins a URI collision
- **GIVEN** members `zeta` and `alpha`, in that order, both listing resource `file:///a.txt`
- **WHEN** a client calls `resources/list` and then `resources/read` for `file:///a.txt`
- **THEN** the URI is listed once, from `zeta`, and the read is answered by `zeta`

### Requirement: BND-14 Name overrides and routing back
Name overrides SHALL replace the prefixed name (`server__tool` → `override_name`); the router MUST map override names
back to the origin upstream/tool on call. Override names MUST be unique within a bundle, against the bundle's other
override names **and** against the prefixed names of every other tool of the bundle's members (validated on write).
The check MUST be repeated whenever the bundle's prefixed names change: adding a member, or renaming a member upstream,
is rejected with `409 Conflict` when it would introduce a prefixed name equal to an existing override name.

#### Scenario: Override name is presented and routes to the origin tool
- **GIVEN** tool `echo__say` has `override_name` `speak` in the bundle
- **WHEN** a client lists tools and then calls `speak`
- **THEN** the list contains `speak` and not `echo__say`
- **AND** the call is executed by tool `say` on upstream `echo`

#### Scenario: Duplicate override name is rejected
- **GIVEN** a tool in the bundle already has `override_name` `speak`
- **WHEN** an admin sets `override_name` `speak` on a different tool of the same bundle
- **THEN** the management API rejects the write with `409 Conflict`

#### Scenario: Override name equal to a prefixed name is rejected
- **GIVEN** a bundle whose member `weather` offers tool `forecast`, presented as `weather__forecast`
- **WHEN** an admin sets `override_name` `weather__forecast` on a tool of another member of the same bundle
- **THEN** the management API rejects the write with `409 Conflict` naming the colliding tool

#### Scenario: Adding a member that would collide is rejected
- **GIVEN** a bundle in which a tool carries `override_name` `weather__forecast`
- **WHEN** an admin adds upstream `weather`, which offers tool `forecast`, as a member of that bundle
- **THEN** the management API rejects the membership with `409 Conflict` and the bundle's members are unchanged

#### Scenario: Renaming a member upstream into a collision is rejected
- **GIVEN** a bundle with member `meteo` offering tool `forecast`, and another tool of the bundle carrying
  `override_name` `weather__forecast`
- **WHEN** an admin renames upstream `meteo` to `weather` with `force=true`
- **THEN** the management API rejects the rename with `409 Conflict` naming the bundle and the override

### Requirement: BND-16 Curation UI
The bundle detail page SHALL list all member tools with an enable toggle and inline editing of the override name,
override title, override description and override annotations, and SHALL flag tools whose name, title, description or
annotations are overridden, tools whose membership is disabled, and stale tools
([UPS-19](../../../../specs/upstreams/spec.md)). Saving a tool's row MUST send every override the tool currently
carries, so a save never clears an override the admin did not change, including one set through the management API.

#### Scenario: Admin toggles and renames a tool in the UI
- **WHEN** an admin opens a bundle's detail page
- **THEN** every member tool appears as a curation row with its presented name `server__tool`
- **AND** unticking the enable toggle or entering an override name and saving updates the tool's curation

#### Scenario: Overridden tool is flagged
- **GIVEN** a tool with an override title
- **WHEN** the bundle detail page is shown
- **THEN** the tool's row carries an "overridden" badge

#### Scenario: Description and annotations are edited inline
- **WHEN** an admin enters an override description and the annotation override `{"readOnlyHint": true}` on a tool's
  row and saves
- **THEN** `GET /api/v1/bundles/{name}/tools` reports both overrides for that tool and its row carries the
  "overridden" badge

#### Scenario: Saving a row keeps overrides set through the API
- **GIVEN** a tool whose `override_description` and `override_annotations` were set through the management API
- **WHEN** an admin changes only the tool's override title in the UI and saves
- **THEN** the tool's `override_description` and `override_annotations` are unchanged

#### Scenario: Stale tool is flagged
- **GIVEN** a tool that the latest successful discovery of its upstream no longer listed
- **WHEN** the bundle detail page is shown
- **THEN** the tool's row carries a "stale" badge

### Requirement: BND-17 Curation through the management API
All curation operations MUST be available via the management API: listing a bundle's member tools with their curation
state — enable flag, every override including `override_annotations`, and whether the tool is stale — and setting a
tool's enable flag and overrides.

#### Scenario: Curation round trip over the API
- **WHEN** an admin sends `PUT /api/v1/bundles/{name}/tools/{tool_id}` with `enabled: false`
- **THEN** `GET /api/v1/bundles/{name}/tools` reports that tool with `enabled: false`

#### Scenario: Annotation overrides are listed
- **WHEN** an admin sends `PUT /api/v1/bundles/{name}/tools/{tool_id}` with `override_annotations`
  `{"readOnlyHint": true}`
- **THEN** `GET /api/v1/bundles/{name}/tools` reports that tool with `override_annotations` `{"readOnlyHint": true}`

#### Scenario: Staleness is listed
- **GIVEN** a member tool that the latest successful discovery of its upstream no longer listed
- **WHEN** an admin calls `GET /api/v1/bundles/{name}/tools`
- **THEN** that tool is reported with `stale: true` and every other tool with `stale: false`
