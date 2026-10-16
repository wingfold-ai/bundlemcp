## ADDED Requirements

### Requirement: SEC-11 Secret-bearing export
An export with `?include_secrets=true` ([MGMT-18](../management/spec.md)) MUST be refused (`403`) unless the caller
holds an admin session; a service API key cannot obtain secret values. Every such export MUST be recorded in the audit
log ([OPS-18](../operations/spec.md)) with the admin's identity and time, and its body MUST carry an explicit warning
field stating that the document contains credentials. The documentation tells operators to treat the file as a
credential.

#### Scenario: Service key cannot export secrets
- **WHEN** `GET /api/v1/export?include_secrets=true` is called with a service-kind API key
- **THEN** the response is `403` and no secret value is returned

#### Scenario: Admin export with secrets is recorded and flagged
- **WHEN** an admin with a session calls `GET /api/v1/export?include_secrets=true`
- **THEN** the body carries the secret values and a `warning` field saying the document contains credentials, and an
  audit entry names the admin and the time of the export

#### Scenario: Default export needs no special rights
- **WHEN** a service-kind API key calls `GET /api/v1/export` without `include_secrets`
- **THEN** the export is returned with placeholders and without a `warning` field
