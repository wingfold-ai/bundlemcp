## MODIFIED Requirements

### Requirement: SEC-9 Auth-failure rate limiting
Authentication failures MUST be rate-limited per client IP per [EP-20](../endpoints/spec.md): after
the configured number of failures within the window, the IP is locked out until the window lapses. Authentication
failures and lockout events SHALL be counted in the exported metrics
([OPS-9](../operations/spec.md)), without the client IP as a label.

#### Scenario: Credential scan is locked out
- **WHEN** one IP sends more failed authentications than the configured limit within the window
- **THEN** its further requests are refused as locked out until the window lapses

#### Scenario: Lockout is visible in metrics
- **GIVEN** an auth-failure limit of N per window
- **WHEN** one IP sends N + 1 failed authentications in one window and `/metrics` is scraped
- **THEN** the auth-failure counter has increased by N + 1 and the lockout counter by at least one
- **AND** no metric line contains the client IP

### Requirement: SEC-10 Secrets stay secret
Secret values (API keys, tokens, static/forwarded header values, client secrets) MUST NOT appear in logs, metric labels,
audit records, API responses (beyond one-time display at creation), or error messages. Server reads return static
header names only; upstream OAuth status never returns the client secret; stored upstream tokens and client secrets are
ciphertext. A unit-test helper SHALL assert redaction on representative paths: logs, metrics output and error bodies.

#### Scenario: Header values are withheld
- **GIVEN** a server registered with a static `Authorization` header
- **WHEN** an admin reads the server through the management API
- **THEN** the response lists `static_header_names` and no header value

#### Scenario: API key value is shown once
- **WHEN** an API key is created
- **THEN** the creation response carries the key value, and every later read carries only its prefix and metadata

#### Scenario: Upstream OAuth status omits the secret
- **GIVEN** a server with a stored upstream OAuth client secret
- **WHEN** the upstream OAuth status is read
- **THEN** the response does not contain the secret

#### Scenario: Metric labels carry no secret or caller identity
- **GIVEN** tool calls made with an API key, an OAuth bearer and a forwarded identity header
- **WHEN** `/metrics` is scraped
- **THEN** the redaction helper finds none of the key value, the bearer, the header value, the user's `sub` or the API
  key id in the output

#### Scenario: Redaction helper covers logs and error bodies
- **WHEN** a request with a bad API key is rejected and the captured log records and the error body are passed to the
  redaction helper together with the presented key
- **THEN** the helper reports no occurrence of the key value
