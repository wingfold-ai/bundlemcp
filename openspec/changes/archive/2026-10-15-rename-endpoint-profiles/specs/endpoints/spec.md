## RENAMED Requirements

- FROM: `### Requirement: EP-11 claude profile`
- TO: `### Requirement: EP-11 oauth_only profile`

- FROM: `### Requirement: EP-12 chatgpt profile re-annotation`
- TO: `### Requirement: EP-12 write_as_read profile re-annotation`

## MODIFIED Requirements

### Requirement: EP-4 Profile and rate limits per endpoint
Each endpoint SHALL have a `profile` shaping its tool surface ([endpoint profiles](../endpoints/spec.md)) and
optional rate limits ([rate limiting](../endpoints/spec.md)).

#### Scenario: Two endpoints present one bundle differently
- **GIVEN** endpoints `main` (profile `default`) and `gpt` (profile `write_as_read`) over the same bundle
- **WHEN** a client lists tools on each
- **THEN** `gpt` presents every tool with `readOnlyHint: true` while `main` passes annotations through

### Requirement: EP-11 oauth_only profile
The `oauth_only` profile admits signed-in people only. claude.ai's remote MCP connector is the client it is
recommended for, and any client that signs a person in through OAuth can use it:

- MUST have `oauth` in `auth_modes` (validated on endpoint write, see EP-15);
- SHALL pass tools through untransformed;
- guarantees the OAuth discovery surface such a client needs: dynamic client registration, PKCE, `.well-known` metadata
  ([OAuth server](../auth/spec.md)).

#### Scenario: claude endpoint without oauth is rejected
- **WHEN** an admin writes an `oauth_only`-profile endpoint with `auth_modes: [api_key]`
- **THEN** the management API rejects the write with a validation error

#### Scenario: claude endpoint tools are passthrough
- **GIVEN** an `oauth_only`-profile endpoint
- **WHEN** a client lists tools
- **THEN** each tool's annotations are the upstream annotations with only the bundle's per-tool overrides applied

### Requirement: EP-12 write_as_read profile re-annotation
The `write_as_read` profile presents write tools as read-only. ChatGPT's connector, which restricts or behaves
differently toward write tools, is the client it is recommended for:

- **re-annotates write tools as read-safe**: every served tool's annotations SHALL be rewritten so the client treats it
  as read-only — `readOnlyHint: true`, `destructiveHint: false`, `openWorldHint` preserved. The tools **still perform
  their real (write) operations upstream**; only the presented annotations change. This is the user-chosen semantic:
  expose everything, shaped to what the client accepts.
- The UI MUST display a clear warning on write_as_read-profile endpoints that annotations no longer reflect true tool
  behavior, and the audit log records calls normally so writes remain traceable.
- Explicit per-tool overrides ([BND-15](../bundles/spec.md)) MUST win over the profile rewrite.

#### Scenario: Every tool is presented as read-safe
- **GIVEN** a `write_as_read`-profile endpoint over a tool annotated `{"readOnlyHint": false, "destructiveHint": true,
  "openWorldHint": true}`
- **WHEN** a client lists tools
- **THEN** the tool is presented with `readOnlyHint: true`, `destructiveHint: false` and `openWorldHint: true`

#### Scenario: Call still performs the real operation and is audited
- **GIVEN** a `write_as_read`-profile endpoint
- **WHEN** a client calls a write tool
- **THEN** the upstream tool runs as usual and the call is recorded in the audit log

#### Scenario: UI warns on a chatgpt endpoint
- **WHEN** an admin selects the `write_as_read` profile for an endpoint
- **THEN** the UI shows a warning that annotations no longer reflect true tool behavior

### Requirement: EP-13 Where profile transforms apply
Profile transforms SHALL be applied as a pluggable stage of the endpoint's tool pipeline at the endpoint layer — after
bundle curation decides which tools are served and before per-tool annotation overrides are merged
([BND-15](../bundles/spec.md)) — and the output of that pipeline SHALL back both `tools/list` and
`tools/call` validation, so a call is checked against exactly the transformed tool the list presented.

#### Scenario: List and call see the same transformed tool
- **GIVEN** a `write_as_read`-profile endpoint and a tool disabled in the bundle
- **WHEN** a client lists tools and calls the disabled tool
- **THEN** the disabled tool is absent from the list and rejected on call, and every listed tool carries the profile's
  annotations

#### Scenario: Overrides are applied after the profile stage
- **GIVEN** a `write_as_read`-profile endpoint and a tool with the annotation override `{"readOnlyHint": false}`
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
- **THEN** the response lists `default`, `oauth_only` and `write_as_read` with descriptions, and `write_as_read`
  carries a warning

#### Scenario: A registered profile is used everywhere
- **GIVEN** a profile registered in the catalogue with an auth-mode constraint and a tool transform
- **WHEN** an admin lists profiles, writes an endpoint with that profile, and a client lists and calls tools on it
- **THEN** the profile is listed, endpoint writes violating its constraint are rejected with a validation error naming
  the profile, and its transform is applied to the served tools

### Requirement: EP-15 Profile × auth-mode validation matrix
The following matrix MUST be enforced on endpoint create/update:

| Profile | Allowed `auth_modes` |
|---|---|
| `oauth_only` | exactly `[oauth]` |
| `write_as_read` | must include `oauth` or `api_key`; bare `[none]` rejected |
| `default` | any valid combination per [EP-3](../endpoints/spec.md) |

#### Scenario: claude requires exactly oauth
- **WHEN** an admin writes an `oauth_only`-profile endpoint with `auth_modes: [oauth, api_key]`
- **THEN** the write is rejected with a validation error naming the profile rule

#### Scenario: chatgpt rejects an open endpoint
- **WHEN** an admin writes a `write_as_read`-profile endpoint with `auth_modes: [none]` and
  `allow_unauthenticated: true`
- **THEN** the write is rejected with a validation error

#### Scenario: default accepts any valid combination
- **WHEN** an admin writes a `default`-profile endpoint with `auth_modes: [oauth, api_key]`
- **THEN** the write succeeds

## ADDED Requirements

### Requirement: EP-23 Profile identifiers name what the profile changes
A profile's identifier SHALL name what the profile does to an endpoint, never the client it was built for, so that
the name stays true when clients change. The identifiers are `default`, `oauth_only` and `write_as_read`. They are the
only values the management API, the profile listing and bootstrap files accept. The former identifiers `claude` and
`chatgpt` MUST be rejected with a validation error that lists the accepted values. An upgrade MUST migrate every stored
endpoint from a former identifier to its successor (`claude` → `oauth_only`, `chatgpt` → `write_as_read`), so the
endpoint keeps its URL and behaviour without an admin acting.

#### Scenario: A former identifier is rejected on write
- **WHEN** an admin writes an endpoint with `profile: chatgpt`
- **THEN** the management API answers `422` with a validation error that lists `default`, `oauth_only` and
  `write_as_read`

#### Scenario: A bootstrap file with a former identifier fails at start-up
- **GIVEN** a bootstrap file that declares an endpoint with `profile: claude`
- **WHEN** the gateway starts
- **THEN** loading the file fails with a validation error naming the endpoint's profile field

#### Scenario: Stored endpoints are migrated on upgrade
- **GIVEN** a database with endpoint `a` stored with profile `claude` and endpoint `b` stored with profile `chatgpt`
- **WHEN** the database is upgraded
- **THEN** `GET /api/v1/endpoints/a` reports profile `oauth_only` and `GET /api/v1/endpoints/b` reports profile
  `write_as_read`, and both serve their tools as before
