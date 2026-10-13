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
- **GIVEN** tool `echo__say` is disabled in a bundle served through a `chatgpt`-profile endpoint
- **WHEN** a client lists tools
- **THEN** `echo__say` is absent, and no override name of `echo__say` is presented either
