## MODIFIED Requirements

### Requirement: UPS-10 Protocol era per upstream
Protocol era per upstream ([PROT-21](../protocol/spec.md)): a server MUST have a `protocol_mode`. It is `auto`
(default: probe `server/discover`, fall back to `initialize`), `session` (always the `initialize` handshake and its
session, for upstreams whose tools need server-initiated requests), or a pinned modern revision (`YYYY-MM-DD`).
`legacy` is accepted on every write (API, bootstrap and import) as a deprecated alias of `session` and stored as
`session`. Every read and export returns `session`, never `legacy`. The published schema lists `auto` and `session` as
an enum beside the revision pattern. Discovery records the negotiated revision as `protocol_version`, shown in the API
and UI so an operator can see which upstreams still speak the handshake era. An update that omits `protocol_mode`
keeps the stored value rather than resetting it to `auto`.

#### Scenario: Omitted mode is kept on update
- **WHEN** a server stored with `protocol_mode: session` is updated without `protocol_mode`
- **THEN** it keeps `protocol_mode: session`

#### Scenario: Invalid mode is rejected
- **WHEN** a server is written with `protocol_mode: newest`
- **THEN** the API answers `422`

#### Scenario: The deprecated alias is accepted and read back by its name
- **WHEN** a server is written through the API with `protocol_mode: legacy`
- **THEN** the write succeeds, the response and every later read carry `protocol_mode: session`, and the gateway
  always negotiates with it through the `initialize` handshake

#### Scenario: A bootstrap or import document may use the alias
- **WHEN** a bootstrap or import document lists an upstream with `protocol_mode: legacy`
- **THEN** the upstream is created with `protocol_mode: session`, and an export of it says `session`

#### Scenario: A server stored before the rename reads by its new name
- **GIVEN** a server whose `protocol_mode` was stored as `legacy` by an earlier release
- **WHEN** it is read through the API or exported
- **THEN** it carries `protocol_mode: session`

#### Scenario: The named modes are published as an enum
- **WHEN** a client reads the OpenAPI document
- **THEN** `protocol_mode` on the server write and read schemas offers `auto` and `session` as enum values beside a
  `YYYY-MM-DD` string pattern, and does not list `legacy`

#### Scenario: Negotiated revision is recorded
- **WHEN** discovery succeeds against an upstream
- **THEN** the revision it negotiated is stored as `protocol_version` and returned by the API
