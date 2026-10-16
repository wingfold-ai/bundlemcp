## MODIFIED Requirements

### Requirement: BND-8 Prompt and resource passthrough
Resources and prompts of member servers MUST be **passthrough**, curated only as far as
[BND-37](../bundles/spec.md) allows (disable an entry, override its title or description). Only members whose
capabilities snapshot ([UPS-22](../upstreams/spec.md)) advertises the capability a method belongs to are asked —
`prompts` for `prompts/*`, `resources` for `resources/*`, `completions` for `completion/complete` — so a member without
it, or one never successfully discovered, is not contacted and contributes nothing
([ADR-0043](../../../docs/adr/0043-contact-upstreams-only-with-a-reason.md)).

`prompts/list`, `resources/list` and `resources/templates/list` answer each capable member from its **listing
snapshot** ([UPS-24](../upstreams/spec.md)) when that snapshot is shareable and complete
([UPS-38](../upstreams/spec.md)), without contacting the member. They ask a member **live** only when it has no such
snapshot. `prompts/get`, `resources/read`, `resources/subscribe`, `resources/unsubscribe` and `completion/complete`
depend on their arguments and are always fetched live from the member. Routing rules:

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

#### Scenario: Lists are served from a shareable snapshot
- **GIVEN** member `weather`, discovered with a shareable prompt snapshot listing `daily`, and a resource snapshot
  listing one resource and one template
- **WHEN** a client calls `prompts/list`, `resources/list` and `resources/templates/list`
- **THEN** the lists show `weather__daily`, the resource and the template, and `weather` receives no request

#### Scenario: A member without a shareable snapshot is listed live
- **GIVEN** member `crm` forwards the caller's `Authorization` header and its prompt listing had no `cacheScope`
- **WHEN** a client calls `prompts/list`
- **THEN** `crm` is asked for its prompts with the caller's header, and its answer is listed

#### Scenario: Served lists stay live
- **GIVEN** a member prompt cached for curation that the member's last discovery no longer listed
- **WHEN** a client calls `prompts/list`
- **THEN** the prompt is not listed, because the list is the member's last listing, not the curation cache
