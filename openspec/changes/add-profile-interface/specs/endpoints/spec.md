## MODIFIED Requirements

### Requirement: EP-13 Where profile transforms apply
Profile transforms SHALL be applied as a pluggable stage of the endpoint's tool pipeline at the endpoint layer — after
bundle curation decides which tools are served and before per-tool annotation overrides are merged
([BND-15](../../../../specs/bundles/spec.md)) — and the output of that pipeline SHALL back both `tools/list` and
`tools/call` validation, so a call is checked against exactly the transformed tool the list presented.

#### Scenario: List and call see the same transformed tool
- **GIVEN** a `chatgpt`-profile endpoint and a tool disabled in the bundle
- **WHEN** a client lists tools and calls the disabled tool
- **THEN** the disabled tool is absent from the list and rejected on call, and every listed tool carries the profile's
  annotations

#### Scenario: Overrides are applied after the profile stage
- **GIVEN** a `chatgpt`-profile endpoint and a tool with the annotation override `{"readOnlyHint": false}`
- **WHEN** a client lists tools
- **THEN** the tool's `readOnlyHint` is `false` and its `destructiveHint` is `false`

#### Scenario: A profile that hides a tool hides it from calls too
- **GIVEN** an endpoint whose profile's transform drops a tool from the served set
- **WHEN** a client calls that tool by its presented name
- **THEN** the gateway answers the same unknown-tool error as for a disabled tool and contacts no upstream

### Requirement: EP-14 Profiles are code presets listed by the API
Adding a new profile SHALL be a code change that implements one small interface — the profile's name, description and
optional warning, the auth-mode constraint it enforces on endpoint writes (EP-15), and the transform it applies to
served tools — and registers it in the gateway's single profile catalogue; no other part of the gateway branches on a
profile's name. The management API MUST list the registered profiles (name, description, and an optional warning) so
the UI stays data-driven.

#### Scenario: Profiles are listed
- **WHEN** an admin requests the profile listing from the management API
- **THEN** the response lists `default`, `claude` and `chatgpt` with descriptions, and `chatgpt` carries a warning

#### Scenario: A registered profile is used everywhere
- **GIVEN** a profile registered in the catalogue with an auth-mode constraint and a tool transform
- **WHEN** an admin lists profiles, writes an endpoint with that profile, and a client lists and calls tools on it
- **THEN** the profile is listed, endpoint writes violating its constraint are rejected with a validation error naming
  the profile, and its transform is applied to the served tools
