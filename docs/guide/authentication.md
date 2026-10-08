# Authentication

Authentication in bundlemcp is easy to find confusing because there are **two directions** — proving who a caller is
*to* the gateway, and telling an upstream server who the caller is — and because the gateway plays
**three different OAuth roles** at once. This page separates them, then walks through each path end to end.

If you only read one thing: the **identity provider (Keycloak, Entra, …)** is where a *human* is authenticated; the
**gateway's OAuth server** is what an *MCP client* uses to get access to an endpoint; and an **API key** is how a
*script* authenticates. They are three different things that all end up as one "caller identity".

## The three roles

bundlemcp is, depending on who it is talking to:

| Role | Meaning | Talks to | Example |
|---|---|---|---|
| **Authorization server** | It issues access tokens | MCP clients | claude.ai gets a token for the `assistant` endpoint |
| **Resource server** | It validates its own tokens | MCP clients | A `tools/call` presents that token |
| **OAuth client** | It obtains tokens from someone else | Upstream MCP servers | The gateway signs in to GitHub on a user's behalf |

## The two directions

```
DIRECTION 1 — does the caller get in?
  Client / script / browser ──── credential ────▶ bundlemcp
                                                   │  resolves one "caller identity"

DIRECTION 2 — what does the upstream see?
  bundlemcp ──── identity or credential ────▶ upstream MCP server
                                                   │  X-MCP-User, a forwarded bearer,
                                                   │  or an upstream OAuth token
```

Everything downstream in the gateway — rate limits, the audit record, the metering hook — keys on the
**caller identity** from Direction 1. Direction 2 never changes *who* the call is attributed to; it only decides what
the upstream is told.

---

## Direction 1 — proving who you are to bundlemcp

There are four ways in, and an endpoint picks which it accepts with its `auth_modes`: `oauth`, `api_key`, or `none`.

### Path A — a person in the admin UI or management API

This is **OIDC-only**. There are no passwords, no signup and no password reset — not a missing feature, a deliberate
deletion of that whole class of code.

```
browser  ── GET /login ──▶  identity provider (Keycloak, Entra, Okta, Auth0)
                                   │  sign in
        ◀── /login/callback ───────┘
gateway: verify the ID token, provision or update a User from (issuer, sub),
         set a signed httpOnly cookie + a session record in Valkey
```

What to take from this:

- The **human** is authenticated by the identity provider, not by bundlemcp.
  bundlemcp trusts the provider's ID token and creates a local `User` row the
  first time it sees that `(issuer, sub)` pair.
- A **session** is two things: a signed cookie held by the browser, and a
  record in Valkey so any replica can serve it. It has a maximum age that
  forces a periodic re-login.
- **Administrator vs user** is one property, `is_admin`, re-evaluated at
  every login from `BUNDLEMCP_ADMIN_EMAILS`. A non-admin can still log in, but
  only sees the catalogue: the management API answers 401 to them on every
  route except `/api/v1/me/…`. See
  [status codes](/integrate/management-api#authentication) — 401, not 403, is
  deliberate but easy to misread.
- A **service API key** can also call the management API, which is how
  automation configures the gateway without a browser. That is the only place
  API keys and sessions overlap; the cookie wins when both are present.

Details: [Identity provider](/self-hosting/identity-provider),
[Roles and identity](/guide/roles-and-identity).

### Path B — a person connecting an MCP client (claude.ai, ChatGPT)

Here it gets interesting, because there are **two OAuth conversations**:

```
claude.ai ─── OAuth 2.1 ───▶  gateway's OAuth server  ─── OIDC ───▶  identity provider
 (wants a token for            (issues the connector's              (authenticates the human)
  the endpoint)                 access token)
```

The identity provider answers **"who is this person?"**. The gateway's OAuth server answers
**"may this client act for that person on this endpoint?"** — and records the answer as an access token. Both happen
inside one browser redirect chain, so it feels like one login, but they are separate systems.

Step by step:

1. **Discovery.** claude.ai fetches the endpoint's protected-resource metadata
   (`/.well-known/oauth-protected-resource/<endpoint>/mcp`) and the gateway's authorization-server metadata
   (`/.well-known/oauth-authorization-server`).
2. **Registration.** claude.ai registers itself (RFC 7591 dynamic client registration), or presents a `client_id` that
   is an `https://` URL whose metadata document the gateway fetches. ChatGPT and Claude still commonly use registration.
3. **Authorize.** `GET /oauth/authorize` carries the client id, redirect URI, PKCE challenge (`S256`, required), and a
   `resource` naming the target endpoint. If the browser has no gateway session, the gateway redirects to `/login` (Path
   A) and returns here afterwards.
4. **Consent.** The user approves a screen naming the client, the endpoint and the scope. Consent is remembered per
   `(user, client, endpoint)` and skipped until revoked.
5. **Code → tokens.** The gateway redirects back with a single-use authorization code (10-minute life). The client
   exchanges it at `POST /oauth/token` for:
   - an **access token** (`bmcp_at_…`, opaque, one hour by default), and
   - a **refresh token** (`bmcp_rt_…`, seven days, **rotated on every use**). A refresh token presented twice is treated
     as stolen and the whole token family is revoked.
6. **Calls.** The client sends `Authorization: Bearer bmcp_at_…` to `/{endpoint}/mcp`. The gateway hashes it, looks it
   up directly (never via an HTTP self-call) and checks that it is not revoked or expired, that its
   **audience is this endpoint**, and that the user is still active.

Two properties are worth stating plainly:

- **Tokens are bound to one endpoint.** A token issued for `assistant` is refused at `assistant-gpt` (RFC 8707
  `resource` → audience). A client simply re-authorizes at the other endpoint.
- **Authorization responses carry `iss`** (RFC 9207), so a client can detect a mix-up between two authorization servers.

Details: [Connect claude.ai](/connect/claude).

### Path C — a script or agent with an API key

Anything that cannot run a browser uses an **API key** (`bmcp_sk_…`), sent as `Authorization: Bearer` or `X-API-Key`
(never a query parameter). Keys come in two kinds:

| Kind | May call |
|---|---|
| `endpoint` | MCP endpoints that accept `api_key`, restricted to its scoped endpoints |
| `service` | The same, **plus** the management API and the introspection route |

A key is a *machine* identity. Its caller identity is `api_key:<id>`, which is what audit, metering and `X-MCP-User` all
report. Keys are hashed at rest and shown once at creation.

Details: [API keys](/manage/api-keys).

### Path D — an open endpoint

An endpoint whose `auth_modes` is `["none"]` admits anyone. The caller identity is anonymous: no `sub`, audit and
metering see no user, `X-MCP-User` is omitted upstream, and a `per_user` upstream server can never be reached through it
(the gateway rejects that combination).

### How the gateway chooses

Within an endpoint, the gateway tries the credentials it accepts, strongest first:

```
OAuth bearer  →  API key  →  anonymous (only if the endpoint accepts none)
```

So if a request carries both a bearer and a key, the bearer wins. Repeated bad credentials from one IP are throttled
(and locked out) before any database lookup.

---

## Direction 2 — telling the upstream who is calling

Once the caller identity is resolved, the gateway reaches the upstream MCP server. How that server learns who is calling
is independent of how the caller authenticated. Three mechanisms, and they can be combined.

### `X-MCP-User` — trusted on the internal network

When a server's `send_identity_header` is on (default), every upstream call carries `X-MCP-User: <sub>` — the user id
for OAuth callers, `api_key:<id>` for key callers, omitted for anonymous. The gateway
**strips any client-supplied `X-MCP-User`**, so the header can only come from the gateway.

This is a plain header, not a signed assertion. Trust it only when the server is reachable *only* through the gateway (a
compose or cluster network). For a server that also faces the internet, use the next mechanism.

### Forwarded bearer + introspection — verifiable

To let an upstream *verify* the caller, forward the client's own `Authorization` header and have the server ask the
gateway whether it is valid:

1. Register the server with `forward_headers: {"authorization": "authorization"}`.
2. Give the server a `service` API key.
3. The server calls the introspection route (never anonymous):

```bash
curl -s https://gw.example.com/oauth/introspect \
  -u "bundlemcp:bmcp_sk_<service key>" \
  -d "token=<the forwarded bearer>"
```

```json
{ "active": true, "sub": "…", "client_id": "…", "exp": 1757340000, "scope": "…", "aud": "…" }
```

A forwarded **API key** introspects as active with `sub` `api_key:<id>` too, so a server written for introspection
serves key callers without a second code path. The upstream connection is keyed by the forwarded values, never just by
`sub`, so one user's credential can never serve another's request.

Details: [Identity for upstream servers](/integrate/upstream-identity).

### Upstream OAuth — the gateway signs in for you

When the upstream is itself OAuth-protected (GitHub, Google, a CRM), the gateway acts as an **OAuth client** to it and
attaches its own bearer:

| `identity_mode` | Whose upstream account | Who connects it |
|---|---|---|
| `shared` | one service account for everybody | an administrator, once |
| `per_user` | the caller's own account | each user, on first call |

With `per_user`, the first call a person makes without a stored account returns a structured MCP error carrying a
connect link. They authorise at the upstream in their browser and retry; from then on their calls carry their own
upstream token, encrypted at rest and refreshed automatically. An administrator's connection is never substituted for a
user's.

Because the caller must be a person, a `per_user` server cannot sit behind a `none`-auth endpoint; the gateway refuses
that combination.

Details: [Servers](/manage/servers#upstream-oauth).

---

## End to end

Alice, a non-admin, and a nightly script, on the same bundle:

1. **Alice** signs in and opens the catalogue. She adds the `assistant` endpoint's URL in claude.ai. claude.ai
   registers, Alice signs in at the identity provider, approves consent, and claude.ai holds a token that means "Alice,
   on `assistant`".
2. Her call to `github__list_issues` reaches a `per_user` server. No GitHub account is stored for Alice, so the call
   returns a connect link; she authorises at GitHub and retries. The call now carries **her** GitHub token, the upstream
   sees `X-MCP-User: <Alice's id>`, and the audit record says Alice.
3. **The script** uses an `endpoint` API key on a second endpoint of the same bundle. It is identified as
   `api_key:<id>`, cannot use a `per_user` server, and would use a `shared` upstream account if one were configured.

## Secrets at a glance

| Secret | Format | Who holds it | Lifetime |
|---|---|---|---|
| Access token | `bmcp_at_…` | MCP client | 1 hour (configurable) |
| Refresh token | `bmcp_rt_…` | MCP client | 7 days, rotated each use |
| API key | `bmcp_sk_…` | scripts, services | no expiry; revoke manually |
| Upstream OAuth token | provider-specific | the gateway (encrypted) | refreshed automatically |
| Admin session | signed cookie | the browser | bounded by max age |

Everything is stored hashed (tokens and keys) or encrypted (upstream tokens), and nothing secret is ever logged or
returned by an API.

## Common confusions

**"Why do I sign in twice when connecting claude.ai?"** You do not, in practice: the gateway only redirects to the
identity provider when you have no session yet. The two systems are distinct, but the browser flow is one trip.

**"Why can't my endpoint API key call `/api/v1`?"** Only `service` keys reach the management API. Endpoint keys are for
tools.

**"Where is the user's password?"** Nowhere in bundlemcp. It lives at your identity provider; the gateway only ever sees
an ID token.

**"Does the MCP client have its own identity?"** No. The token stands for the person; the client is just the software
presenting it. Every client a person uses resolves to the same user and the same upstream accounts.

**"Is `X-MCP-User` proof of anything?"** It is trusted only on a network where the upstream is reachable solely through
the gateway. For proof, introspect a forwarded bearer.

**"A token works on one endpoint but not another — is it broken?"** No, that is audience binding. Re-authorize on the
second endpoint.