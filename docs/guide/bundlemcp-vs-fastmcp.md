---
description: "bundlemcp vs. FastMCP: when to write an MCP server with FastMCP, and when to put an MCP gateway in front
  of several servers you did not write."
---

# bundlemcp vs. FastMCP

A common question when you look at bundlemcp: "Can't I just serve my tools with FastMCP?"

The two sit at different layers. [FastMCP](https://gofastmcp.com) is a Python framework for **writing** an MCP server.
bundlemcp is a gateway you **run** in front of MCP servers, whatever they are written in. They work together: bundlemcp
uses FastMCP as its client towards the upstream servers, and many of those upstream servers are FastMCP servers.

<LikeC4Diagram view="gatewayVsFramework" />

## When each fits

**Write the server with FastMCP** when you want to define tools, prompts and resources in Python. FastMCP can also
compose and proxy servers in code, and it ships authentication providers and middleware, so a single server you own
can be made remote-ready on its own.

**Put bundlemcp in front** when you have several servers, often ones you did not write, and want to serve them to
hosted clients without changing them:

- **One endpoint for many servers.** Servers are registered once, and their tools are combined into bundles with
  prefixed names (`server__tool`), so names never collide.
- **One login.** bundlemcp runs the OAuth 2.1 server claude.ai and ChatGPT connect to, and issues API keys for scripts.
  The upstream servers need no login of their own. When they do have one, bundlemcp can keep a token per user for
  them and forward the caller's identity.
- **Curation without code changes.** Hide, rename or re-describe a tool per bundle, and shape each endpoint for its
  client, for example re-annotating tools for ChatGPT.
- **Configuration instead of code.** Servers, bundles and endpoints change through the admin UI or the management API
  and apply live, without a redeploy.
- **Sessions that survive a restart.** Session state lives in Valkey, so any replica serves any request and a restart
  does not end sessions. An open event stream is still cut and has to reconnect.
- **One audit trail and one metering hook** across every bundled tool.
- **Mixed protocol revisions.** Each upstream is negotiated on its own, so clients and servers on different MCP
  revisions can work together.

## In short

| | FastMCP | bundlemcp |
|---|---|---|
| What it is | A framework you write an MCP server with | A gateway you run in front of MCP servers |
| You work in | Python code | The admin UI, the management API or a bootstrap file |
| Typical scope | One server, or a few composed in code | Many servers from different authors behind shared endpoints |
| Client login | Authentication providers you configure in code | A built-in OAuth 2.1 server plus API keys, shared by every bundled server |
| Per-client shaping | What your code exposes | Endpoint profiles and per-bundle curation |

If you only run one server that you wrote yourself, FastMCP alone may be all you need.
