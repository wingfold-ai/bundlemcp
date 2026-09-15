# Roles and identity

Two questions come up on every deployment: who may do what, and which
identity a call carries at each step. This page answers both. For *how* each
credential is obtained and validated — the identity provider, the gateway's
OAuth server, API keys, and the pass-through to upstream servers — read
[Authentication](/guide/authentication) first.

## Two roles

Everyone who reaches bundlemcp signs in at the same identity provider. What
they can do afterwards depends on one thing: whether their email is listed in
`BUNDLEMCP_ADMIN_EMAILS`, re-checked at every login.

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

An **administrator** builds the platform: which servers exist, how they are
composed, under which contracts they are exposed. The management UI and the
management API are theirs.

A **user** consumes it. After signing in they see one page, the
**catalogue**: every bundle that has an endpoint accepting OAuth, and inside
each bundle the endpoints with the URL to paste into an MCP client and the
steps for that client. They do not create endpoints, bundles or API keys, and
they have no management API. Using an endpoint as a person always goes through
their gateway identity.

This split is deliberate. Endpoints are public URLs on your gateway with
their own security contract, servers carry credentials and reach into your
network, and API keys are long-lived secrets. Deciding those once, as an
administrator, keeps the gateway a single shared workspace. Anything finer,
such as which person may use which bundle, belongs to the identity provider
(who may log in at all) or to an application layer using the
[metering hook](/integrate/metering-hook).

## Which identity, when

A tool call passes two boundaries, and each has its own identity.

### 1. The client reaches the gateway: the caller identity

Every request through an endpoint resolves one **caller identity**, and
everything downstream keys on it: rate limits, the audit record, the metering
hook, and what upstream servers are told.

| The client presents | Resolved identity | Who this is for |
|---|---|---|
| An OAuth bearer minted by the gateway | the person's user id (`sub`) | People and their MCP clients: claude.ai, ChatGPT, Claude Code |
| An endpoint or service API key | `api_key:<key id>` | Scripts, agents, automation, upstream servers verifying bearers |
| Nothing, on an endpoint with auth mode `none` | anonymous | Deliberately open endpoints |

When a request carries both a bearer and a key, the bearer wins.

The OAuth path is how a person connects: the MCP client is sent to the
gateway's authorization server, the gateway federates the login to your
identity provider, shows a consent screen naming the client and the endpoint,
and mints a token bound to that person and that endpoint. The MCP client
never handles the person's password and has no identity of its own; the
person is the identity, in whichever client they use.

An endpoint's `auth_modes` decides which of these it accepts. An endpoint
that accepts OAuth appears in the catalogue; an endpoint that accepts only
API keys is for automation and does not.

### 2. The gateway reaches an upstream server: the upstream identity

Each server's `auth_mode` decides how the gateway authenticates *to it*, and
this is independent of who called:

| `auth_mode` | Identity toward the upstream | Typical case |
|---|---|---|
| `none` | none | Servers on your own network that trust the gateway |
| `static_headers` | one fixed credential, such as an API key header, for every caller | A hosted server with a service key |
| `upstream_oauth`, `identity_mode: shared` | one OAuth account an administrator connected once | A service account at the upstream |
| `upstream_oauth`, `identity_mode: per_user` | the caller's own account at the upstream | GitHub, Google, a CRM: anything where the upstream must see the person |

With `per_user`, the first tool call a person makes without a stored account
fails with a structured MCP error that carries a connect link. They open it,
sign in at the upstream in their browser, and retry; from then on their calls
carry their own upstream token, encrypted at rest and refreshed
automatically. Two people using the same endpoint therefore act as two
different upstream accounts, and an administrator's connection is never
substituted for a user's.

One account per person per server: a person's upstream token is shared by
every MCP client they use. Because the caller must be a person, a `per_user`
server cannot sit behind an endpoint with auth mode `none`, and the gateway
refuses that combination.

Independently of `auth_mode`, two mechanisms tell the upstream **who** is
calling: the injected `X-MCP-User` header with the caller identity, and
optional forwarding of the caller's bearer so the upstream can verify it
against the gateway's introspection route. Details in
[Identity for upstream servers](/integrate/upstream-identity).

## The same picture as a walk-through

1. Alice, not an administrator, signs in and opens the catalogue. She sees
   the `assistant` bundle with its `assistant` endpoint shaped for claude.ai.
2. She adds the URL in claude.ai. claude.ai registers itself at the gateway,
   Alice signs in at the identity provider once more, approves the consent,
   and claude.ai holds a token that says "Alice, on `assistant`".
3. Her first call to `github__list_issues` reaches a `per_user` server. No
   GitHub account is stored for Alice, so the call returns a connect link.
   She opens it, authorises at GitHub, and retries. The call now carries
   Alice's GitHub token; the audit record says Alice called it.
4. Bob does the same on the same endpoint and ends up with his own GitHub
   token. A nightly script uses an endpoint API key on a second endpoint of
   the same bundle; it is identified as that key, and could only use the
   server's shared account, if one were configured.
