## MODIFIED Requirements

### Requirement: UPS-27 Interactive connect flow
The gateway SHALL offer an interactive connect flow: from the server detail page (admin, shared mode) — and, for
`per_user` mode, from a minimal hosted "connect your account" page a user is directed to when calling a tool that lacks
a token for them. The state parameter is server-generated, single-use, stored server-side (metamcp's CSRF fix carried
over). PKCE is used when supported. Because a user with no token may have no tool to call yet, `tools/list` also
offers a signed-in caller who has no valid token for a `per_user` member server a gateway-provided tool
`<server>__connect_account` ([ADR-0037](../../../docs/adr/0037-connect-account-tool.md)). Calling it returns the
connect URL as a normal result; it reaches no upstream and is not metered. It is not listed once the caller holds a
valid token, stays callable to connect a different account, and never shadows an upstream tool presenting the same
name. API-key and anonymous callers are not offered it: a per-user connection is keyed by a user.

The callback is completed only by the browser session that started the flow. For a per-user connection, the signed-in
session user must be the user the flow was started for. For the shared connection, the session user must be an admin.
A callback without a signed-in session, or with a session that does not meet this rule, is refused: its state is
consumed, the authorization code is not redeemed, and no token is stored. The refusal page asks the user to sign in and
start the connect again.

#### Scenario: Unconnected user sees the connect tool
- **WHEN** a signed-in user without a valid token for a `per_user` member server lists tools
- **THEN** the list includes `<server>__connect_account`, and calling it returns the connect URL without reaching the
  upstream or metering

#### Scenario: Connected user does not see it
- **WHEN** the same user lists tools after connecting
- **THEN** `<server>__connect_account` is not listed, but calling it still returns the connect URL

#### Scenario: State is single-use
- **WHEN** a connect callback is replayed with a state that was already consumed
- **THEN** the callback is rejected and no token is stored

#### Scenario: API-key caller is not offered the tool
- **WHEN** an API-key caller lists tools of a bundle with a `per_user` server
- **THEN** no `__connect_account` tool is listed

#### Scenario: Another user cannot finish a per-user connect
- **GIVEN** user A started a per-user connect for server `crm`
- **WHEN** the callback for that state arrives in a browser signed in as user B
- **THEN** the callback is refused, no token is stored for A or for B, and the upstream authorization code is not
  redeemed

#### Scenario: A callback without a session is refused
- **GIVEN** user A started a per-user connect for server `crm`
- **WHEN** the callback for that state arrives in a browser with no gateway session
- **THEN** the callback is refused with a page asking to sign in and connect again, and the state can no longer be used

#### Scenario: A non-admin cannot finish the shared connect
- **GIVEN** an admin started the shared connect for server `crm`
- **WHEN** the callback for that state arrives in a browser signed in as a user who is not an admin
- **THEN** the callback is refused and the shared connection is unchanged

#### Scenario: The initiator finishes the connect
- **GIVEN** user A started a per-user connect for server `crm`
- **WHEN** the callback for that state arrives in A's browser session
- **THEN** the code is redeemed and the token is stored for A
