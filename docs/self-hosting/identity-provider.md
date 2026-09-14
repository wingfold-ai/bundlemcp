# Identity provider

Humans authenticate to bundlemcp **only** through an external OIDC provider.
There is no local password store, no signup page and no password reset, by
design. The same login serves two purposes:

- signing in to the admin UI and the management API;
- authorising an MCP client such as claude.ai, where the gateway's OAuth
  authorization flow redirects to the provider before showing consent.

A user record is created on first login from the provider's `(issuer, sub)`
pair, with email and display name taken from the claims.

## Configuring a provider

Register a **confidential** OpenID Connect client with your provider:

| Setting | Value |
|---|---|
| Flow | Authorization code |
| Redirect URI | `<BUNDLEMCP_PUBLIC_URL>/login/callback` |
| Scopes | `openid`, `email`, `profile` |

Then point the gateway at it:

```
BUNDLEMCP_OIDC_DISCOVERY_URL=https://idp.example.com/.well-known/openid-configuration
BUNDLEMCP_OIDC_CLIENT_ID=bundlemcp-gateway
BUNDLEMCP_OIDC_CLIENT_SECRET=<secret>
BUNDLEMCP_ADMIN_EMAILS=["ops@example.com"]
```

The discovery URL and every endpoint it names go through the gateway's
egress policy. A provider on the gateway's own loopback address needs an
entry in `BUNDLEMCP_EGRESS_ALLOW_CIDRS`; a provider on a private network or
on the public internet works out of the box.

## Who is an admin

Users whose email appears in `BUNDLEMCP_ADMIN_EMAILS` get admin rights. The
list is re-evaluated **on every login**, so removing an address demotes that
person at their next login and adding one promotes them the same way.

Everyone else can still log in, as a **user**: they see the catalogue of
bundles and endpoints, authorise MCP clients for those endpoints, and connect
their own accounts on per-user upstream servers. They see no management
pages and the management API answers 403. See
[Roles and identity](/guide/roles-and-identity).

## Sessions

A successful login sets a signed, `httpOnly` cookie whose `Domain` and
`Secure` attributes derive from the public URL. The session record lives in
Valkey, so any replica can serve it. Sessions have a maximum age that forces a
periodic re-login, which is when the admin list and the provider's own state
are re-checked.

`POST /logout` ends the bundlemcp session. Single logout from the provider is
not required.

## Deactivating a user

An admin can deactivate a user from **Users** or with
`POST /api/v1/users/{id}:deactivate`. That immediately revokes their admin
sessions, every OAuth token issued to their connectors, their consents, and
their upstream OAuth tokens. A user removed at the provider loses access at
the latest when their session and token lifetimes expire, and immediately if
you deactivate them here.

## The development provider

The compose stack ships Keycloak with a pre-imported realm named `bundlemcp`:

| | |
|---|---|
| Console | <http://localhost:8080>, `admin` / `admin` |
| Client | `bundlemcp-gateway`, secret `dev-gateway-secret`, redirect URI `http://localhost:8000/login/callback` |
| User | `admin` / `admin`, email `admin@example.com` (listed as admin in the compose file) |

The gateway reaches Keycloak at `http://keycloak:8080` inside the compose
network and sends your browser to the same hostname, which is why `keycloak`
must resolve to `127.0.0.1` on the host. Add users in the Keycloak console
to try the non-admin experience.

Replace it before exposing the gateway to anyone: the realm has
`sslRequired: none` and a well-known password.

## Provider notes

- **Keycloak**: create a client with *Client authentication* on and
  *Standard flow* enabled. The discovery URL is
  `https://<host>/realms/<realm>/.well-known/openid-configuration`.
- **Google, Microsoft Entra, Okta, Auth0**: any of them works with the
  standard discovery URL. Make sure the `email` claim is released; without it
  the user is created but can never match `BUNDLEMCP_ADMIN_EMAILS`.
- **One issuer per deployment**: multi-provider federation is out of scope.
  If you need it, federate at the provider.
