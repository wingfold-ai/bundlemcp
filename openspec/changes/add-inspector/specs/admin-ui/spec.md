## ADDED Requirements

### Requirement: UI-8 Inspector targets
The inspector SHALL connect to three kinds of target: (a) any registered upstream server, using its stored
configuration — static headers and upstream OAuth applied server-side, secrets never sent to the browser; (b) any
endpoint of this gateway, exercising the full public path (authentication, profile, curation, metering); (c) an
arbitrary URL with headers entered ad hoc.

#### Scenario: A registered upstream uses its stored credentials
- **GIVEN** upstream `weather` registered with a static `Authorization` header
- **WHEN** an admin inspects `weather`
- **THEN** the upstream receives the stored header, and no response to the browser contains its value

#### Scenario: An endpoint is inspected through its public path
- **GIVEN** endpoint `b1-chatgpt` with the ChatGPT profile and a disabled tool in its bundle
- **WHEN** an admin lists tools of `b1-chatgpt` in the inspector with a valid credential for it
- **THEN** the list matches what a client of that endpoint sees: curated, profile-annotated, without the disabled tool

#### Scenario: An ad-hoc URL is inspected with the entered headers
- **WHEN** an admin enters a URL and a header and connects
- **THEN** the gateway connects to that URL with that header and stores neither

### Requirement: UI-9 Inspector operations
The inspector SHALL support `initialize` with the target's capabilities shown, `ping`, `tools/list` with each tool's
schema, and `tools/call` with a form generated from the tool's input schema and a raw-JSON fallback. It SHALL show the
response or error, progress notifications received during a call, and the time each request took.

#### Scenario: Capabilities are shown after initialize
- **WHEN** an admin connects to a target
- **THEN** the UI shows the server's name, version, negotiated protocol revision and advertised capabilities

#### Scenario: A call is built from the input schema
- **GIVEN** a tool whose input schema has a required string `city`
- **WHEN** the admin opens the tool
- **THEN** a form with a required `city` field is shown, and switching to raw JSON shows the same arguments

#### Scenario: Progress and timing are shown
- **WHEN** a called tool sends two progress notifications before its result
- **THEN** the UI shows both progress notifications as they arrive, then the result and the request's duration

#### Scenario: An error result is displayed
- **WHEN** a call returns a JSON-RPC error or a result with `isError: true`
- **THEN** the UI shows the error content rather than an empty result

### Requirement: UI-10 Traffic is proxied by the management API
The browser MUST never talk to an inspector target directly: the management API proxies inspector traffic,
authenticated like every management route ([MGMT-2](../../../../specs/management/spec.md)), so stored secrets stay
server-side and no target needs CORS. Ad-hoc URL targets MUST pass the egress policy
([SEC-1, SEC-2](../../../../specs/security/spec.md)).

#### Scenario: Inspector requests need management credentials
- **WHEN** an inspector route is called without an admin session or service API key
- **THEN** it is refused as unauthenticated and no target is contacted

#### Scenario: A blocked ad-hoc URL is refused
- **WHEN** an admin inspects an ad-hoc URL that resolves to a blocked range
- **THEN** no request is sent to it and the inspector reports `egress_denied`

### Requirement: UI-11 Inspector calls are attributed
Inspector calls against **endpoints** SHALL go through the real public path and be audited like any client call
([OPS-1](../../../../specs/operations/spec.md)). Calls against upstreams and ad-hoc URLs bypass the endpoint context:
they MUST be marked `source=inspector` in the logs and MUST NOT create audit records.

#### Scenario: An endpoint call is audited
- **WHEN** an admin calls a tool through an endpoint in the inspector
- **THEN** one audit record is written for it, as for any client of that endpoint

#### Scenario: An upstream call is logged, not audited
- **WHEN** an admin calls a tool on upstream `weather` directly in the inspector
- **THEN** the call's log events carry `source=inspector` and no audit record is written
