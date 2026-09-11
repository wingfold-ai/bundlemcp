---
aside: false
---

# What is bundlemcp?

bundlemcp is a self-hostable **MCP bundling gateway**. It sits between the MCP
clients your users run (claude.ai, ChatGPT, Claude Code, your own agents) and
the MCP servers you operate, and does one thing well: it **bundles MCP servers
and exposes the bundles the way each consuming client needs them**.

<div class="wide"><HomePipeline compact /></div>

- A **server** is an upstream MCP server reachable over Streamable HTTP. The
  gateway probes it, discovers its tools, and keeps that tool list cached.
- A **bundle** composes any number of servers into one virtual MCP server.
  Tools are prefixed with the server name so they never collide, and you can
  hide or rename tools per bundle.
- An **endpoint** is a public URL that serves one bundle. A bundle can have
  many endpoints, each with its own authentication modes, client profile and
  rate limits.

## Where it sits

The gateway is one system with five neighbours: the people who operate it,
the MCP clients that call it, the servers it aggregates, the identity
provider that authenticates humans, and, optionally, an application layer
that bills for calls and registers servers through the API.

<div class="wide">
<img src="/diagrams/index.png" class="diagram light-only" alt="System context: administrator, MCP clients, upstream MCP servers, OIDC identity provider and an optional application layer around the bundlemcp gateway">
<img src="/diagrams/dark/index.png" class="diagram dark-only" alt="System context: administrator, MCP clients, upstream MCP servers, OIDC identity provider and an optional application layer around the bundlemcp gateway">
</div>

## Who it is for

- **Teams that run several MCP servers** and want to hand their users a single
  connector instead of five.
- **Operators who need OAuth for claude.ai** without building an authorization
  server. bundlemcp ships one, and federates human login to whatever OIDC
  provider you already have.
- **Platform builders** who need a bundling core with a real management API, a
  metering hook for billing, and identity propagation to upstream servers.

## What it is not

- Not an MCP server marketplace, not an identity provider, not a billing
  system. Those belong to an application layer built on top.
- Not a transport bridge. Upstreams must speak Streamable HTTP. stdio servers
  run behind a small sidecar, see [stdio servers behind a sidecar](/connect/stdio-sidecar).
- Not multi-tenant. A deployment is one shared workspace where every admin
  sees and manages everything.

## Why a gateway at all

Connecting a client directly to each MCP server works until you have more than
a couple of servers, more than one kind of client, or more than one user. Then
you need a place to:

- decide **which tools** each client sees, and under which names;
- give claude.ai the **OAuth discovery surface** it requires, while a cron job
  uses an API key against the same tools;
- work around client quirks, such as ChatGPT refusing write tools, without
  changing the servers;
- know **who called what**, and optionally charge for it;
- pass the caller's identity to upstream servers that keep per-user state.

bundlemcp centralises all of that, and keeps its own state out of process
memory so that restarts and additional replicas never break a session.

## Where to go next

- [Quickstart](/guide/quickstart) brings up the full stack with Docker Compose
  in a few minutes.
- [Core concepts](/guide/concepts) explains servers, bundles, endpoints,
  profiles and identity in more depth.
- [Production deployment](/self-hosting/deploy) covers public URLs, reverse
  proxies, upgrades and backups.
