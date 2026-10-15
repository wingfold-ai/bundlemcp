# Users and consents

Users are not created in bundlemcp. They appear the first time someone signs in through the identity provider, whether
to reach the admin UI or to authorise a connector such as claude.ai. One human is one user, whichever way they arrived.

## What a user record holds

| Field | Meaning |
|---|---|
| `email`, `display_name` | Claims from the identity provider at the last login. |
| `is_admin` | Whether the email matched `BUNDLEMCP_ADMIN_EMAILS` at the most recent login. |
| `is_active` | Whether the user may authenticate at all. |

The user's id is the `sub` that upstream servers see in `X-MCP-User`, that the metering hook receives, and that the
introspection route reports. It is stable for the lifetime of the gateway's database. The identity provider's issuer and
subject are stable beyond it, across a rebuild or restore, so they are reported too: as `oidc_issuer` / `oidc_sub` to
the metering hook, as `oidc_iss` / `oidc_sub` by introspection, and in `X-MCP-User` when
`BUNDLEMCP_IDENTITY_SUBJECT=oidc`.

`GET /api/v1/users` lists users; the UI page is **Users**.

## Admins and everyone else

Admins configure the gateway. Everyone else is a **user**: after signing in
they see the catalogue, the bundles with endpoints they can connect an MCP
client to, and nothing else. They authorise connectors, connect their own
accounts on per-user servers, and that is the extent of it; the management
API answers 403 to them outside the `/api/v1/me/…` routes
([status codes](/integrate/management-api#authentication)). The division of
responsibilities is spelled out on
[Authentication](/guide/authentication#administrators-and-users).

Admin status is re-evaluated at every login, from the email list and the admin claim (see
[Who is an admin](/self-hosting/identity-provider#who-is-an-admin)). To promote or demote someone, change
`BUNDLEMCP_ADMIN_EMAILS` or their group at the identity provider, and have them log in again.

## Deactivating a user

```bash
curl -s -X POST https://gw.example.com/api/v1/users/$USER_ID:deactivate \
  -H "Authorization: Bearer $SERVICE_KEY"
```

Deactivation is immediate: the user's admin sessions end, every OAuth token issued to their connectors and their
consents are revoked, and their upstream OAuth connections are deleted, so neither their own calls nor discovery of a
per-user upstream can use them any more.

It also sticks. When a deactivated user signs in at the identity provider again, through the admin UI or an MCP
client's OAuth flow, the gateway refuses them with a page saying their account is deactivated, creates no session and
issues no code. Only an administrator brings them back:

```bash
curl -s -X POST https://gw.example.com/api/v1/users/$USER_ID:activate \
  -H "Authorization: Bearer $SERVICE_KEY"
```

or **Reactivate** on the Users page. Nothing revoked at deactivation is restored: the user consents to their clients
and connects their upstream accounts again.

When someone leaves, deactivating them here is enough to keep them out of this gateway. Disable them at the identity
provider as well, so they lose access to everything else that trusts it.

## Consents

When a user authorises an MCP client for an endpoint, the gateway shows a consent screen naming the client and the
endpoint, then remembers the decision per `(user, client, endpoint)`. Later authorisations for the same triple skip the
screen.

`GET /api/v1/users/{id}/consents` lists a user's consents. Revoking one with
`DELETE /api/v1/users/{id}/consents/{consent_id}` also revokes every token issued under it, so the client has to ask
again. The **Users** page exposes the same actions.

Revoke a consent when a user reports a connector they no longer use, or when a client's registration is replaced.
