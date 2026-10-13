## MODIFIED Requirements

### Requirement: EP-8 Rename requires force
Renaming an endpoint changes its public URL and breaks every connected client. Renames MUST be rejected unless the
request carries an explicit `force` flag (mirror of [UPS-5](../../../../specs/upstreams/spec.md)); the
rejection message spells out the consequence. The UI offers the rename only in its danger zone and spells out the
consequence **before** the attempt: it shows the current and the resulting public URL, states that every connected
client stops working until it is reconfigured, and enables the rename only once the admin has acknowledged that
consequence, which sends `force`.

#### Scenario: Rename without force is refused
- **WHEN** an admin calls `POST /api/v1/endpoints/main:rename?new_name=other` without `force=true`
- **THEN** the API answers `409 Conflict` explaining that the public URL changes and connected clients break
- **AND** the endpoint keeps its name

#### Scenario: Rename with force succeeds
- **WHEN** an admin repeats the rename with `force=true`
- **THEN** the endpoint is served at `/other/mcp` and `/main/mcp` answers 404

#### Scenario: Name change through PUT is refused
- **WHEN** an admin sends `PUT /api/v1/endpoints/main` with a body whose `name` is `other`
- **THEN** the API rejects the request and points at the rename operation

#### Scenario: The UI states the consequence before the attempt
- **WHEN** an admin types a new name into the rename control of endpoint `main`
- **THEN** the UI shows the current URL `/main/mcp`, the resulting URL, and a warning that connected clients break,
  and the rename button stays disabled until the admin acknowledges the warning
