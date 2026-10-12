# Upstream server settings explained

An **upstream server** is an MCP server that bundlemcp connects to on your behalf. Your MCP client (claude.ai, ChatGPT,
a script) only ever talks to the gateway; the gateway then talks to each upstream server. Most of an upstream server's
settings answer one of two questions about that second hop:

- **How does the gateway get in?** Some upstream servers answer anyone, some want an API key, some want each person to
  sign in with their own account.
- **What does the upstream server learn about the caller?** Your own servers often want to know which user is calling;
  third-party servers should usually learn nothing.

This page explains every setting in plain terms, with the situation it is made for. For the full reference, see
[Upstream servers](/manage/servers); for what a server you write yourself receives, see
[Identity for upstream servers](/integrate/upstream-identity).

## Which settings does my server need? {#which-settings}

When you register an upstream server in the admin UI, it asks one question, **Where does the credential come from?**,
and pre-selects the answer the server itself gave when the gateway checked it. The answers map to settings like this:

| Your situation | Answer in the UI | Settings |
|---|---|---|
| The server needs no login at all (a public demo, a server on your own network). | No credential needed | [`auth_mode`](#auth_mode) `none` |
| The server's docs give you an API key or personal access token, and everyone may share it. | A key or token I enter | [`static_headers`](#static_headers) |
| Each person should use their own account at the service (GitHub, Linear, Notion-style). | Each user signs in with their own account | [`auth_mode`](#auth_mode) `upstream_oauth`, [`identity_mode`](#identity_mode) `per_user` |
| One service account, signed in once by an admin, should serve everyone. | One shared account I sign in with once | [`auth_mode`](#auth_mode) `upstream_oauth`, [`identity_mode`](#identity_mode) `shared` |
| The provider gave you a client id and secret for machine access. | One shared machine account (client credentials) | as above, with a client credentials client |
| It is your own server and it must verify who is calling. | A token the gateway issues for each caller | [`auth_mode`](#auth_mode) `delegated_token` |

The remaining settings — [`forward_headers`](#forward_headers), [`send_identity_header`](#send_identity_header) and
[`protocol_mode`](#protocol_mode) — sit under **Advanced**, because their defaults are right for almost every server.

## URL {#url}

**What it is.** The address the gateway connects to, for example `https://mcp.example.com/mcp` or, for a server running
next to the gateway in Docker, `http://weather:8080/mcp`. bundlemcp speaks MCP's Streamable HTTP transport only; a
server that runs as a local command (stdio) needs a [small HTTP sidecar](/connect/stdio-sidecar) first.

**Things to know.**

- The gateway dials this URL itself, from wherever it runs. Inside a container, `localhost` is the container, not your
  machine; use the other service's name, or `host.docker.internal` for a server on your host.
- Addresses the gateway may not reach (its own loopback, cloud metadata addresses) are refused. See
  [Network egress](/self-hosting/deploy#network-egress).
- When you click **Check**, the gateway also tries the URL with `/mcp` appended and suggests it if that works.

**In the UI:** *Server URL* when registering, *URL* on the server's page. **API and bootstrap:** `url`.

## Auth mode {#auth_mode}

**What it is.** How the gateway proves itself to the upstream server. There are four values:

| Value | UI label | Meaning |
|---|---|---|
| `none` | no credential | The upstream server accepts requests without a credential. |
| `static_headers` | API key / static headers | A fixed credential, such as an API key header, is sent on every request. |
| `upstream_oauth` | upstream OAuth | The upstream server is OAuth-protected; the gateway signs in there and keeps the tokens. |
| `delegated_token` | delegated token | Each call carries a short-lived token the gateway issues for the caller, valid only at this server. |

You never pick between `none` and `static_headers` yourself: an upstream server with at least one
[static header](#static_headers) stored is `static_headers`, one without is `none`.

**When to use which.**

- **`none`** for a server that answers anyone who can reach it.
- **`static_headers`** for a service that hands out API keys, such as a weather or search API.
- **`upstream_oauth`** for a server that sends you to a sign-in page. Combine it with [`identity_mode`](#identity_mode)
  to choose whose account is used. It needs `BUNDLEMCP_TOKEN_ENCRYPTION_KEYS`, because the gateway stores the tokens
  encrypted. The step-by-step setup is in [Upstream OAuth](/manage/servers#upstream-oauth).
- **`delegated_token`** for a server **you** write that must know, and be able to check, who is calling. The server
  receives `Authorization: Bearer bmcp_dt_…` and asks the gateway what it means; the details are in
  [Identity for upstream servers](/integrate/upstream-identity#delegated-token-plus-introspection-verifiable-and-bound-to-you).

**In the UI:** the *Where does the credential come from?* choice when registering, *Auth mode* on the server's page.
**API and bootstrap:** `auth_mode`.

## Static headers {#static_headers}

**What problem it solves.** Many services identify you with an API key that you send in an HTTP header on every request,
for example `X-API-Key: abc123` or `Authorization: Bearer abc123`. Static headers are those headers: the gateway adds
them to every request it sends to this upstream server.

**Scenario.** You use a weather MCP server whose provider gave you the key `wk_live_…`. You add the header
`X-API-Key: wk_live_…`. Every caller of every bundle that includes this server now uses that one key, so everyone shares
its quota and its permissions.

**When not to use it.** When each person should act as themselves at the service, the shared key is wrong: use
[`upstream_oauth`](#auth_mode) with [`per_user`](#identity_mode) instead.

**Things to know.**

- Values are secrets. They are write-only: after you save, the API returns only the header **names**, and values never
  appear in logs.
- Saving the server again without static headers keeps the stored values. To change a value, save a header with the
  same name and the new value.
- A [forwarded header](#forward_headers) with the same name wins over a static one for that request.

**In the UI:** *Key or token* (with a *Header* preset) when registering; *Static headers (API keys, tokens)* on the
server's page. **API and bootstrap:** `static_headers`, an object of header name to value.

## Forward headers {#forward_headers}

**What problem it solves.** Sometimes the upstream server needs a value only the client knows, sent in a header of the
client's request. Forward headers copy selected headers from the incoming client request onto the request to the
upstream server, optionally under a different name.

**Scenario.** Your scripts call the gateway with `X-Tenant: acme`, and your internal reporting server needs to know the
tenant to pick the right database. You map `x-tenant` → `x-tenant`. A request without the header simply does not get
one.

**When not to use it.**

- Not for credentials you control: those are [static headers](#static_headers).
- Not to tell your own server who the user is: [`send_identity_header`](#send_identity_header) or
  [`delegated_token`](#auth_mode) do that without trusting the client.
- Avoid forwarding `authorization`. That passes the caller's own gateway token on to the upstream server — "token
  passthrough", which the MCP authorization spec forbids. It still works for trusted internal servers, and the UI warns
  when you configure it; prefer `delegated_token`.

**Things to know.** Some headers can never be forwarded and are rejected when you save: `host`, `cookie`,
`content-length`, `x-api-key`, `mcp-session-id`, and anything starting with `sec-` or `proxy-`.

**In the UI:** under *Advanced*, *Forward client headers (client header → upstream header)* when registering, *Forward
headers* on the server's page. **API and bootstrap:** `forward_headers`, an object of client header name to upstream
header name.

## Send identity header {#send_identity_header}

**What problem it solves.** A server you run often needs to know which person is calling, to keep each user's data
apart or apply a per-user limit. With this setting on, the gateway adds `X-MCP-User: <caller>` to every request: the
user's id for a signed-in person, `api_key:<id>` for a script using an API key.

**Scenario.** You run an internal note-taking MCP server on the same Docker network as the gateway. It stores notes per
user, keyed by `X-MCP-User`, and needs no login code of its own.

**When not to use it.** Leave it off for third-party servers: they would learn your users' ids. It is also only safe
when the upstream server can be reached **only** through the gateway, because the header is a plain value, not a
signature; anyone who can reach the server directly could send it. If the server must verify the caller, use
[`delegated_token`](#auth_mode).

**Things to know.**

- The default depends on where the server is. When you register a server without choosing, it is on for a host on the
  gateway's own network (a name without dots, `localhost`, names ending in `.local`, `.internal`, `.svc` or
  `.localhost`, or a private IP address) and off for public hosts. Editing a server keeps whatever it has.
- A client can never fake it: the gateway removes any `X-MCP-User` a client sends.
- On an endpoint without authentication there is no caller, so the header is not sent.

**In the UI:** the checkbox *Send the caller's identity as `X-MCP-User`* (under *Advanced* when registering). **API and
bootstrap:** `send_identity_header`.

## Identity mode {#identity_mode}

**What problem it solves.** For an OAuth-protected upstream server ([`upstream_oauth`](#auth_mode)), someone has to sign
in there. Identity mode decides whose account the gateway uses.

| Value | UI label | Meaning |
|---|---|---|
| `shared` | one shared account | An admin connects one account once; every caller uses it. |
| `per_user` | each user's own account | Each caller connects their own account the first time, and the upstream server sees them as themselves. |

**Scenarios.**

- **`per_user`:** a GitHub-style server where each person should see their own repositories. A user who has not
  connected yet finds an extra tool, `<server>__connect_account`, in their tool list; it returns the link to connect.
  After connecting, the server's real tools appear.
- **`shared`:** a company analytics service accessed through one service account, where it does not matter who asks.

**When not to use `per_user`.** It needs callers the gateway can tell apart, so it only works on endpoints where people
sign in. The gateway refuses to put a `per_user` server behind an endpoint without authentication, and API-key callers
are not offered the connect tool.

**Things to know.** Identity mode only matters with `upstream_oauth`; the UI shows it only then. The default is
`shared`; when the gateway detects an OAuth server while you register it, it suggests `per_user`, the safer choice.

**In the UI:** *Whose account* on the server's page; the registration choices *Each user signs in with their own
account* and *One shared account I sign in with once*. **API and bootstrap:** `identity_mode`.

## Protocol mode {#protocol_mode}

**What problem it solves.** MCP has several protocol revisions, and newer ones work differently from older ones. The
gateway works out on its own which revision an upstream server speaks; this setting lets you override that in the rare
case it gets it wrong.

| Value | UI label | Meaning |
|---|---|---|
| `auto` | auto — negotiate (recommended) | Try the newest revision first, fall back to the older `initialize` handshake. |
| `legacy` | legacy — always the initialize handshake | Always use the older handshake. |
| a date, e.g. `2026-07-28` | pin 2026-07-28 | Always use exactly that revision. |

**When to change it.** Almost never. Use `legacy` only for a server that speaks both revisions but asks the user
questions mid-call (elicitation, sampling) only over the older one. The revision the gateway actually negotiated is
shown as the server's *Protocol* in the server list.

**In the UI:** *Protocol*, under *Advanced*. **API and bootstrap:** `protocol_mode`.

## Where to go next

- [Upstream servers](/manage/servers) — registering, inspecting, upstream OAuth step by step, tools and health.
- [Identity for upstream servers](/integrate/upstream-identity) — what your own server receives and how to verify it.
- [Authentication](/guide/authentication) — how callers prove who they are to the gateway in the first place.
