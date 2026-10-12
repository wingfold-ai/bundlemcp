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
- A **session** is a signed cookie in the browser plus a record in Valkey, so any gateway replica can serve it. It has a
  maximum age that forces a periodic re-login.
- **Administrator or user** is decided at every login from `BUNDLEMCP_ADMIN_EMAILS`. A user can still log in, but only
  sees the catalogue: the management API answers 401 to them on every route except `/api/v1/me/…`. See
  [status codes](/integrate/management-api#authentication) — 401 rather than 403 is deliberate but easy to misread.
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
   exchanges it at `POST /oauth/token` for:
   - an **access token** (`bmcp_at_…`, opaque, one hour by default), and
   - a **refresh token** (`bmcp_rt_…`, seven days, **rotated on every use**). A refresh token presented twice is treated
     as stolen and the whole token family is revoked.
6. **Calls.** The client sends `Authorization: Bearer bmcp_at_…` to `/{endpoint}/mcp`. The gateway looks the token up
   directly in its database and checks that it is not revoked or expired, that it was issued **for this endpoint**, and
   that the person is still active.

Two properties are worth stating plainly:

- **Tokens are bound to one endpoint.** A token issued for `assistant` is refused at `assistant-gpt` (RFC 8707
  `resource` → audience). A client simply re-authorizes at the other endpoint.
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

Once the caller identity is resolved, the gateway calls the upstream server. Two separate questions arise there, and
each upstream server answers them in its own settings:

- **How does the gateway authenticate to the upstream server?** That is its `auth_mode`, and it is independent of who
  called.
- **Does the upstream server learn who the caller is?** That is `send_identity_header` and `forward_headers`.

The settings themselves, with when to use each, are described on [Upstream servers](/manage/servers).

### How the gateway authenticates to the upstream server

| `auth_mode` | Identity toward the upstream | Typical case |
|---|---|---|
| `none` | none | Upstream servers on your own network that trust the gateway |
| `static_headers` | one fixed credential, such as an API key header, for every caller | A hosted server with a service key |
| `upstream_oauth`, `identity_mode: shared` | one OAuth account an administrator connected once | A service account at the upstream |
| `upstream_oauth`, `identity_mode: per_user` | the caller's own account at the upstream | GitHub, Google, a CRM: anything where the upstream must see the person |

With `upstream_oauth` the gateway is itself an **OAuth client** of the upstream, and attaches its own bearer to every
call.

With `per_user`, the first tool call a person makes without a stored account returns a structured MCP error carrying a
connect link. They open it, sign in at the upstream in their browser, and retry. From then on their calls carry their
own upstream token, encrypted at rest and refreshed automatically. Two people using the same endpoint therefore act as
two different upstream accounts, and an administrator's connection is never substituted for a user's. A person's
upstream token is shared by every MCP client they use: one account per person per upstream server.

Because the caller must be a person, a `per_user` upstream server cannot sit behind a `none`-auth endpoint; the gateway
refuses that combination.

Details: [Upstream OAuth](/manage/servers#upstream-oauth).

### Telling the upstream server who is calling

Independently of `auth_mode`, two mechanisms pass the caller identity on. They can be combined.

#### `X-MCP-User`: trusted on the internal network

When an upstream server's `send_identity_header` is on (the default), every call to it carries `X-MCP-User: <sub>`:
the user id for OAuth callers (or their identity provider subject with `BUNDLEMCP_IDENTITY_SUBJECT=oidc`),
`api_key:<id>` for key callers, and nothing for anonymous callers. The gateway **strips any `X-MCP-User` a client
sends**, so the header can only come from the gateway.

This is a plain header, not a signed assertion. Trust it only when the upstream server is reachable *only* through the
gateway, such as on a compose or cluster network. For an upstream server that also faces the internet, use the next
mechanism.

#### Forwarded bearer plus introspection: verifiable

To let an upstream server *verify* the caller, forward the client's own `Authorization` header and have the upstream ask
the gateway whether it is valid:

1. Register the upstream server with `forward_headers: {"authorization": "authorization"}`.
2. Give the upstream server a `service` API key.
3. The upstream server calls the introspection route (never anonymous):

```bash
curl -s https://gw.example.com/oauth/introspect \
  -u "bundlemcp:bmcp_sk_<service key>" \
  -d "token=<the forwarded bearer>"
```

```json
{ "active": true, "sub": "…", "client_id": "…", "exp": 1757340000, "scope": "…", "aud": "…" }
```

A forwarded **API key** introspects as active with `sub` `api_key:<id>` too, so an upstream server written for
introspection serves key callers without a second code path. The upstream connection is keyed by the forwarded values,
never just by `sub`, so one user's credential can never serve another's request.

Details: [Identity for upstream servers](/integrate/upstream-identity).

## End to end

Alice, a user who is not an administrator, Bob, and a nightly script, all on the same bundle:

1. **Alice** signs in and opens the catalogue. She sees the `assistant` bundle with its `assistant` endpoint shaped for
   claude.ai, and adds its URL in claude.ai. claude.ai registers itself, Alice signs in at the identity provider,
   approves the consent screen, and claude.ai now holds a token that means "Alice, on `assistant`".
2. Her call to `github__list_issues` reaches a `per_user` upstream server. No GitHub account is stored for Alice, so the
   call returns a connect link. She authorises at GitHub and retries. The call now carries **her** GitHub token, the
   upstream sees `X-MCP-User: <Alice's id>`, and the audit record says Alice.
3. **Bob** does the same on the same endpoint and ends up with his own GitHub token. Neither can act as the other.
4. **The script** uses an `endpoint` API key on a second endpoint of the same bundle. It is identified as
   `api_key:<id>`, cannot use a `per_user` upstream server, and would use a `shared` upstream account if one were
   configured.

## Secrets at a glance

| Secret | Format | Who holds it | Lifetime |
|---|---|---|---|
| Access token | `bmcp_at_…` | MCP client | 1 hour (configurable) |
| Refresh token | `bmcp_rt_…` | MCP client | 7 days, rotated each use |
| API key | `bmcp_sk_…` | scripts, services | no expiry; revoke manually |
| Upstream OAuth token | provider-specific | the gateway (encrypted) | refreshed automatically |
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
through the gateway. For proof, introspect a forwarded bearer.

**"A token works on one endpoint but not another — is it broken?"** No, that is endpoint binding. Re-authorize on the
second endpoint.
