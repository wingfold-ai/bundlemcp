## MODIFIED Requirements

### Requirement: BND-13 Disabled tools are hidden and rejected
Disabled tools MUST be absent from `tools/list` **and** rejected on `tools/call` with a standard MCP error —
enforcement in both paths, as the first stage of the endpoint's tool pipeline, ahead of the profile transform
([EP-13](../endpoints/spec.md)) and the per-tool overrides, whose output backs both paths.

#### Scenario: Disabled tool is hidden from the list
- **GIVEN** tool `echo__say` is disabled in the bundle
- **WHEN** a client calls `tools/list` on an endpoint of the bundle
- **THEN** `echo__say` is not in the result

#### Scenario: Disabled tool is rejected on call
- **GIVEN** tool `echo__say` is disabled in the bundle
- **WHEN** a client calls `tools/call` with name `echo__say`
- **THEN** the gateway answers with a JSON-RPC invalid-params error (`-32602`) naming the unknown tool
- **AND** no upstream call is made

#### Scenario: A disabled tool never reaches the profile transform
- **GIVEN** tool `echo__say` is disabled in a bundle served through a `write_as_read`-profile endpoint
- **WHEN** a client lists tools
- **THEN** `echo__say` is absent, and no override name of `echo__say` is presented either

### Requirement: BND-15 Annotation overrides as a shallow merge
Annotation overrides SHALL be a shallow merge over the upstream annotations (setting a key to `null` removes it). This
is the same mechanism the `write_as_read` profile uses programmatically ([endpoint profiles](../endpoints/spec.md));
explicit per-tool overrides MUST win over profile rewrites.

#### Scenario: Override merges and removes keys
- **GIVEN** an upstream tool annotated `{"readOnlyHint": false, "openWorldHint": true}`
- **WHEN** the bundle overrides annotations with `{"readOnlyHint": true, "openWorldHint": null}`
- **THEN** the tool is presented with `{"readOnlyHint": true}`

#### Scenario: Explicit override wins over the chatgpt profile
- **GIVEN** a tool with an annotation override `{"readOnlyHint": false}` served through a
  `write_as_read`-profile endpoint
- **WHEN** a client lists tools
- **THEN** the tool's `readOnlyHint` is `false`, while `destructiveHint` is still rewritten to `false` by the profile

### Requirement: BND-30 Profiles do not rewrite
Endpoint profiles ([endpoint profiles](../endpoints/spec.md)) MUST NOT rewrite bundle prompts or resources.

#### Scenario: chatgpt endpoint serves prompts unchanged
- **GIVEN** a `write_as_read`-profile and a `default`-profile endpoint over the same bundle
- **WHEN** a client calls `prompts/get` for a bundle prompt on each
- **THEN** both return identical messages
