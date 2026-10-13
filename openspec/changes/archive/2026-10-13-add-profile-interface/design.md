# Design

## Context

See [proposal.md](proposal.md) for the motivation. Today:

- `domain/endpoints/endpoint_profile.py` — `EndpointProfile` StrEnum, persisted on the endpoint row and published in
  the OpenAPI document (the generated TS union drives the UI's profile select).
- `application/schemas/endpoints/endpoint_upsert.py` — `auth_and_profile_rules` holds the EP-15 matrix as `if`s on
  the enum.
- `domain/bundles/tool_presentation.py` — `profile_annotations` branches on `CHATGPT`; `present_tool` applies the
  curation filter, the profile rewrite and the overrides in one function.
- `application/serving/bundle_view_loader.py` — calls `present_tool` per cached tool to build the `BundleView` that
  backs `tools/list` and `tools/call`.
- `api/management/controllers/endpoint_controller.py` — a module-level `PROFILES` list of `EndpointProfileRead`.

## Goals / Non-Goals

**Goals:**

- One class per profile; one registration point; no branching on profile names outside it.
- The tool pipeline is an explicit ordered list of stages, with the ordering that BND-15 needs (curation filter,
  profile, overrides), backing list and call.
- Behaviour-preserving: every existing endpoint-profile (EP-10..15) and curation (BND-12..17) test passes unchanged.

**Non-Goals:**

- User-defined or scriptable profiles (endpoint-profiles out of scope).
- Moving metering or audit into the same stage list; that is PROT-25's question
  ([align-metering-contract](../align-metering-contract/proposal.md)).
- The ChatGPT `search`/`fetch` profile itself.

## Decisions

### The profile interface lives in the domain

`domain/endpoints/profiles/` holds a `@runtime_checkable` `Protocol` `EndpointProfilePreset` with `name`,
`description`, `warning`, `check_auth_modes(modes, allow_unauthenticated) -> None` (raises a domain `ValueError` whose
message names the profile and the rule) and `transform(tool: PresentedTool) -> PresentedTool | None`. One module per
profile (`default_profile.py`, `claude_profile.py`, `chatgpt_profile.py`) and a `ProfileCatalog` (frozen Pydantic model
holding the presets keyed by `EndpointProfile`) with `get(profile)` and `all()`. Everything here is pure and I/O-free,
so it belongs in `domain/`.

*Alternative:* put the presets in `application/`. Rejected: the transform is a domain rule over domain entities, and
`tool_presentation.py`, its only consumer at serve time, is already domain.

### The StrEnum stays as the persisted identifier

The enum remains the stored value and the OpenAPI enum. Adding a profile is: one enum member, one preset class, one
catalogue entry. A domain test asserts the catalogue and the enum have exactly the same members, so a half-registered
profile fails CI rather than at runtime.

*Alternative:* replace the enum by a string validated against the catalogue. Rejected: the generated TypeScript union
and the database check would be lost, and the UI's profile select would need another source of truth.

### The tool pipeline is a list of stages

`domain/bundles/tool_pipeline.py` defines a `ToolStage` protocol (`apply(tool, context) -> PresentedTool | None`) and
the pipeline `[CurationFilter, ProfileStage(preset), OverrideStage]`. `CurationFilter` drops disabled tools (BND-13) and
— once [complete-tool-curation](../complete-tool-curation/proposal.md) lands — stale ones; `ProfileStage` delegates to
the endpoint's preset; `OverrideStage` applies the name, title, description and annotation overrides (BND-14, BND-15).
`bundle_view_loader.py` (application) runs the pipeline per cached tool; the resulting `BundleView.tools` is what both
`tools/list` and `tools/call` resolve against, so a stage that drops a tool drops it from both.

*Alternative:* apply stages at dispatch time in the `tools/list` and `tools/call` handlers (a true per-method
middleware chain). Rejected for this change: it duplicates work per request that the composed view does once, and
would split one rule across two handlers. It remains open under PROT-25.

### Write validation and listing ask the catalogue

The catalogue is a collaborator, not a module-level global: the composition root builds it (`ProfileCatalog.builtin()`,
or `CompositionOverrides.profiles` in a test) and hands it to the endpoint service, a `ProfileService` and the bundle
view loader, so a test app can register its own preset (task 2.4).

That decides where the EP-15 rule runs. A Pydantic validator on `EndpointUpsert` cannot receive an injected catalogue,
so `EndpointService.upsert` calls `profiles.get(body.profile).check_auth_modes(...)` and turns a
`ProfileRuleViolation` into `InvalidInputError` — still a 422 with the same message. The DTO keeps the
profile-independent EP-3 rules. Bootstrap goes through the same service, so it is checked too.

*Alternative:* the DTO validator reads a module-level catalogue (the first version of this design). Rejected during
implementation: it makes the catalogue a global a test or deployment can only replace by patching.

The profile list moves to `application/management/profile_service.py` (`ProfileService.list() ->
list[EndpointProfileRead]`), reached through a `get_profile_service` provider; the controller handler calls that one
method. The route path does not change here.

## Risks / Trade-offs

- [A behaviour change hides in the refactor] → The change is gated on the existing EP-10…6, BND-13…4 and BND-3 tests
  passing unmodified; new tests only add the registered-profile scenario.
- [Stage order regresses BND-15] → A domain test asserts the order (curation, profile, overrides) and the BND-15
  scenario.
- [Validation messages change wording] → The messages keep the profile name and the `(EP-15)` marker; UI tests that
  match on them are run.

## Migration Plan

No data migration. Ships as a refactor; rollback is a revert.
