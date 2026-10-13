# Proposal

## Why

Endpoint profiles were specified as a small interface (constrain auth modes, transform tools) applied as a stage at the
endpoint layer. Today a profile is spread across four places that each branch on its name: the `EndpointProfile`
StrEnum, the `EndpointUpsert.auth_and_profile_rules` validator, an `if` in `domain/bundles/tool_presentation.py`, and
the hard-coded `PROFILES` list in `api/management/controllers/endpoint_controller.py`. A fourth profile — the ChatGPT
`search`/`fetch` connector on the roadmap — would mean touching all four and keeping them consistent by hand.

## What Changes

- A profile becomes one object implementing one small interface: its name, description and optional warning, the
  auth-mode rule it enforces (EP-15), and the transform it applies to served tools. A single catalogue of profiles is
  the only place a profile is registered.
- The endpoint write validation, the profile listing of the management API, and the tool presentation all ask the
  catalogue instead of branching on a profile's name (EP-14).
- The profile transform runs as a named stage of the endpoint's tool pipeline — curation filter, profile transform,
  per-tool overrides — whose output backs both `tools/list` and `tools/call` (EP-13). Disabled-tool enforcement is the
  first stage of the same pipeline (BND-13).
- No client-visible behaviour of the three shipping profiles changes; the existing EP-10…EP-15 tests must pass
  unchanged.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `endpoints`: EP-13 (transforms as a pluggable stage at the endpoint layer, in list and call) and EP-14
  (adding a profile is implementing one interface and registering it).
- `bundles`: BND-13 (disabled-tool enforcement is a stage of that pipeline).

## Open decision

**EP-13 and BND-13 — build the stage, or amend the wording.** The original specs said profile transforms and the
disabled-tool filter are "middleware". What exists is a shared, per-request `BundleView` composed once and used by both
`tools/list` and `tools/call`, which already guarantees list and call agree. The maintainers choose:

1. **Build** (the deltas as written, recommended): make the composition an explicit, ordered list of stages behind one
   interface, of which the profile transform is one. This is what makes EP-14's "one small interface" true.
2. **Amend**: keep the composed view as it is and reword EP-13 and BND-13 to describe it ("applied when the endpoint's
   served tool set is built"), dropping both deltas; EP-14 can still be built on its own.

This decision should be taken together with PROT-25 in
[align-metering-contract](../align-metering-contract/proposal.md), which asks the same question for the whole
`tools/call` pipeline. Note that PROT-25 lists overrides *before* the profile transform while BND-15 requires overrides
to win; the stage order here (profile, then overrides) is the one that satisfies BND-15.

## Impact

- **Code:** new `domain/endpoints/profiles/` (the interface, the three profiles, the catalogue);
  `domain/bundles/tool_presentation.py` becomes the pipeline of stages;
  `application/schemas/endpoints/endpoint_upsert.py` delegates the profile rule; the profile list moves out of
  `endpoint_controller.py` into a service the controller calls. No database, DTO shape or route change; the OpenAPI
  document changes only if descriptions move.
- **ADR:** a new ADR (next free number) records profiles as a registered interface and the tool pipeline as ordered
  stages, superseding the "if-on-name" shape.
- **Docs:** `docs/manage/endpoints.md` (profiles) and the arc42 building-block view (§5) for the new domain package.
- **Related changes:** [align-metering-contract](../align-metering-contract/proposal.md) (PROT-25, see above);
  [align-management-api](../align-management-api/proposal.md) may move the profile listing route (MGMT-1), which this
  change does not depend on.
