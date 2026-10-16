## ADDED Requirements

### Requirement: OPS-18 Management events in the audit log
The audit log SHALL also hold records of management actions that need a durable trace, distinguished by a `kind`:
`tool_call` for the records of OPS-1 and `management` for these. A management record carries an `action` naming what
happened, the acting user or API key, the time and status `success`; it has no endpoint, bundle or tool, and never a
secret value. A secret-bearing export ([SEC-11](../security/spec.md)) writes one with action
`export.secrets_included`. `GET /api/v1/audit-records` filters by `kind`, and the CSV export carries `kind` and
`action`.

#### Scenario: A secret-bearing export is recorded
- **WHEN** an admin exports with `include_secrets=true`
- **THEN** one audit record of kind `management` with action `export.secrets_included`, the admin's user id and the
  time exists, and it holds no secret value

#### Scenario: Tool-call records are unchanged
- **WHEN** a client calls a tool
- **THEN** its audit record has kind `tool_call` and no action, as before

#### Scenario: Filtering by kind
- **GIVEN** tool-call records and one management record
- **WHEN** `GET /api/v1/audit-records?kind=management` is called
- **THEN** only the management record is listed
