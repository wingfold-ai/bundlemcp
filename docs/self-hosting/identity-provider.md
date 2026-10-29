# Identity provider

Humans authenticate to bundlemcp **only** through an external OIDC provider. There is no local password store, no signup
page and no password reset, by design. The same login serves two purposes:

- signing in to the admin UI and the management API;
- authorising an MCP client such as claude.ai, where the gateway's OAuth authorization flow redirects to the provider
  before showing consent.

A user record is created on first login from the provider's `(issuer, sub)` pair, with email and display name taken from
the claims.

This page covers **configuring the provider**. For how the provider's login combines with the gateway's own OAuth server
and API keys — the full picture — see [Authentication](/guide/authentication).

## Configuring a provider

Register a **confidential** OpenID Connect client with your provider:

| Setting | Value |
|---|---|
| Flow | Authorization code |
| PKCE | `S256` (may be enforced) |
| Redirect URI | `<BUNDLEMCP_PUBLIC_URL>/login/callback` |
| Scopes | `openid`, `email`, `profile` |

Then point the gateway at it:

```
BUNDLEMCP_OIDC_DISCOVERY_URL=https://idp.example.com/.well-known/openid-configuration
BUNDLEMCP_OIDC_CLIENT_ID=bundlemcp-gateway
BUNDLEMCP_OIDC_CLIENT_SECRET=<secret>
BUNDLEMCP_ADMIN_EMAILS=["ops@example.com"]
```

Every login carries a PKCE `S256` challenge, so a client that enforces PKCE (in Keycloak, *Proof Key for Code Exchange
Code Challenge Method* set to `S256`) works without further configuration. A provider that does not enforce PKCE ignores
the challenge. Only a provider whose discovery document lists `code_challenge_methods_supported` without `S256` is sent
no challenge, and the gateway logs `oidc.pkce_unsupported` at startup.

The discovery URL and every endpoint it names go through the gateway's egress policy. A provider on the gateway's own
loopback address needs an entry in `BUNDLEMCP_EGRESS_ALLOW_CIDRS`; a provider on a private network or on the public
internet works out of the box.

The gateway starts without waiting for the provider, and `/readyz` does not depend on it. While the discovery document
cannot be fetched, `/login` answers `503` with `Retry-After` and the log shows `oidc.discovery_failed`. The gateway
keeps retrying in the background, backing off up to once a minute, so a provider or realm that comes up later is picked
up without a restart (`oidc.discovered`). The document is refreshed hourly; signing keys are fetched on every login.

## Who is an admin

A user is an admin when their email appears in `BUNDLEMCP_ADMIN_EMAILS` and the provider marks it verified, or when
their ID token's admin claim carries the admin value: by default a `groups` claim containing `bundlemcp-admin`. Set
`BUNDLEMCP_ADMIN_CLAIM` to another claim name, or a dotted path into nested claims, and `BUNDLEMCP_ADMIN_CLAIM_VALUE` to
the group or role your provider issues; for Keycloak realm roles that is `BUNDLEMCP_ADMIN_CLAIM=realm_access.roles`. The
claim may be a single value or a list. Both are re-evaluated **on every login**, so removing an address or a group
demotes that person at their next login and adding one promotes them the same way.

A listed email counts only when the ID token's `email_verified` claim is true (the boolean, or the string `"true"`).
Otherwise anyone could register the address at a provider that allows self-signup or unverified email changes and
become an admin. A login whose email is listed but unverified is logged as `user.admin_email_unverified`, without the
address, and the person signs in as a user. If your provider does not send `email_verified`, grant admin through the
admin claim instead.

Everyone else can still log in, as a **user**: they see the catalogue of bundles and endpoints, authorise MCP clients
for those endpoints, and connect their own accounts on per-user upstream servers. They see no management pages, and the
management API answers 403 to their session outside the `/api/v1/me/…` routes (401 is for a caller with no valid
session or key)
([status codes](/integrate/management-api#authentication)). See
[Administrators and users](/guide/authentication#administrators-and-users).

## Sessions

A successful login sets a cookie carrying an opaque random session id: `httpOnly`, host-only (no `Domain`),
`SameSite=Lax`, and `Secure` exactly when the public URL is https. The session record lives in Valkey, so any replica
can serve it. A session lasts `BUNDLEMCP_ADMIN_SESSION_LIFETIME` seconds (12 hours by default), which is also the
cookie's max age; then the user signs in at the provider again, which is when the admin list, the admin claim and the
provider's own state are re-checked.

`POST /logout` ends the bundlemcp session. Single logout from the provider is not required.

## Deactivating a user

An admin can deactivate a user from **Users** or with `POST /api/v1/users/{id}:deactivate`. That immediately revokes
their admin sessions, every OAuth token issued to their connectors, their consents, and their upstream OAuth tokens, and
signing in at the provider again does not undo it: the gateway refuses a deactivated user until an admin reactivates
them (`POST /api/v1/users/{id}:activate`). A user removed at the provider loses access at the latest when their session
and token lifetimes expire, and immediately if you deactivate them here.

## The development provider

The compose stack ships Keycloak with a pre-imported realm named `bundlemcp`:

| | |
|---|---|
| Console | <http://localhost:8080>, `admin` / `admin` |
| Client | `bundlemcp-gateway`, secret `dev-gateway-secret`, PKCE `S256` enforced |
| Redirect URI | `http://localhost:8000/login/callback` |
| User | `admin` / `admin`, email `admin@example.com` (listed as admin in the compose file) |

The gateway reaches Keycloak at `http://keycloak:8080` over the compose
network, but the compose file pins `KC_HOSTNAME: http://localhost:8080` so the
URLs Keycloak advertises to your *browser* use a name the host can resolve.
Nothing needs adding to `/etc/hosts`. If a login ever does send you to
`http://keycloak:8080`, that pin is missing — see
[Troubleshooting](/self-hosting/troubleshooting).

Add users in the Keycloak console to try the non-admin experience.

Replace it before exposing the gateway to anyone: the realm has `sslRequired: none` and a well-known password.

## Provider notes

- **Keycloak**: create a client with *Client authentication* on and *Standard flow* enabled. The discovery URL is
  `https://<host>/realms/<realm>/.well-known/openid-configuration`.
- **Google, Microsoft Entra, Okta, Auth0**: any of them works with the standard discovery URL. Make sure the `email`
  and `email_verified` claims are released; without them the user is created but can never match
  `BUNDLEMCP_ADMIN_EMAILS`.
- **Microsoft Entra ID** does not send `email_verified`, so `BUNDLEMCP_ADMIN_EMAILS` grants nobody admin there. Define
  an app role (for example `bundlemcp-admin`) on the app registration, assign it to the administrators, and set
  `BUNDLEMCP_ADMIN_CLAIM=roles`.
- **One issuer per deployment**: multi-provider federation is out of scope. If you need it, federate at the provider.
