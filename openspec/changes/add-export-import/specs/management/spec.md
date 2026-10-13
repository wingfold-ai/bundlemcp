## ADDED Requirements

### Requirement: MGMT-17 Versioned export document
`GET /api/v1/export` SHALL return a versioned JSON document (`{"version": 1, "upstreams": [...], "bundles": [...],
"endpoints": [...]}`, keys per [UPS-16](../../../../specs/upstreams/spec.md)) containing all configuration by
natural keys. The document MUST validate against the same schema bootstrap consumes
([MGMT-8](../../../../specs/management/spec.md)), so an export can be used as a bootstrap file unchanged.

#### Scenario: Export lists every configured resource by name
- **GIVEN** upstream `weather`, bundle `b1` with member `weather` and a tool override, and endpoint `b1-api`
- **WHEN** an admin calls `GET /api/v1/export`
- **THEN** the response has `version: 1` and lists `weather` under `upstreams`, `b1` with its member, enable flag and
  tool curation under `bundles`, and `b1-api` under `endpoints`, each identified by name rather than database id

#### Scenario: An export is a valid bootstrap document
- **WHEN** an export is written to a file and named in `BUNDLEMCP_BOOTSTRAP_FILE` of an empty gateway
- **THEN** bootstrap accepts it and creates the same upstreams, bundles and endpoints

### Requirement: MGMT-18 Secrets become named placeholders
Secrets (static header values, upstream OAuth client secrets) MUST be **excluded** by default and exported as named
placeholders (`{"$secret": "<NAME>"}`, the header name or `client_secret`). `?include_secrets=true` exports the values
for full backups, under the controls of [SEC-11](../security/spec.md). On import, a placeholder keeps the value the
target already stores; with nothing stored, that resource is reported as an error.

#### Scenario: Default export withholds header values
- **GIVEN** upstream `weather` with static header `Authorization: Bearer s3cret`
- **WHEN** `GET /api/v1/export` is called
- **THEN** the entry carries `"Authorization": {"$secret": "Authorization"}` and the value appears nowhere in the body

#### Scenario: Placeholder keeps the stored secret on import
- **GIVEN** the target already stores a value for `weather`'s `Authorization` header
- **WHEN** a document with the placeholder for that header is imported
- **THEN** the stored value is unchanged and the upstream is reported `updated` or `skipped`

#### Scenario: Placeholder without a stored value is an error
- **WHEN** a document with a placeholder is imported into a gateway that stores no value for it
- **THEN** that upstream is reported `error` naming the missing secret

### Requirement: MGMT-19 Transactional import by natural key
`POST /api/v1/import` SHALL apply a document transactionally as upserts by natural key, through the same operations
the management API uses, and report a result per resource: `created`, `updated`, `skipped` (unchanged) or `error` with
a message. If any resource errors, nothing is written. `dry_run=true` SHALL validate and report without writing.

#### Scenario: Import reports per-resource results
- **GIVEN** a target that has upstream `weather` identical to the document's and no bundle `b1`
- **WHEN** the document is imported
- **THEN** the response reports `weather` as `skipped` and `b1` as `created`

#### Scenario: Dry run writes nothing
- **WHEN** a document is imported with `dry_run=true`
- **THEN** the response carries the same per-resource results a real import would, and no configuration changes

#### Scenario: One error rolls back the document
- **WHEN** a document whose second endpoint names a bundle that exists neither in the document nor on the target is
  imported
- **THEN** that endpoint is reported `error`, and none of the document's other resources are written

#### Scenario: Unsupported version is refused
- **WHEN** a document with `version: 2` is imported
- **THEN** the request is rejected with `422` naming the supported version, and nothing is written

### Requirement: MGMT-20 Import is additive
Import MUST never delete resources absent from the document; it only creates and updates. A `prune=true` flag MAY be
added later; it is not part of version 1.

#### Scenario: Resources absent from the document survive
- **GIVEN** the target has upstream `legacy` that the document does not list
- **WHEN** the document is imported
- **THEN** `legacy` still exists and is not mentioned as deleted

### Requirement: MGMT-21 Identity and runtime state are not exported
The export MUST NOT contain users, OAuth server state (clients, codes, tokens, consents), API key values, audit
records, or upstream OAuth tokens. These are identity and runtime state, not configuration, and an import never
creates them.

#### Scenario: Export carries configuration only
- **GIVEN** a gateway with users, API keys, issued OAuth tokens, audit records and stored upstream OAuth tokens
- **WHEN** `GET /api/v1/export?include_secrets=true` is called by an admin
- **THEN** the document contains none of them

### Requirement: MGMT-22 Export and import in the admin UI
The admin UI SHALL offer an export button that downloads the document, and an import that first shows the dry-run
report and applies the document only after the admin confirms it.

#### Scenario: Import previews before it applies
- **WHEN** an admin chooses a document file to import in the UI
- **THEN** the UI shows the dry-run report per resource, and nothing is written until the admin confirms

#### Scenario: Export downloads a file
- **WHEN** an admin clicks the export button
- **THEN** the browser downloads the export document as a JSON file
