# Spec Delta

## ADDED Requirements

### Requirement: UPS-41 Credentials stay with the resource they were obtained for
When a write changes a server's `url` so that it names another resource (another scheme, host, port or path; the
letter case of the host and a trailing slash do not count), the gateway MUST, in the same transaction as the change,
delete every stored upstream token of the server, delete a client it obtained itself, and make an admin-stored client
forget its remembered endpoints and step-up scopes. It records a `management` audit record with action
`upstream.credentials_revoked`.

#### Scenario: Connected accounts are disconnected
- **GIVEN** a `per_user` `upstream_oauth` server at `https://seo.example/mcp` with two connected users and a shared
  connection
- **WHEN** its `url` is changed to `https://other.example/mcp`
- **THEN** no upstream token of the server is stored, and a `per_user` caller is offered the connect tool again

#### Scenario: No old token reaches the new URL
- **GIVEN** a server whose users connected their accounts at its old URL
- **WHEN** its `url` is changed and a tool call or discovery then reaches the new URL
- **THEN** that request carries none of the tokens obtained for the old URL

#### Scenario: A client the gateway obtained is dropped
- **GIVEN** a server whose upstream client the gateway registered or identified itself
- **WHEN** its `url` is changed to another resource
- **THEN** the client is deleted, so the next connect discovers the new resource's authorization server

#### Scenario: An admin-stored client is kept without its remembered server
- **GIVEN** a server with an upstream client an admin stored, remembered endpoints and step-up scopes
- **WHEN** its `url` is changed to another resource
- **THEN** the client keeps its client id and grant, and its endpoints and step-up scopes are forgotten

#### Scenario: The revocation is audited
- **WHEN** an admin changes the `url` of a server with stored tokens
- **THEN** one audit record of kind `management` with action `upstream.credentials_revoked` and the admin's user id
  exists, and it holds no token or secret

#### Scenario: Case and a trailing slash change nothing
- **GIVEN** a server at `https://seo.example/mcp` with stored tokens
- **WHEN** its `url` is written as `https://SEO.Example/mcp/`
- **THEN** its tokens and client are kept and no revocation is audited

#### Scenario: A failed write revokes nothing
- **WHEN** a write changing a server's `url` is refused
- **THEN** the server's tokens, client and URL are all as they were

### Requirement: UPS-42 Secrets are entered again when a server moves to another origin
A write that changes a server's origin (scheme, host or port) MUST carry the values of its static headers when any are
stored; otherwise it is refused with `409` and nothing changes. The move clears the secret of an admin-stored upstream
OAuth client. An import placeholder cannot keep a stored static header value across such a move.

#### Scenario: Static headers must be re-entered
- **GIVEN** server `crm` at `https://crm.example/mcp` with static header `Authorization`
- **WHEN** it is upserted with `url` `https://other.example/mcp` and no `static_headers`
- **THEN** the write answers `409`, and the stored URL and headers are unchanged

#### Scenario: Re-entered headers move with the server
- **WHEN** the same write carries `static_headers` with a value for `Authorization`
- **THEN** the server is stored at the new URL with the new header value

#### Scenario: A new path on the same origin keeps the headers
- **WHEN** server `crm` is upserted with `url` `https://crm.example/v2/mcp` and no `static_headers`
- **THEN** the write succeeds and the stored header values are kept

#### Scenario: An admin-stored client secret is cleared
- **GIVEN** a server with an admin-stored upstream OAuth client that has a secret
- **WHEN** its `url` moves to another origin
- **THEN** the client has no secret until an admin stores one again

#### Scenario: An import placeholder does not follow a server to another origin
- **GIVEN** server `crm` with a stored static header `Authorization`
- **WHEN** a document imports `crm` with another origin and `Authorization` as a placeholder
- **THEN** that upstream is reported as an error and nothing of it changes
