# Requirements

What bundlemcp needs from you before it will run, split by whether you are
trying it out or running it for other people.

## Trying it locally

| | |
|---|---|
| Docker Engine | 24 or newer, with the compose plugin |
| Free ports | 8000 (gateway), 3000 (admin UI), 8080 (dev identity provider) |
| Memory | ~4 GB free. Postgres, Valkey, Keycloak (a JVM), the gateway, the admin UI and a demo MCP server |
| Disk | ~5 GB, mostly the two images built from source |
| Time | A few minutes for the first build; `--wait` can time out before it finishes |

Nothing else. The compose stack brings its own Postgres, Valkey and identity
provider. Go to the [Quickstart](/guide/quickstart).

## Running it for other people

| | |
|---|---|
| Postgres | 17 is what the reference stack and CI run. Holds **all** durable state, so back it up |
| Valkey or Redis | Any RESP-compatible server; Valkey 8 is what the reference stack runs. **One shared instance**, not one per replica |
| An OIDC identity provider | Mandatory, and yours. See below |
| A TLS-terminating reverse proxy | Yours. The gateway speaks plain HTTP on one port |
| A container registry | Only if you build your own images; otherwise pull the published ones, see [Deploy](/self-hosting/deploy#get-the-images) |
| Python | Only if you run the gateway outside a container: 3.13 or newer; the image ships 3.14 |
| Node.js | Only if you build or run the admin UI outside a container: 24 or newer (`npm ci` refuses older); the image ships 26 |

### The identity provider is not optional

There is **no local password store, no signup and no password reset**, by
design. Every human login goes through an external OIDC provider, and
administrator status is decided by matching the provider's `email` claim
against `BUNDLEMCP_ADMIN_EMAILS`. Two consequences worth knowing before you
commit:

- If your provider does not release the `email` claim, users can sign in but
  can never become administrators.
- One issuer per deployment. Multi-provider federation is out of scope —
  federate at the provider instead.

Any compliant issuer works; [Identity provider](/self-hosting/identity-provider)
has per-provider notes for Keycloak, Google, Entra, Okta and Auth0. The
Keycloak in the compose file is for development and ships with
`sslRequired: none` and a well-known password.

### What you own that the gateway does not do

- **TLS.** Terminate it at your proxy.
- **Metrics.** There is no Prometheus `/metrics` route. Alert on the structured
  logs instead — [Operations](/self-hosting/operations) names the events.
- **Backups.** Postgres only; Valkey is deliberately disposable.

## Not multi-tenant

One instance is one shared workspace. Every administrator sees and can change
every server, bundle and endpoint. If you need isolated tenants, run separate
instances with separate databases — see
[What it is not](/guide/what-is-bundlemcp).

## Next steps

- [Quickstart](/guide/quickstart) — the local stack, ten minutes.
- [Production deployment](/self-hosting/deploy) — proxy, secrets, scaling, backups.
- [Configuration](/self-hosting/configuration) — every setting and its default.
