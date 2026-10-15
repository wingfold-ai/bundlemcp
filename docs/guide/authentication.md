# Authentication

Every tool call through bundlemcp crosses two boundaries. The MCP client has to prove to the gateway who is calling, and
the gateway has to authenticate to the upstream server that runs the tool, often telling it who the caller is. This page
explains both, and who is allowed to do what once they are signed in.

If you read only one thing: a **person** is authenticated by your **identity provider**. An **MCP client** such as
claude.ai gets access to an endpoint from the **gateway's own OAuth server**. A **script** authenticates with an
**API key**. All three end up as one **caller identity**, and that identity is what the rest of the gateway works with.

## Words used on this page

You can follow this page without knowing OAuth in detail. These are the terms it relies on:

| Term | What it means here |
|---|---|
| **Identity provider** | The system where your people have accounts and passwords: Keycloak, Microsoft Entra, Google, Okta, Authentik. bundlemcp never stores passwords; it sends people there to sign in. |
| **OIDC** (OpenID Connect) | The standard the gateway uses to ask the identity provider "who is this person?". The answer is an *ID token* naming the person. |
| **OAuth** | The standard for granting an application limited access on someone's behalf without giving it their password. claude.ai uses it to get access to an endpoint. |
| **Access token** / **bearer token** | The string an MCP client sends with every request, in the header `Authorization: Bearer <token>`. Whoever *bears* it is let in, so it is short-lived and kept secret. |
| **API key** | A long-lived secret for software that cannot open a browser, such as a script. It is sent the same way as a bearer token. |
| **Upstream server** | An MCP server registered with the gateway, which actually runs the tools. The gateway sits between it and the client. |
| **Endpoint** | The URL a client connects to, `<public url>/<endpoint>/mcp`. Each endpoint decides which ways of signing in it accepts. |

## Administrators and users

Everyone who reaches bundlemcp signs in at the same identity provider. What they can do afterwards depends on one thing:
whether their email is listed in `BUNDLEMCP_ADMIN_EMAILS`, re-checked at every login.

| | Administrator | User |
|---|---|---|
| Register upstream servers, store their credentials | ✔ | ✖ |
| Compose bundles, curate tools | ✔ | ✖ |
| Create endpoints, choose profiles, auth modes, rate limits | ✔ | ✖ |
| Create API keys (service and endpoint keys) | ✔ | ✖ |
| Manage users, consents, runtime settings | ✔ | ✖ |
| See the catalogue of bundles and their endpoints | ✔ | ✔ |
| Connect an MCP client to an endpoint | ✔ | ✔ |
| Connect their own account on a per-user upstream server | ✔ | ✔ |

An **administrator** builds the platform: which upstream servers exist, how they are composed into bundles, and under
which rules they are exposed. The admin UI and the management API are theirs.

A **user** consumes it. After signing in they see one page, the **catalogue**: every bundle that has an endpoint
accepting OAuth, with the URL to paste into an MCP client and the steps for that client. They do not create endpoints,
bundles or API keys, and they have no access to the management API.

The split is deliberate. Endpoints are public URLs with their own security rules, upstream servers carry credentials and
reach into your network, and API keys are long-lived secrets. Deciding those once, as an administrator, keeps the
gateway a single shared workspace. Anything finer, such as which person may use which bundle, belongs to the identity
provider (who may log in at all) or to an application layer using the [metering hook](/integrate/metering-hook).

## Two directions, two identities

<LikeC4Diagram view="authDirections" />

A tool call carries two identities, one per boundary:

- The **caller identity** answers "who is calling the gateway?". It is resolved once per request, and everything inside
  the gateway keys on it: rate limits, the audit record, the metering hook, and what upstream servers are told.
- The **upstream identity** answers "as whom does the gateway talk to this upstream server?". It is set per upstream
  server by an administrator, and it never changes who the call is attributed to.

The next two sections take each in turn.

## Caller identity: who is calling the gateway

There are four ways in. An endpoint picks which it accepts with its `auth_modes`: `oauth`, `api_key`, or `none`.

| The client presents | Resolved caller identity | Who this is for |
|---|---|---|
| An OAuth access token issued by the gateway | the person's user id (`sub`) | People and their MCP clients: claude.ai, ChatGPT, Claude Code |
| An endpoint or service API key | `api_key:<key id>` | Scripts, agents, automation, upstream servers verifying tokens |
| Nothing, on an endpoint with auth mode `none` | anonymous | Deliberately open endpoints |

An endpoint that accepts OAuth appears in the catalogue; one that accepts only API keys is for automation and does not.

### Signing in to the admin UI or the management API

People sign in with **OIDC only**. There are no passwords, no signup and no password reset in bundlemcp: that whole
class of code is deliberately absent, because your identity provider already does it better.

<LikeC4Diagram view="authLogin" />

What to take from this:

- The **person** is authenticated by the identity provider, not by bundlemcp. The gateway trusts the provider's ID token
  and creates a local user record the first time it sees that person.
- A **session** is a cookie carrying an opaque random id in the browser plus a record in Valkey, so any gateway replica
  can serve it. It lasts `BUNDLEMCP_ADMIN_SESSION_LIFETIME` (12 hours by default), which forces a periodic re-login.
- **Administrator or user** is decided at every login from `BUNDLEMCP_ADMIN_EMAILS` and the admin claim
  (`BUNDLEMCP_ADMIN_CLAIM`, by default a `groups` claim containing `bundlemcp-admin`). A user can still log in, but only
  sees the catalogue: the management API answers 403 to them on every route except `/api/v1/me/…`, and 401 only to a
  caller with no valid session or key. See [status codes](/integrate/management-api#authentication).
- A **service API key** can also call the management API, which is how automation configures the gateway without a
  browser. That is the only place API keys and sessions overlap; the cookie wins when both are present.

Details: [Identity provider](/self-hosting/identity-provider).

### Connecting an MCP client such as claude.ai or ChatGPT

This is where OAuth comes in, and where it helps to know that the gateway plays **three OAuth roles** at once:

| Role | What it does | Talks to | Example |
|---|---|---|---|
| **Authorization server** | Issues access tokens | MCP clients | claude.ai gets a token for the `assistant` endpoint |
| **Resource server** | Accepts and checks its own tokens | MCP clients | A `tools/call` presents that token |
| **OAuth client** | Obtains tokens from someone else | Upstream servers | The gateway signs in to GitHub on a user's behalf |

Connecting a client involves **two conversations**, one with the identity provider and one with the gateway's OAuth
server:

<LikeC4Diagram view="authConnect" />

The identity provider answers **"who is this person?"**. The gateway's OAuth server answers **"may this client act for
that person on this endpoint?"**, and records the answer as an access token. Both happen inside one chain of browser
redirects, so it feels like one login, but they are separate systems. The MCP client never sees the person's password
and has no identity of its own: the token stands for the person, in whichever client they use.

Step by step:

1. **Discovery.** claude.ai fetches the endpoint's protected-resource metadata
   (`/.well-known/oauth-protected-resource/<endpoint>/mcp`) and the gateway's authorization-server metadata
   (`/.well-known/oauth-authorization-server`). This tells it where to send the person to sign in.
2. **Registration.** claude.ai registers itself as an OAuth client (RFC 7591 dynamic client registration), or presents
   a `client_id` that is an `https://` URL whose metadata document the gateway fetches. ChatGPT and Claude still
   commonly use registration.
3. **Authorize.** `GET /oauth/authorize` carries the client id, redirect URI, a PKCE challenge (`S256`, required) and a
   `resource` naming the target endpoint. If the browser has no gateway session yet, the gateway first sends the person
   to the identity provider and returns here afterwards.
4. **Consent.** The person approves a screen naming the client, the endpoint and the scope. Consent is remembered per
   person, client and endpoint, and skipped until revoked.
5. **Code → tokens.** The gateway redirects back with a single-use authorization code (10-minute life). The client
   exchanges it at `POST /oauth/token`, optionally naming the endpoint again as `resource` (RFC 8707); a `resource`
   that is not the endpoint the code was issued for is refused with `invalid_target`, and without one the tokens are
   bound to that endpoint. The exchange yields:
   - an **access token** (`bmcp_at_…`, opaque, one hour by default), and
   - a **refresh token** (`bmcp_rt_…`, seven days, **rotated on every use**). A refresh token presented twice is treated
     as stolen and the whole token family is revoked.
6. **Calls.** The client sends `Authorization: Bearer bmcp_at_…` to `/{endpoint}/mcp`. The gateway looks the token up
   directly in its database and checks that it is not revoked or expired, that it was issued **for this endpoint**, and
   that the person is still active.

Two properties are worth stating plainly:

- **Tokens are bound to one endpoint.** A token issued for `assistant` is refused at `assistant-gpt` (RFC 8707
  `resource` → audience) with `error="invalid_token"` in the `WWW-Authenticate` challenge, and a client simply
  re-authorizes at the other endpoint. A refresh can name `resource` too; it must be the same endpoint.
- **Authorization responses carry `iss`** (RFC 9207), so a client can detect a mix-up between two authorization servers.

Details: [Connect claude.ai](/connect/claude).

### A script or agent with an API key

Anything that cannot run a browser uses an **API key** (`bmcp_sk_…`), sent as `Authorization: Bearer` or `X-API-Key`
(never a query parameter). Keys come in two kinds:

| Kind | May call |
|---|---|
| `endpoint` | MCP endpoints that accept `api_key`, restricted to its scoped endpoints |
| `service` | The same, **plus** the management API and the introspection route |

A key is a *machine* identity. Its caller identity is `api_key:<id>`, which is what audit, metering and `X-MCP-User` all
report. Keys are hashed at rest and shown once at creation.

Details: [API keys](/manage/api-keys).

### An open endpoint

An endpoint whose `auth_modes` is `["none"]` admits anyone. The caller identity is anonymous: audit and metering see no
user, `X-MCP-User` is omitted upstream, and a `per_user` upstream server can never be reached through it (the gateway
rejects that combination).

### How the gateway chooses

Within an endpoint, the gateway tries the credentials it accepts, strongest first:

```
OAuth bearer  →  API key  →  anonymous (only if the endpoint accepts none)
```

So if a request carries both a bearer and a key, the bearer wins. Repeated bad credentials from one IP address are
throttled, and then locked out, before any database lookup.

## Upstream identity: how the gateway reaches an upstream server

Once the caller identity is resolved, the gateway calls the upstream server. Each upstream server's settings answer two
questions:

- **How does the gateway get in?** Without a credential, with one shared key, with one shared OAuth account, or with
  each person's own account at the upstream service.
- **What does the upstream server learn about the caller?** Nothing, a header naming the caller, or a short-lived token
  it can verify with the gateway.

Every option, with the situation it is for, is on [Upstream server settings](/guide/upstream-server-settings). What a
server you write yourself receives, and how it checks it, is on
[Identity for upstream servers](/integrate/upstream-identity). For authentication, three points matter:

- **The upstream identity never changes who the call is attributed to.** Rate limits, the audit record and the
  metering hook always use the caller identity, even when the gateway reaches the upstream through a shared account.
- **With each person's own account, people never share one.** A person connects their account once: until then their
  tool list holds a `<server>__connect_account` tool that returns a sign-in link. Their upstream token is stored
  encrypted, refreshed automatically, and used by every MCP client they connect. Because the gateway has to know which
  person is calling, such a server cannot sit behind an endpoint without authentication, and API-key callers cannot
  use it.
- **To prove the caller to an upstream server, use a delegated token.** The gateway then sends a token issued for this
  caller and valid only at this server, which the server checks with the gateway. The simpler `X-MCP-User` header
  names the caller too, but anyone who can reach the server directly could send it, so trust it only on a network
  where the upstream server is reachable solely through the gateway.

## End to end

Three callers use the same bundle, `assistant`: two people who are not administrators, and a nightly script.

1. **The first person** signs in and opens the catalogue. They see the `assistant` bundle with its `assistant`
   endpoint shaped for claude.ai, and add its URL in claude.ai. claude.ai registers itself, the person signs in at the
   identity provider and approves the consent screen. claude.ai now holds a token that means "this person, on
   `assistant`".
2. The bundle contains a GitHub upstream server where each person uses their own account. The first person has not
   connected one yet, so their tool list shows `github__connect_account` instead of the GitHub tools. Calling it gives
   them a sign-in link; they authorise at GitHub, and the GitHub tools appear. A call to `github__list_issues` now
   carries **their** GitHub token, and the audit record names them.
3. **The second person** does the same on the same endpoint and ends up with their own GitHub token. Neither can act
   as the other.
4. **The script** uses an `endpoint` API key on a second endpoint of the same bundle. It is identified as
   `api_key:<id>`, cannot use the GitHub server, because that one needs each caller's own account, and would use a
   shared upstream account if one were configured.

## Secrets at a glance

| Secret | Format | Who holds it | Lifetime |
|---|---|---|---|
| Access token | `bmcp_at_…` | MCP client | 1 hour (configurable) |
| Refresh token | `bmcp_rt_…` | MCP client | 7 days, rotated each use |
| API key | `bmcp_sk_…` | scripts, services | no expiry; revoke manually |
| Upstream OAuth token | provider-specific | the gateway (encrypted) | refreshed automatically |
| Delegated token | `bmcp_dt_…` | the one upstream server it was issued for | 5 minutes |
| Admin session | signed cookie | the browser | bounded by max age |

Tokens and keys are stored hashed, upstream tokens encrypted, and nothing secret is ever logged or returned by an API.

## Common confusions

**"Why do I sign in twice when connecting claude.ai?"** You do not, in practice: the gateway only sends you to the
identity provider when you have no session yet. The two systems are distinct, but the browser flow is one trip.

**"Why can't my endpoint API key call `/api/v1`?"** Only `service` keys reach the management API. Endpoint keys are for
tools.

**"Where is the user's password?"** Nowhere in bundlemcp. It lives at your identity provider; the gateway only ever sees
an ID token.

**"Does the MCP client have its own identity?"** No. The token stands for the person; the client is just the software
presenting it. Every client a person uses resolves to the same user and the same upstream accounts.

**"Is `X-MCP-User` proof of anything?"** It is trusted only on a network where the upstream server is reachable solely
through the gateway. For proof, use a [delegated token](/guide/upstream-server-settings#auth_mode).

**"A token works on one endpoint but not another — is it broken?"** No, that is endpoint binding. Re-authorize on the
second endpoint.
