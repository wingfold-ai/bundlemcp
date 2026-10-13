# ADR-0046: Profiles are registered presets; the served tool set is built by ordered stages

**Status:** accepted · **Date:** 2026-10-13 · **Amends:** [ADR-0007](0007-endpoint-profiles.md)

## Context

ADR-0007 made endpoint profiles code presets. In the code, a preset was not one thing: each profile was spread over
four places that branched on its name.

| Concern | Where it lived |
|---|---|
| Identifier | the `EndpointProfile` enum |
| Which auth modes an endpoint may combine with it | `if`s in the endpoint write DTO's validator |
| What it does to the served tools | an `if profile != CHATGPT` in the tool presentation function |
| Its description and warning in the management API | a hard-coded list in the endpoint controller |

Adding a fourth profile — the ChatGPT `search`/`fetch` connector on the roadmap — meant touching all four and keeping
them consistent by hand. The same presentation function applied the curation filter, the profile rewrite and the
per-tool overrides in one body, so their order (which decides that an explicit override wins over a profile, BND-15)
was implicit.

## Decision drivers

- Adding a profile should be one class and one registration, with nothing else branching on a profile's name (EP-14).
- The order of curation filter, profile and overrides must be explicit and tested, because it is a contract.
- Behaviour must not change: every existing endpoint, profile and curation test passes unmodified.

## Decision

- **A profile is a preset implementing one interface** (`domain/endpoints/profiles/`): its identifier, description and
  optional warning, `check_auth_modes` (raises when an endpoint may not use those modes with it), and `transform`
  (the tool as the profile presents it, or `None` to hide it). The three shipping profiles are three classes.
- **One catalogue registers them** (`ProfileCatalog`). It must cover every `EndpointProfile` member, so a
  half-registered profile fails at construction. The enum stays the stored identifier and the OpenAPI enum.
- **The catalogue is a collaborator, not a global.** The composition root builds it and hands it to the endpoint
  service (write validation), a `ProfileService` (the management API's listing) and the bundle view loader (the served
  tools); a test app can register its own.
- **The served tool set is built by ordered stages** (`domain/bundles/tool_pipeline.py`): curation filter, then the
  endpoint's profile, then the per-tool overrides, which therefore win. The result backs both `tools/list` and
  `tools/call`, so a tool a stage drops is also refused on call.
- **The profile's auth-mode rule is checked by the endpoint service**, against the catalogue, and answers 422 with the
  same message as before. The request DTO keeps only the profile-independent rules (`none` alone and explicitly
  allowed). A DTO validator cannot receive an injected catalogue; bootstrap goes through the same service.

## Alternatives considered

- **Keep the name branches and reword the specs** to describe them. Cheapest; leaves a fourth profile touching four
  files and the stage order implicit.
- **A module-level catalogue the DTO validator reads.** Keeps the 422 coming from request validation, but a test, or a
  deployment, cannot register its own catalogue without patching a global.
- **Replace the enum by strings validated against the catalogue.** Removes one registration step, but loses the
  OpenAPI enum the generated TypeScript union and the UI's profile select are built from.
- **Apply the stages per request in the `tools/list` and `tools/call` handlers.** A true per-method middleware chain;
  it repeats per request what the composed view does once, and splits one rule across two handlers. Whether metering
  and audit join one chain with these stages is open in the `align-metering-contract` change (PROT-25).

## Consequences

**Positive:**

- A new profile is one enum member, one preset class and one catalogue entry; a test enforces that the catalogue and the
  enum agree.
- A profile can now hide a tool, which the original EP-13 scenario asked for and nothing supported.
- The stage order is a list a test asserts, not the line order of one function.

**Trade-offs:**

- A violated profile rule is now reported by the service as a plain 422 message rather than inside Pydantic's
  validation-error list; the status code and the message text are unchanged.
- Three more collaborators carry the catalogue (endpoint service, bootstrap runner, admission gate).
