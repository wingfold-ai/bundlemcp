## RENAMED Requirements

- FROM: `### Requirement: MGMT-10 Initial service key`
- TO: `### Requirement: MGMT-10 API keys at bootstrap`

## MODIFIED Requirements

### Requirement: MGMT-8 Document sources
The gateway SHALL read a bootstrap document from `BUNDLEMCP_BOOTSTRAP_FILE` (path to a YAML/JSON file,
compose-friendly) and/or `BUNDLEMCP_BOOTSTRAP` (the same document inline as JSON); when both are set, the file is
applied first, then the inline document. The document SHALL be a Pydantic-validated model carrying a format `version`
(only `1` exists; any other value is rejected) and the lists `upstreams`, `bundles`, `endpoints` and `api_keys`
(MGMT-10).

#### Scenario: Both sources apply
- **GIVEN** `BUNDLEMCP_BOOTSTRAP_FILE` names a file registering upstream `filed` and `BUNDLEMCP_BOOTSTRAP` inlines a
  document registering upstream `echo`
- **WHEN** the gateway starts
- **THEN** both `filed` and `echo` are registered

#### Scenario: Unknown version is refused
- **WHEN** a document declares `"version": 2`
- **THEN** it fails validation instead of being applied

#### Scenario: Document declares API keys
- **WHEN** a document lists an entry under `api_keys`
- **THEN** it validates, and the key is provisioned when the document is applied

### Requirement: MGMT-10 API keys at bootstrap
Each `api_keys` entry SHALL name a key, its kind and, for an endpoint-kind key, its endpoints by name, and take its
value from a named environment variable — the document never holds a key value — or as `create_if_missing`, generated
and written to the file the entry names, created with mode `0600`; the value never appears in a log line. A file that
already exists is never overwritten: when it holds a well-formed `bmcp_sk_…` value that value is used, otherwise the
document does not land. A key whose name already exists is never overwritten. When
`BUNDLEMCP_INITIAL_SERVICE_KEY` is set and no service key exists, the gateway SHALL also provision a service key with
that value.

#### Scenario: First boot provisions the key
- **GIVEN** no service-kind key exists and `BUNDLEMCP_INITIAL_SERVICE_KEY` is set
- **WHEN** the gateway starts
- **THEN** a service key with that value exists and authenticates management calls

#### Scenario: Existing service key is kept
- **GIVEN** a service-kind key already exists
- **WHEN** the gateway starts with `BUNDLEMCP_INITIAL_SERVICE_KEY` set
- **THEN** no key is created or changed

#### Scenario: Key value from an environment reference
- **GIVEN** an `api_keys` entry `registrar` of kind `service` naming the variable `REGISTRAR_KEY`, and that variable
  holds a well-formed `bmcp_sk_…` value
- **WHEN** the gateway starts with no key named `registrar`
- **THEN** a service key `registrar` exists, authenticates with the variable's value, and only its hash is stored

#### Scenario: Missing referenced variable invalidates the document
- **GIVEN** an `api_keys` entry naming a variable that is unset, or holds a value not in the `bmcp_sk_…` format
- **WHEN** the document is applied
- **THEN** the document does not land and the strict-mode rule (MGMT-11) decides whether the gateway starts

#### Scenario: Plaintext value is refused
- **WHEN** an `api_keys` entry carries a key value inline instead of a variable reference or `create_if_missing`
- **THEN** the document fails validation

#### Scenario: Generated key is written to its file
- **GIVEN** an `api_keys` entry `ci` of kind `endpoint` with `create_if_missing` writing to `/secrets/ci.key`, scoped
  to endpoint `demo`
- **WHEN** the gateway starts for the first time
- **THEN** a key `ci` scoped to `demo` is created, `/secrets/ci.key` holds its value with mode `0600`, and no log line
  carries the value
- **AND** on the next start no key is created and the file is unchanged

#### Scenario: An existing file is reused, not overwritten
- **GIVEN** `/secrets/ci.key` holds a well-formed key value and no key named `ci` exists
- **WHEN** the document is applied
- **THEN** key `ci` is created with the value from the file, and the file is unchanged

#### Scenario: Existing key is never overwritten
- **GIVEN** a key named `registrar` already exists, possibly deactivated or with another scope
- **WHEN** a document with an `api_keys` entry `registrar` is applied
- **THEN** the stored key's value, kind, scope and state are unchanged

#### Scenario: Scope names an unknown endpoint
- **WHEN** an endpoint-kind entry is scoped to an endpoint name that neither the document nor the store defines
- **THEN** the document does not land
