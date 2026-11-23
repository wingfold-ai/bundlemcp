---
description: "The core concepts of the bundlemcp MCP gateway: upstream servers, bundles, endpoints, profiles and tool
  curation, and how they fit together."
---

# Core concepts

This page explains the ideas bundlemcp is built from. If you have not run it yet, the [Quickstart](/guide/quickstart)
shows each of them in the admin UI.

## MCP in brief

The **Model Context Protocol** (MCP) is a standard way for an AI assistant to use other software. It has two sides:

- The **MCP client** is the program you talk to the AI in: claude.ai or ChatGPT in the browser, Claude Desktop, Claude
  Code in the terminal, or an agent you wrote yourself. It holds the conversation and runs the model.
- An **MCP server** is a separate program that connects that model to one particular service — your GitHub account, a
  company database, a weather API. It describes what that service can do in a form the model understands, and does it
  when asked.

For example, with a GitHub MCP server connected, you can ask Claude to "open an issue for this bug": Claude, the client,
asks the GitHub MCP server to create the issue, and the server calls GitHub to do it. A server offers the client three
kinds of things:

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

Most upstream servers need only a name and a URL. The name becomes the prefix of every tool the server contributes (more
on that under [Bundles](#bundles)). The other settings exist for servers that need a credential, want to know who is
calling, or have each person sign in to their own account; [Upstream server settings](/guide/upstream-server-settings)
explains each of them.

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

**A bundle can also bring prompts and resources of its own.** The same upstream server often serves very different
bundles: a Python-execution server might sit in one bundle for drawing charts and in another for bookkeeping. Its tools
are identical in both, so what tells the model how to use them for *this* bundle is context — chart conventions in one,
rounding and currency rules in the other. You write that context on the bundle, as prompts and as documents, and the
gateway serves it itself, before the members' own: a bundle prompt's name has no server prefix, and a bundle document
is read as `bundle://resources/<name>`. Serving it never contacts an upstream. See
[Bundles: the bundle's own prompts and documents](../manage/bundles.md#bundle-prompts-and-documents).

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

An endpoint decides who may come in and how: whether a person signs in (`oauth`, as claude.ai and ChatGPT do), a
script sends an API key (`api_key`), or anyone may call it. It can also cap how often it is called, and be switched off
without losing its settings. [Endpoints](/manage/endpoints) lists every setting.

So the same `tools` bundle could have a `tools-claude` endpoint with OAuth for people and a `tools-cron` endpoint with
an API key and a tight rate limit for a script — two doors to the same room.

### Profiles: adapting to a client's habits

MCP clients do not all behave alike. claude.ai insists on a particular OAuth setup before it connects; ChatGPT is
stricter with tools that are marked as changing data, and may refuse them or ask for confirmation each time. A
**profile** adapts an endpoint to such habits, so you do not have to change your upstream servers to suit one client:

| Profile | What it changes | Recommended for |
|---|---|---|
| `default` | Nothing. Tools are served as the bundle defines them. | Scripts, agents, Claude Code, most clients |
| `oauth_only` | Requires OAuth as the only sign-in, with the metadata a client needs to find it. Tools are unchanged. | claude.ai and Claude Desktop |
| `write_as_read` | Marks every tool as read-only so a client wary of write tools accepts it. The tools still do what they do — a delete still deletes — so only use it with tools you trust. | ChatGPT |

A profile is named for what it does, not for a client: the recommendation can change without the profile changing.

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
