---
description: "How a metamcp setup maps onto bundlemcp, what bundlemcp leaves out, and how to move servers, namespaces
  and endpoints over."
---

# Coming from metamcp

bundlemcp began as a rewrite of the bundling core of [metamcp](https://github.com/metatool-ai/metamcp), so most of what
you set up there has a direct counterpart here. This page is for someone running metamcp and deciding whether to move:
how the concepts map, what bundlemcp deliberately leaves out, how to bring a setup over, and what you get in return.

::: info Compared against metamcp 2.4.22
Everything this page says about metamcp comes from the documentation of
[metamcp v2.4.22](https://github.com/metatool-ai/metamcp/tree/v2.4.22), the latest release when it was written. If you
run a later version, check its documentation for what changed.
:::

## How the concepts map

| metamcp | bundlemcp | What differs |
|---|---|---|
| [MCP server](https://github.com/metatool-ai/metamcp/blob/v2.4.22/docs/en/concepts/mcp-servers.mdx), type `STREAMABLE_HTTP` | [Upstream server](/manage/servers) | The same URL. A `bearerToken` or custom `headers` become `static_headers`; a server that wants its own OAuth login uses [upstream OAuth](/guide/authentication#upstream-identity-how-the-gateway-reaches-an-upstream-server), with a token per user if you choose. |
| MCP server, type `STDIO` | An upstream server behind a [sidecar](/connect/stdio-sidecar) | bundlemcp never starts processes. The same `command` and `args` run in a small container next to the gateway, which you register by its URL. The server's `env` goes to that container. |
| MCP server, type `SSE` | An upstream server at its Streamable HTTP URL | bundlemcp speaks Streamable HTTP only. Most servers that offered SSE now offer Streamable HTTP too; for one that does not, a sidecar can bridge it. |
| `${ENV_VAR}` in a server's `env` | Substituted before the gateway reads the document | A [bootstrap document](/self-hosting/bootstrap) does no substitution of its own: template it from your secret store before it reaches the container. |
| [Namespace](https://github.com/metatool-ai/metamcp/blob/v2.4.22/docs/en/concepts/namespaces.mdx) | [Bundle](/manage/bundles) | A bundle groups upstream servers into one virtual server, as a namespace does. A member can be turned off without leaving the bundle, as a server in a namespace can. |
| Tool prefix `ServerName__toolName` | Tool prefix `server__tool` | The same scheme, so clients see the same names unless you rename a tool. |
| Tool turned off, and tool overrides (name, title, description, annotations) | [Tool curation](/manage/bundles#curating-tools) | The same four overrides and the same on/off switch, set per bundle. A tool that is turned off is never listed, so there is no "filter inactive tools" step to add. |
| Namespace middleware | [Endpoint profiles](/manage/endpoints#profiles) and the [metering hook](/integrate/metering-hook) | metamcp's built-in middleware filters inactive tools, which curation already does. Shaping what a client sees is the endpoint profile's job, and intercepting tool calls is the metering hook's. |
| [Endpoint](https://github.com/metatool-ai/metamcp/blob/v2.4.22/docs/en/concepts/endpoints.mdx) | [Endpoint](/manage/endpoints) | Served at `<public URL>/<name>/mcp` instead of `/metamcp/<name>/mcp`. There is no `/sse` route and no `/api` OpenAPI route. One bundle can have several endpoints, each with its own profile, auth modes and rate limits. |
| Endpoint auth: API key, or MCP OAuth | Endpoint [auth modes](/manage/endpoints#auth-modes) `api_key` and `oauth` | The API key goes in the `Authorization: Bearer` header only. OAuth is the gateway's own OAuth 2.1 server, with dynamic client registration and a consent page. |
| API keys (`sk_mt_…`), private or public | [API keys](/manage/api-keys) (`bmcp_sk_…`), service or endpoint keys | A service key manages the gateway; an endpoint key calls the endpoints it is scoped to. Keys belong to the workspace, not to a user. |
| [Inspector](https://github.com/metatool-ai/metamcp/blob/v2.4.22/README.md#-inspector) | [Inspector](/manage/inspector) | Tries an upstream server directly or an endpoint as a client would, without a separate MCP client. |
| Sign-in with Better Auth accounts or OIDC | Sign-in with your [identity provider](/self-hosting/identity-provider) (OIDC) | bundlemcp stores no passwords; every admin signs in through OIDC. |

## What bundlemcp leaves out

Some of metamcp's features were left out on purpose, to keep the gateway small and its failure modes simple. The
reasons are in the
[decision log](https://github.com/wingfold-ai/bundlemcp/blob/main/openspec/README.md#decision-log--deliberately-dropped-from-metamcp).
A dropped feature comes back only with new evidence; if yours is one, say so in
[Discussions](https://github.com/wingfold-ai/bundlemcp/discussions/categories/ideas).

| metamcp feature | Instead |
|---|---|
| STDIO servers started by the gateway | Run the server in a [sidecar](/connect/stdio-sidecar) and register its URL. |
| SSE, towards servers and towards clients | Streamable HTTP in both directions. A client that only speaks stdio, such as a desktop app, connects through a local proxy, as it does with metamcp. |
| The OpenAPI bridge (`/api`, `openapi.json`) | No replacement. Clients that need REST rather than MCP are not a target. |
| API keys in a `?api_key=` query parameter | The `Authorization: Bearer` header. A key in a URL ends up in logs. |
| Private and public resources per user | One shared workspace: every admin sees and manages everything. Separating tenants is left to an application built on bundlemcp. |
| Admin tools over MCP | The [management API](/integrate/management-api), which an agent can call over HTTP. |
| Local password accounts | OIDC sign-in only. |
| Translations of the admin UI | English only. |
| The registry browser | Servers arrive through the UI, the management API or a bootstrap document. |

## Moving a setup over

There is no importer yet: one that reads a metamcp database and brings servers, namespaces and endpoints over in one
step is a theme on the [roadmap](/roadmap). Until then you move a setup by writing it down as a
[bootstrap document](/self-hosting/bootstrap), which the gateway applies at startup, or which you
[import](/manage/export-import) into a running gateway.

The example below moves a small metamcp setup: three servers (one of them stdio), a namespace with two tool overrides
and a tool turned off, and two endpoints, one for claude.ai with OAuth and one for scripts with an API key. Each part
names the metamcp setting it replaces.

<<< @/snippets/metamcp-migration.yaml

Then:

1. **Start the sidecar** for each stdio server, as on the [sidecar page](/connect/stdio-sidecar). Here that is a
   container named `hn-mcp` running `uvx mcp-hn` behind Supergateway.
2. **Apply the document**, either at startup with `BUNDLEMCP_BOOTSTRAP_FILE`, or into a running gateway with
   `POST /api/v1/import`. Substitute the secrets first; the document itself never holds them in your repository.
3. **Apply it once more** after the first start. Curation names tools as their server names them, so it can only land
   once the gateway has discovered them; the second run, or a restart, sets the overrides.
4. **Create the API keys** your scripts used, as endpoint keys scoped to `research-api`, and hand out the new values.
   metamcp keys do not carry over.
5. **Reconnect the clients.** claude.ai and ChatGPT add the new endpoint URL as a connector and go through the
   gateway's sign-in once.

Users, OAuth clients and consents are never part of a document; people sign in to the new gateway themselves.

## What you get in return

- **Restart-safe sessions and replicas.** Session state lives outside the gateway process, so a restart does not end
  sessions and several replicas serve the same clients. See [Two kinds of data](/guide/concepts#two-kinds-of-data) and
  [Scaling out](/self-hosting/deploy#scaling-out).
- **One endpoint per client.** The same bundle served differently to claude.ai, ChatGPT and scripts, through
  [endpoint profiles](/manage/endpoints#profiles) and
  [several endpoints per bundle](/manage/endpoints#one-bundle-several-endpoints).
- **Per-user tokens for upstream servers.** Each user connects their own account to an OAuth-protected upstream, and the
  gateway can [forward who is calling](/integrate/upstream-identity).
- **An audit log** of every tool call, with filters and CSV export: [Audit log](/manage/audit).
- **A metering hook** for applications that count or bill tool calls: [Metering hook](/integrate/metering-hook).
- **Configuration as a document.** The whole setup [exports](/manage/export-import) as the same document a gateway
  bootstraps from.
