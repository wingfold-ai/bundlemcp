# Design

## Context

A server write goes through `ServerService.upsert`, both from `PUT /api/v1/upstreams/{name}` and from a configuration
import or bootstrap document. It assigns the new URL and leaves the server's upstream tokens and upstream client alone,
and the credential resolver attaches whatever is stored to requests sent to the current URL. Tokens are requested for
the canonical server URL as RFC 8707 resource (UPS-36), so they belong to that resource. Static header values are
write-only (UPS-3), and an empty map on update keeps the stored values. The audit log already holds `management`
records (OPS-18).

## Goals / Non-Goals

**Goals:**

- No stored credential is sent to a resource it was not obtained or entered for.
- Revocation commits or rolls back together with the URL change.

**Non-Goals:**

- A warning in the admin UI before saving ("N accounts will be disconnected"). The write still says what happened in
  the audit log; a confirmation step can follow.
- Delegated tokens (`delegated_token` mode): the gateway mints them per call for the server, they are short-lived and
  never stored for reuse.
- Rebinding by the protected resource document's parent `resource`: a token issued for a parent might still be valid at
  the new path, but revoking on any path change is the safe side and simpler to reason about.

## Decisions

**Two thresholds: resource for tokens, origin for secrets.** Tokens are bound to the resource they were requested for,
so any change of the canonical resource (scheme, host, port, path) revokes them. Static header values and an admin's
client secret were entered for a host, so they need re-entry only when the origin changes; a new path on the same host
keeps them. Alternative: re-entry on any URL change. Rejected because moving `/mcp` to `/v2/mcp` on the same host is a
routine edit and exposes nothing new.

**Refuse, don't drop, static headers.** On an origin move without header values the write answers `409`. Silently
dropping the stored values would leave a server that fails at the next call with no explanation; refusing tells the
admin what to do and keeps the old state intact.

**Admin client: keep id and grant, forget the server, clear the secret on an origin move.** The id was entered
deliberately, so it stays (the issue's ask). The remembered endpoints and step-up scopes describe the old authorization
server and are forgotten, so the next connect discovers the new one. Keeping the secret would hand it to whatever token
endpoint the new resource names — with the client-credentials grant that is full access — so it is cleared on an origin
move and the admin stores it again.

**Where the pieces live.**

- `domain/servers/url_change.py`: a frozen `UrlChange` value object with `moves_resource` and `moves_origin`, built on
  the existing `canonical_resource`.
- `domain/upstream_oauth/upstream_client_metadata.py`: `UpstreamClientMetadata.forgetting_server()` returns the record
  without endpoint keys and step-up scopes, keeping how the client was obtained, its grant and unknown keys.
- `application/management/upstream_credential_revocation.py`: `UpstreamCredentialRevocation` takes the unit of work,
  deletes tokens, deletes or trims the client, and adds the audit record. It stages changes only; the server write's
  commit carries them.
- `ServerService.upsert(body, *, actor=None)` checks the static headers before reconfiguring and calls the revocation
  after the other checks pass and before `_save`, so a refused write revokes nothing.
- `ConfigImportService.run(..., actor=None)` passes the principal down; its placeholder resolution refuses a static
  header placeholder when the origin moves. Bootstrap passes none, and its record names no actor.
- `api`: `ServerController.upsert_server` and `ConfigTransferController.import_config` take the `PrincipalProvider`.

## Risks / Trade-offs

- [An operator repoints a server and is surprised that users must reconnect] → The docs page says so next to the URL
  field, and the audit record shows when and by whom.
- [A concurrent refresh writes a token for the old resource after the delete] → Refresh replaces ciphertext by row id
  and expected value; a deleted row makes it a no-op, so no new token appears.
- [An import with a placeholder now fails across an origin move] → Intended; the error names the header and UPS-42.
