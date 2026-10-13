# Proposal

## Why

Member prompts and resources are uncurated passthrough (BND-8): the only way to hide one member prompt from one bundle
is to disable the whole membership, which also hides every tool of that member. BND-37 in the original bundle prompts
and resources spec recorded per-bundle curation of member prompts and resources as a **MAY, decided separately** from
the bundle-owned prompts and resources that shipped. This change writes that option down so it can be decided.

**This change is optional and needs an explicit go/no-go from the maintainers before it is applied.** It is a feature
nobody has asked for yet, and it adds a discovery cache that BND-8 deliberately avoided.

## What Changes

- **Prompt and resource discovery** (UPS-24, new): the discovery probe also lists a member's prompts and resources when
  its capability snapshot advertises them, and caches their names or URIs, titles and descriptions — never messages
  or content — hash-gated, bounded, and kept when they vanish. Nothing on the request path reads it to serve.
- **Per-bundle curation** (BND-37, new): an admin disables a member prompt or resource in one bundle, or overrides its
  title and description, through new management routes and the bundle detail page.
- **Passthrough honours curation** (BND-8): served lists stay live from the members, but disabled entries are dropped,
  overrides applied, and `prompts/get` / `resources/read` of a disabled entry answer not-found without contacting the
  member.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `bundles`: BND-37 (added: member prompt and resource curation).
- `upstreams`: UPS-24 (added: prompt and resource discovery). Its "Out of scope" note ("content discovery of
  resources/prompts is handled in bundles … never the prompt/resource lists themselves") must be reworded on archive.
- `bundles`: BND-8 (passthrough is curated as far as BND-37 allows).

## Open decision

**Go / no-go.** Arguments for: per-bundle shaping of prompts matches what bundles do for tools, and a member exposing
dozens of prompts can drown a bundle's own (BND-26). Arguments against: a second discovery cache to keep consistent,
more upstream traffic at every probe (ADR-0043 asks for a reason to contact an upstream — the probe already happening is
that reason, but the listing adds requests), resource listings that can be huge or per-user, and no consumer request so
far. A no-go closes this change unapplied; BND-37 then stays out of the main spec and its ID unused.

## Impact

- **Depends on** [complete-tool-curation](../complete-tool-curation/proposal.md): it reuses that change's staleness
  rule and curation UI patterns, and its BND-8 delta already contains that change's member-order edit, so this change
  must archive **after** complete-tool-curation (or its BND-8 delta be rebased on the main spec at that time).
- **Data:** an Alembic migration adds the cached member prompts and resources per server and their per-bundle curation.
- **API:** `GET/PUT /api/v1/bundles/{name}/member-prompts[/{prompt_id}]` and `…/member-resources[/{resource_id}]`;
  regenerate `apps/web/openapi.json` and `apps/web/types/api.d.ts`.
- **Code:** `domain/servers/` (cached entries, sync), `domain/bundles/` (curation entities, view), the discovery probe
  and service, the `prompts/*` and `resources/*` handlers, repositories (Postgres and in-memory), the bundle page.
- **Not covered:** export/import and bootstrap of this curation (follow-up for
  [add-export-import](../add-export-import/proposal.md) if this goes ahead); resource templates.
- **Docs:** `docs/manage/bundles.md`, `docs/integrate/management-api.md`, arc42 §5 and §8. A new ADR (next free
  number) records the decision to cache member prompt and resource listings for curation only, which partly reverses
  the "no cache for prompts/resources" stance of ADR-0021.
