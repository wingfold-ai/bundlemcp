# Proposal

## Why

Stored upstream credentials are not bound to the server URL they were obtained for. Changing a server's `url` keeps
every connected user's upstream OAuth tokens, the gateway's client registration and the static header values, and the
next discovery or tool call sends them to whatever the new URL points at. One management write is enough to collect
users' bearer tokens or an API key, although no API ever returns their values. Resolves
[#54](https://github.com/wingfold-ai/bundlemcp/issues/54).

## What Changes

- A write that points a server at a different resource (scheme, host, port or path) revokes what was obtained for the
  old one, in the same transaction as the URL change: every stored upstream token of the server, shared and per user,
  is deleted; a client the gateway obtained itself is deleted; a client an admin stored keeps its id and grant but
  forgets the remembered authorization-server endpoints and step-up scopes. `per_user` callers see the connect tool
  again, and the shared connection has to be made again.
- The revocation writes a `management` audit record with action `upstream.credentials_revoked`, naming who made the
  write and holding no secret.
- A write that moves a server to another origin (scheme, host or port) must re-enter the values of its static headers;
  without them it answers `409` and nothing changes. The secret of an admin-stored upstream OAuth client is cleared, so
  the admin enters it again for the new origin. An import placeholder cannot keep a stored value across such a move.
- **BREAKING** for operators who repoint a server at a new host: the write now needs the static header values, and users
  reconnect their upstream accounts.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `upstreams`: adds UPS-41 (credentials are revoked when a server's URL names another resource) and UPS-42 (secrets are
  re-entered when a server moves to another origin).

## Impact

- `application/management`: the server write revokes credentials and checks the static headers; the import refuses a
  placeholder across an origin change and passes the importing principal on.
- `domain`: a value object for a URL change, and the client record learns to forget the remembered server.
- `api`: the server write and the import pass the calling principal, for the audit record.
- No schema migration, no DTO or route change.
- Docs: `docs/manage/servers.md` gets a "Changing a server's URL" section.
