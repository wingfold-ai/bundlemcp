## MODIFIED Requirements

### Requirement: BND-8 Prompt and resource passthrough
Resources and prompts of member servers MUST be **passthrough**, curated only as far as
[BND-37](../bundles/spec.md) allows (disable an entry, override its title or description); they are
fetched **live** from members per request, and the discovery cache ([UPS-24](../upstreams/spec.md)) feeds
curation, never what is served. Only members whose capabilities snapshot
([UPS-22](../upstreams/spec.md)) advertises the capability a method belongs to are asked —
`prompts` for `prompts/*`, `resources` for `resources/*`, `completions` for `completion/complete` — so a member without
it, or one never successfully discovered, is not contacted and contributes nothing
([ADR-0043](../../../docs/adr/0043-contact-upstreams-only-with-a-reason.md)). Routing rules:

- **Prompts** carry a name, so they are **always prefixed** `<server_name>__<prompt_name>` (BND-2 scheme);
  `prompts/get` and completion prompt-refs de-prefix on the first `__` to find the owning member.
- **Resources** are keyed by opaque URI, not a prefixable name, so URIs are passed through **unchanged**.
  `resources/list` (and `resources/templates/list`) merge members' entries verbatim, de-duplicating by URI (first
  enabled member in member order (BND-1) wins, collisions logged). `resources/read`, `resources/subscribe`, and
  resource-template completions resolve the owning member by **fan-out** — trying enabled members in member order and
  taking the first that owns the URI.
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

#### Scenario: The first member in member order wins a URI collision
- **GIVEN** members `zeta` and `alpha`, in that order, both listing resource `file:///a.txt`
- **WHEN** a client calls `resources/list` and then `resources/read` for `file:///a.txt`
- **THEN** the URI is listed once, from `zeta`, and the read is answered by `zeta`

#### Scenario: Served lists stay live
- **GIVEN** a member prompt cached by discovery that the member no longer lists
- **WHEN** a client calls `prompts/list`
- **THEN** the prompt is not listed, because the list comes from the member, not from the cache

## ADDED Requirements

### Requirement: BND-37 Member prompt and resource curation
Member prompts and resources SHALL be curatable per bundle like tools
([bundles](../bundles/spec.md)): an admin can disable a member's prompt or resource in
one bundle, or override its title and description, through the management API and the bundle detail page. The entries
offered for curation are those cached by discovery ([UPS-24](../upstreams/spec.md)). Curation never changes a
prompt's name, a resource's URI, prompt messages or resource content, and an entry without curation is served
unchanged.

#### Scenario: A disabled member prompt is hidden and refused
- **GIVEN** member `weather` offers prompt `daily` and it is disabled in bundle `b1`
- **WHEN** a client calls `prompts/list` and then `prompts/get` with `weather__daily` on an endpoint of `b1`
- **THEN** the list does not contain `weather__daily`, and the get answers not-found without contacting `weather`

#### Scenario: A disabled member resource is hidden and refused
- **GIVEN** member `docs` lists resource `file:///a.txt` and it is disabled in bundle `b1`
- **WHEN** a client calls `resources/list` and then `resources/read` for `file:///a.txt` on an endpoint of `b1`
- **THEN** the list does not contain the URI, and the read answers not-found without contacting `docs`

#### Scenario: Title and description overrides are presented
- **GIVEN** prompt `weather__daily` with an override title `Morning forecast` in bundle `b1`
- **WHEN** a client calls `prompts/list` on an endpoint of `b1`
- **THEN** the prompt is listed as `weather__daily` with title `Morning forecast`, and its upstream arguments unchanged

#### Scenario: Curation is per bundle
- **GIVEN** prompt `weather__daily` is disabled in bundle `b1`
- **WHEN** a client calls `prompts/list` on an endpoint of bundle `b2`, which also has member `weather`
- **THEN** `weather__daily` is listed

#### Scenario: Curation over the management API
- **WHEN** an admin lists `GET /api/v1/bundles/{name}/member-prompts` and sets `enabled: false` on one entry with
  `PUT /api/v1/bundles/{name}/member-prompts/{prompt_id}`
- **THEN** the next listing reports that entry with `enabled: false`, and the same holds for `member-resources`
