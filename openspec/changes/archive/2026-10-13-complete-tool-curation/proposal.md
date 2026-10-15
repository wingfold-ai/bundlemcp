# Proposal

## Why

Tool curation is the core of what a bundle offers, and three parts of it fall short of what was specified. A tool that
vanished upstream is still listed and callable until an admin disables it, and nothing removes it for good. An override
name is checked only against other override names, so it can shadow a prefixed name. And the curation UI silently wipes
description and annotation overrides set through the API whenever a row is saved (`saveCuration` in
`apps/web/app/pages/bundles/[name].vue` always sends `override_description: null` and omits `override_annotations`).
Member order is also fixed to server-name order, so an admin cannot say which member wins a resource URI collision.

## What Changes

- **Vanished tools stop being served** (UPS-19): a tool the latest successful discovery did not list is stale; it is
  absent from `tools/list`, rejected on `tools/call`, and comes back with its curation if it reappears. Going stale and
  coming back count as a change of the tool set, so live clients re-list.
- **Refresh & prune** (UPS-19): `POST /api/v1/upstreams/{name}:refresh-tools?prune=true` probes now and, only if the
  probe succeeds, deletes the stale tools and their curation in every bundle. The UI offers it on the upstream page.
- **Write-free sync in the common case** (UPS-18): a discovery run that finds nothing new, changed, vanished or
  reappeared writes no tool row. See the decision below.
- **Override names unique against prefixed names** (BND-14): validated on write against every other override and every
  prefixed name of the bundle, and re-checked when a member is added or a member upstream is renamed.
- **Full curation UI** (BND-16): inline editing of override name, title, description and annotations; saving a row never
  clears an override the row does not show; stale tools are flagged. **Bug fix** for the wiped overrides above.
- **Curation API returns everything it accepts** (BND-17): `GET /api/v1/bundles/{name}/tools` also returns
  `override_annotations` and whether the tool is stale.
- **Admin-controlled member order** (BND-1, BND-8): members keep a position the admin sets; resource de-duplication and
  fan-out follow it. Existing bundles are migrated to today's server-name order, so nothing changes until an admin
  reorders.
- Docstrings and field descriptions in `domain/servers/tool_sync.py`, `application/discovery/discovery_service.py`,
  `domain/servers/tool.py` and `application/schemas/tools/tool_read.py` already claim vanished tools stop being served;
  they are made true here, and `docs/manage/bundles.md` (which already claims BND-14's prefixed-name check) is aligned.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `bundles`: BND-14 (uniqueness against prefixed names, re-checked on membership and rename), BND-16 (full
  curation UI, stale flag, no wiped overrides), BND-17 (curation listing returns annotation overrides and staleness).
- `upstreams`: UPS-18 (write-free sync in the common case), UPS-19 (stale tools are not served; refresh & prune).
- `bundles`: BND-1 (admin-controlled member order), BND-8 (first-member-wins and fan-out follow that order).
- `protocol`: PROT-25 (the tool filter drops stale tools as well as disabled ones).

## Decision

**UPS-18 — write-free sync: build it** (option 1 of the three the proposal offered; the alternatives were to batch the
`last_seen_at` write into one statement per run, or to amend UPS-18 to today's per-row write). A tool records when it
*goes* stale instead of when it was last seen, so an unchanged run writes no tool row. `last_seen_at` stays a published
field, derived from the server's last successful discovery, or from `stale_since` for a stale tool.

## Impact

- **API:** `GET /api/v1/bundles/{name}/tools` gains `override_annotations` and `stale`; `GET /upstreams/{name}/tools`
  gains `stale`; `:refresh-tools` accepts `prune` and reports `pruned`; membership writes accept a `position`, and
  `GET /bundles/{name}/upstreams` returns members in that order. Regenerate `apps/web/openapi.json` and
  `apps/web/types/api.d.ts`.
- **Behaviour change:** clients stop seeing tools that vanished upstream; an admin who relied on a vanished tool still
  being listed sees it disappear. Override writes that collide with a prefixed name now answer `409`.
- **Data:** an Alembic migration adds a member position (backfilled in server-name order), the stale marker on cached
  tools and the server's last discovery time (backfilled from the newest `last_seen_at` of its tools), and drops
  `tools.last_seen_at`.
- **Code:** `domain/servers/tool_sync.py`, `domain/bundles/` (view composition, membership), `application/discovery/`,
  `application/management/bundle_service.py` and `server_service.py`, the Postgres and in-memory repositories, the
  bundle and upstream pages of `apps/web`.
- **Docs:** `docs/manage/bundles.md`, `docs/manage/servers.md`, `docs/integrate/management-api.md`.
- **Related changes:** [complete-admin-ui](../../complete-admin-ui/proposal.md) takes the stale badges and "refresh &
  prune" from here (UI-1). [add-member-prompt-curation](../../add-member-prompt-curation/proposal.md) also modifies
  BND-8 and must archive after this change. [add-export-import](../../add-export-import/proposal.md) should carry the
  member position in its document once both land.
- No ADR: the change completes existing decisions (ADR-0038 periodic refresh) rather than making a new one.
