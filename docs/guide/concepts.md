# Core concepts

This page explains the ideas bundlemcp is built from, for someone who has just started with MCP. If you have not run it
yet, the [Quickstart](/guide/quickstart) shows each of them in the admin UI.

## MCP in two paragraphs

The **Model Context Protocol** (MCP) is how an AI application — claude.ai, ChatGPT, Claude Code, your own agent — talks
to the systems that give it abilities and context. The application is the **MCP client**. Each system is an
**MCP server**, which offers the client three kinds of things:

| A server offers | What it is | Who decides to use it | Example |
|---|---|---|---|
| **Tools** | Actions the model can take | The model, while it works | `get_forecast(city)`, `run_python(code)` |
| **Prompts** | Ready-made instructions with blanks to fill in | The person, usually by picking one from a menu | "Summarise this pull request" |
| **Resources** | Documents and data the client can read into the conversation | The application or the person | A style guide, a database schema, a file |

Without a gateway, every client connects to every server on its own, each with its own sign-in. bundlemcp sits in the
middle: clients connect to bundlemcp once, and bundlemcp connects to the servers.

## The four things you configure

Everything in bundlemcp is built from four pieces. Read them in the order a request travels — from the client inwards:

```text
MCP client ──▶ endpoint ──▶ bundle ──▶ upstream servers
               URL + who     which        the MCP servers that
               may use it    tools        actually do the work
```

- An **upstream server** (or **upstream** for short) is an MCP server that bundlemcp forwards to.
- A **bundle** combines several upstream servers into what looks, to a client, like one server.
- An **endpoint** publishes a bundle at a URL, with the rules for who may use it and how.
- An **API key** lets a script or agent use an endpoint without a person signing in.

People and the OAuth registrations of their clients (claude.ai, ChatGPT) appear on their own once an endpoint is in use;
you do not create them. How they sign in is explained in [Authentication](/guide/authentication).

## Upstream servers

An upstream server is an MCP server that bundlemcp talks to over **Streamable HTTP**, MCP's transport for servers
reached over the network. "Upstream" says which way it faces: clients are downstream of the gateway, the servers it
forwards to are upstream — so the short name for one is simply an *upstream*, and that is what the management API
calls them. The admin UI lists them on the **Upstream servers** page.

Most upstream servers need only a name and a URL. The other settings exist for servers that need a credential, want to
know who is calling, or have each person sign in to their own account. Each is explained, with the situations it is for,
on [Upstream server settings](/guide/upstream-server-settings):

| Setting | In one line |
|---|---|
| `name` | Unique, letters, digits, `-` and `_`, never `__`. Becomes the prefix of every tool the server contributes. |
| `url` | Where the server is reached, for example `http://weather:8080/mcp`. [More](/guide/upstream-server-settings#url) |
| `auth_mode` | How the gateway proves itself to the server: no credential, a fixed key, or OAuth. [More](/guide/upstream-server-settings#auth_mode) |
| `static_headers` | A fixed credential, such as an API key, sent with every request. [More](/guide/upstream-server-settings#static_headers) |
| `forward_headers` | Headers from the client's request passed on to the server. [More](/guide/upstream-server-settings#forward_headers) |
| `send_identity_header` | Tells your own servers which user is calling. [More](/guide/upstream-server-settings#send_identity_header) |
| `identity_mode` | With OAuth: one shared account for everyone, or each person their own. [More](/guide/upstream-server-settings#identity_mode) |
| `protocol_mode` | Which MCP revision to speak to the server; `auto` is right almost always. [More](/guide/upstream-server-settings#protocol_mode) |

When you register an upstream server, the gateway **probes** it: connects, agrees on a protocol revision and asks for
its tool list. A failed probe never blocks registration — the server is stored with its error, so you can register one
that is not running yet.

## Tools, prompts and resources

The three things an upstream server offers are handled differently, because they are used differently.

**Tools are copied and curated.** The gateway stores each upstream's tool list — name, description, input
schema — and answers clients from that copy. That has two effects. A client's request for the list never wakes an
upstream, and keeps working while one is down. And because the list is the gateway's own, a bundle can hide a
tool or change how it is presented without touching the server. The copy is refreshed when you change the server, when
you ask for it, and periodically.

**Prompts and resources are passed through.** When a client asks for them, the gateway asks the upstreams live
and hands the answer back unchanged: prompt names are prefixed with the server name, exactly like tool names; resource
addresses are passed on as they are. Only servers that said they offer prompts or resources are asked.

::: info Planned: prompts and resources of the bundle's own
The same upstream server often serves very different bundles. A Python-execution server might sit in a bundle for
drawing charts and in one for bookkeeping. Today the server's own prompts and resources are the same in both. A planned
change lets each bundle add its own — chart conventions in one, rounding and currency rules in the other — so the same
tools come with context for the bundle's purpose. The design is in review in
[pull request #99](https://github.com/wingfold-ai/bundlemcp/pull/99).
:::

## Bundles

A bundle is a set of upstreams presented as **one MCP server**. A client connected to a bundle sees the tools of
every member server, as if they all came from one place. The bundle's description is sent to the model as that server's
instructions.

Every tool is presented as `<server name>__<tool name>`, such as `weather__get_forecast`. The prefix keeps two servers'
tools apart when both have a `search`, and it is how the gateway knows where to forward a call. That is why upstream
server names may not contain `__`.

Each bundle decides, per tool, whether to **show** it and how to **present** it — a different name, title, description
or hints. That is *curation*, and it is per bundle: the same server can offer all its tools in one bundle and only the
read-only ones in another.

## Endpoints and profiles

A bundle decides *what* a client gets. It does not decide *who* may use it, or *how* a particular client needs it
served. Those are separate because the same set of tools is often wanted by very different clients at once: you in
claude.ai, a colleague in ChatGPT, a nightly script. Each needs a different way in.

### Endpoints: the way in

An **endpoint** is one way into one bundle: a URL, `<public url>/<endpoint name>/mcp`, plus its rules. It is what you
paste into a client. A bundle can have as many endpoints as it has kinds of clients.

| Setting | What it decides |
|---|---|
| Bundle | Which bundle this URL serves. |
| Auth modes | How a caller proves who they are: `oauth` (a person signs in, as claude.ai and ChatGPT do), `api_key` (a script sends a key), or `none` (anyone, which must be allowed explicitly). Several can be allowed at once. |
| Profile | Which client the endpoint is shaped for (below). |
| Rate limits | Optional caps on calls per time window: for the whole endpoint, and per caller. |
| Enabled | A disabled endpoint answers *not found* but keeps its settings. |

So the same `tools` bundle could have a `tools-claude` endpoint with OAuth for people and a `tools-cron` endpoint with
an API key and a tight rate limit for a script — two doors to the same room.

### Profiles: adapting to a client's habits

MCP clients do not all behave alike. claude.ai insists on a particular OAuth setup before it connects; ChatGPT is
stricter with tools that are marked as changing data, and may refuse them or ask for confirmation each time. A
**profile** adapts an endpoint to such habits, so you do not have to change your upstream servers to suit one client:

| Profile | Use it for | What it changes |
|---|---|---|
| `default` | Scripts, agents, Claude Code, most clients | Nothing. Tools are served as the bundle defines them. |
| `claude` | claude.ai and Claude Desktop | Requires OAuth and guarantees the sign-in metadata claude.ai looks for. Tools are unchanged. |
| `chatgpt` | ChatGPT | Marks every tool as read-only so ChatGPT accepts it. The tools still do what they do — a delete still deletes — so only use it with tools you trust. |

The endpoint says *who and how much*; the profile says *in which shape*. [Endpoints](/manage/endpoints) covers creating
them, and [Connect clients](/connect/claude) has a page per client.

## Two kinds of data

The gateway keeps two kinds of data, and treats them differently on purpose:

- **Configuration** is what you set up and what people agreed to: upstream servers, bundles, endpoints, API keys, users,
  their consents and connected accounts, and the audit log. It must survive anything, so it is kept in a database and
  belongs in your backups.
- **Live state** is what exists only while clients are connected: open sessions, rate-limit counters, a half-finished
  sign-in, and the messages that tell other copies of the gateway that something changed. It is short-lived, so losing
  it costs little — clients simply connect again.

Neither is kept in the memory of a single gateway process. That is what lets you run several copies side by side,
restart one, or roll out a new version without clients noticing: any copy can serve any request. Which stores hold the
two kinds is a deployment detail; see [Requirements](/self-hosting/requirements).
