---
title: "MCP sessions: what they were, and why the protocol dropped them"
description: Why an AI assistant can lose its tools when a server restarts, what the July 2026 version of MCP changed about it, and what to check in your own setup.
date: 2026-11-30
author: Marius Högger
draft: true
---

AI assistants such as Claude or ChatGPT can do more than chat. They can look up a ticket in your issue tracker, read a
file or query a database. They reach these tools through MCP, the Model Context Protocol: an open standard for how an
assistant (the **client**) talks to a program that offers tools (the **server**).

Over the web, an MCP connection used to start with a check-in. The assistant introduced itself, the server usually
answered with a session ID, and from then on the assistant sent that ID with every request. That ID is the
**session**. Most users never saw it, but it explains a failure many have seen.

Say your assistant uses a tool server for your tickets, and someone restarts that server to install an update. It is
back within seconds, but it has forgotten every session ID it handed out. The next time the assistant asks it for a
ticket, it still sends its old ID. Some assistants notice the answer, check in again and carry on. Others keep failing
until the assistant itself is restarted.

In July 2026, a new version of MCP removed sessions altogether. MCP names its versions after their release date, so this
one is called [2026-07-28](https://modelcontextprotocol.io/specification/versioning). This post explains what sessions
were, why they caused failures like this one, what replaced them, and what to check if your tools still use them. A
disclosure: I maintain bundlemcp, an open-source MCP gateway that began as a rewrite of metamcp. Both come up later; the
rest of the post does not depend on them.

## What a session was

A session worked like a cloakroom ticket. You hand in your coat, get a ticket, and show it every time you come back. The
ticket only works at that one counter, because the coat rack is behind it. If someone clears the rack at the end of a
shift, your ticket is worthless. The right answer is then "we don't have that ticket", which means: check in again.

In MCP's HTTP transport, called Streamable HTTP (the revisions 2025-03-26, 2025-06-18 and 2025-11-25), the **client**,
meaning the assistant or AI app, opens with an `initialize` request. The **server** may hand back a session ID in the
`Mcp-Session-Id` header. That is the ticket, and the client sends it on every later request. The
[spec](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports) is strict about what happens next:
when the server no longer knows a session, it must answer `404 Not Found`, and the client must "start a new session by
sending a new InitializeRequest". A request with no ticket at all gets `400 Bad Request`. So 404 means "I don't know
this ticket" and 400 means "you sent no ticket".

The coat was mostly the settings agreed at check-in, such as the protocol version and what each side supports, not
your files or chats. The counter is one running copy of the server, and the rack is where it keeps its sessions. The
rack could have been shared between several copies: the
[proposal that introduced this transport](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/206)
allowed it. Most servers kept the rack behind one counter anyway, because that was the default, and that default is
where the trouble started.

## Why it became a problem

The default came from the official TypeScript SDK, the library many servers are built on. It keeps sessions in the
memory of one running program and "provides no public API for reconstructing a session on a different node", as
[SEP-2567](https://modelcontextprotocol.io/seps/2567-sessionless-mcp), one of the proposals that later changed MCP, puts
it. A single copy loses every session when it restarts, as in the opening. A busy server runs as several copies behind
a load balancer, which spreads incoming requests across them. Then every request with a given ticket has to reach the
copy that issued it, which is called sticky routing.
[NGINX Plus](https://community.f5.com/kb/technicalarticles/mcp-session-affinity-with-f5-nginx-plus/341961), for example,
can pin requests by session ID. [SEP-2575](https://modelcontextprotocol.io/seps/2575) calls these "complex and fragile
solutions like sticky sessions", and adds: "if the specific server instance handling a client session fails, that
session state is lost."

The 404 rule was meant to make that loss cheap, but only if the client checks in again. The assistant in the opening
did not. The official SDKs also ship a client part, which apps and scripts use to talk to servers, so they appear below
too. One more thing matters for one row: some servers answer a ticket they don't know with 400 instead of the 404 the
spec requires. This is the reported behaviour I could find a source for, as of November 2026. These are public
reports, not my own tests:

| Client | After a 404 for its session | Source |
|---|---|---|
| Claude Code | Checks in again | [Anthropic maintainer, 2026-05-23](https://github.com/anthropics/claude-code/issues/55970) |
| VS Code | Checks in again on its next request | [VS Code team, 2025-07-08](https://github.com/microsoft/vscode/issues/253854) |
| Cursor IDE (the editor) | Checks in again, as the spec requires | [Cursor staff, 2026-05-20](https://forum.cursor.com/t/cursor-mcp-client-does-not-restart-session-on-404-session-not-found/161132) |
| Cursor CLI (the terminal tool) | Does not check in again | Same thread, still reported 2026-09-25 |
| claude.ai | Checks in again; stays stuck if the server answers 400 instead | [A user's own diagnosis, 2026-04-15](https://github.com/anthropics/claude-code/issues/48557) |
| TypeScript SDK client | Does not check in again | [#1708](https://github.com/modelcontextprotocol/typescript-sdk/issues/1708) and [#3056](https://github.com/modelcontextprotocol/typescript-sdk/issues/3056), open as of 2026-11-25 |
| Python SDK client | Gives up with an error | [#1676](https://github.com/modelcontextprotocol/python-sdk/issues/1676), open as of 2026-11-25 |
| ChatGPT, Claude Desktop | Unknown | No source found |

The SDK rows matter beyond the SDKs, because many clients and gateways are built on them. The claude.ai row shows a
second trap, on the server side: a server that has lost a session should answer 404, "I don't know this ticket". One
that answers 400, "you sent no ticket", although the ticket was there, leaves claude.ai stuck, because only the 404
tells it to check in again.

Chat users often barely notice. Users report that the
[ChatGPT connector](https://community.openai.com/t/connector-tool-calls-generating-fresh-mcp-session-each-invocation/1364975)
and [claude.ai chat](https://github.com/anthropics/claude-ai-mcp/issues/583) open a fresh session before nearly every
tool call. The damage concentrates on IDE and agent clients that keep one session for as long as they run, and on
gateways: a **gateway** sits between the assistant and many tool servers and holds a ticket at each of them. SEP-2567
calls gateways "the hardest-hit category".

[metamcp](https://github.com/metatool-ai/metamcp) shows how this plays out. It is a widely used open-source gateway that
does a lot this post doesn't cover, such as running local servers and offering OpenAPI endpoints. Like any gateway, it
sits on both sides: a server to the assistants, and a client holding a ticket at each server behind it. As of November
2026 it keeps its sessions in the memory of its process, in a
[process-local map](https://github.com/metatool-ai/metamcp/blob/05818ec2767b946f98d280ae9cefa401f0362d62/apps/backend/src/lib/session-lifetime-manager.ts),
the TypeScript SDK's standard pattern. Towards assistants that works as the spec intends: it answers unknown sessions
with a correct 404. The trouble was on the other side, where metamcp is the client. In
[PR #283](https://github.com/metatool-ai/metamcp/pull/283), one operator reported "~8k failed tool calls over a few
hours" after a server behind metamcp restarted and forgot metamcp's ticket. metamcp kept sending the old ticket instead
of checking in again, until metamcp itself was restarted. The fix was merged in June 2026 and covers the tool-call path;
it is not yet in a tagged release. That is not carelessness. It is what the SDK's defaults lead to: sessions that live
in one process's memory, and a client that does not check in again on its own.

## What replaced it

The [2026-07-28 transport](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http)
says it in four words: "Removal of protocol-level sessions." The
[official announcement](https://blog.modelcontextprotocol.io/posts/2026-07-28/) gives the reason: "Any request can now
land on any server instance behind a plain round-robin load balancer without needing shared storage." In cloakroom
terms: the load balancer no longer has to send each ticket to the one counter that holds its coat. It can hand requests
to the copies in turn, which is what round-robin means, and the copies don't need to share a rack.

There is no ticket and no rack any more. You bring your coat, the check-in settings, to whichever counter you reach.

- **Each request describes itself.** A field called `_meta` carries the protocol version and what the client supports
  (its capabilities), on every request. Headers repeat the key values, so anything in front of the server can read
  them without opening the body. Servers "MUST NOT infer capabilities from prior requests", because the next request
  may reach a different copy.
- **A server's question becomes a round trip.** When a server needs something from the user mid-call, for example a
  confirmation, it returns a result asking for it, and the client sends the original call again with the answer
  attached.
- **Data a tool needs across calls becomes a handle.** SEP-2567's own example is a shop: `create_basket()` returns a
  `basket_id`, and the assistant passes it into later calls as an ordinary argument. Any copy of the server can answer
  those calls. The protocol itself no longer needs shared storage; only the tool's own data, here the basket, has to
  live somewhere all copies can reach, as any web shop's data already does. The ID is not a password: a server that
  checks who is calling still does so on every call, whatever ID it is given.

<!-- DIAGRAM: Before/after. Left, session-based: client -> load balancer pinned to one of three server copies, which
holds the session in memory; a restarted copy answers "404, check in again". Right, 2026-07-28: client -> plain
round-robin load balancer -> any of three copies; each request carries _meta (version, capabilities) and, where needed,
a basket_id. -->

Put together, MCP is now stateless by default: a server no longer has to remember anything about a client from one
request to the next. [Cloudflare's summary](https://blog.cloudflare.com/mcp-v2/) puts it in one line: "There is no
protocol session to store." The word that matters is *protocol*: SEP-2575 itself says MCP is not stateless entirely,
and state that a task really needs, like the basket, is kept by the tool.

## The in-between year

The major official SDKs shipped 2026-07-28 support on release day, some
[in beta](https://developers.googleblog.com/scaling-ai-agent-infrastructure-with-the-mcp-stateless-updates/). Clients
are slower. [Zuplo's compatibility matrix](https://zuplo.com/learn/mcp/compatibility), last checked for clients on
2026-07-31, lists Claude's surfaces as "initialize era" and VS Code at 2025-11-25.
[Cursor staff wrote on 2026-09-21](https://forum.cursor.com/t/mcp-client-cannot-connect-to-modern-only-2026-07-28-streamable-http-servers-legacy-initialize-rejected/172536)
that its client "currently speaks the 2025-11-25 revision and earlier", adding "No timeline at the moment!" From these
data points, many deployed clients still open with `initialize`, and the spec expects that: a server that must serve
older clients keeps implementing the old revision too.

So a gateway in the middle has to serve both kinds on one URL. [bundlemcp](https://github.com/wingfold-ai/bundlemcp),
the gateway I maintain, is one way to do it. It is a v0.4 public preview and speaks Streamable HTTP only. It looks at
each request: one that describes itself in the new style is stored nowhere and gets no session ID. A session-based
request loads its session from Valkey, a small key-value store that every copy of the gateway can reach, so another
copy, or the same one after a restart, continues it. In cloakroom terms, the rack is shared. As long as Valkey keeps its
data, the gateway answers 404 only for a session that has really expired, not because of a restart. Its own tickets at
the servers behind it are kept in Valkey too.

Here is that on bundlemcp's local Docker Compose stack, the setup from its
[quickstart](https://github.com/wingfold-ai/bundlemcp#quickstart):

```sh
# Start the stack (repo root)
docker compose -f deploy/docker-compose.yml up -d --wait

# Check in: open a session on the demo endpoint (it serves the stack's echo server) with the stack's dev key
KEY=bmcp_sk_devservicekey000000000000000000000000
SID=$(curl -si http://localhost:8000/demo/mcp \
  -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"demo","version":"0"}}}' \
  | awk 'tolower($1)=="mcp-session-id:" {print $2}' | tr -d '\r')

# Restart the gateway and wait until it reports ready again
docker compose -f deploy/docker-compose.yml restart gateway
docker compose -f deploy/docker-compose.yml up -d --no-deps --wait gateway

# Same ticket, no new initialize
curl -s http://localhost:8000/demo/mcp -H "Authorization: Bearer $KEY" -H "Mcp-Session-Id: $SID" \
  -H 'MCP-Protocol-Version: 2025-11-25' -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
```

The last call answers with the four tools behind the demo endpoint, `echo__countdown`, `echo__echo`, `echo__reverse`
and `echo__shout`, on the session opened before the restart. A ticket the gateway never issued still gets a 404.

The limits of that guarantee, stated plainly:

- **Sessions survive a restart; single requests may not.** The
  [integration tests](https://github.com/wingfold-ai/bundlemcp/blob/main/tests/integration/test_replicas.py) run two
  gateway copies and restart both, and also update both to a new version, while clients send a request every 50 ms.
  For each request they accept an answer or a 503 ("try again"), and afterwards they require every session to work
  without checking in again. They do not show that no request was refused.
- **One copy means a gap.** The default stack runs one gateway. While it restarts, requests fail for a few seconds,
  though it lets running calls finish first.
- **Open streams drop.** A session-based client can keep a connection open for the server to push messages on. After a
  restart, the client has to open it again.
- **If Valkey loses its data, sessions are lost.** Clients get an ordinary 404, which only helps clients that act on a
  404. That brings us back to the table.

## What to check in your own setup

If you build or run MCP clients, servers or gateways, check these five things:

1. **Which revision your clients speak.** If they still open with `initialize`, sessions are still your problem.
2. **How they react to a lost session.** Restart your server while a client you depend on is connected, then make
   another tool call.
3. **The status code.** Answer exactly 404 for an unknown or expired session ID, because only 404 tells a client to
   check in again. Use 400 only when the ID is missing, and never 500.
4. **The connection behind your gateway.** If you run one, restart a server behind it and check that the next call
   through the gateway works.
5. **Your SDK client.** If you build on the TypeScript or Python SDK client and still use sessions, it will not check
   in again for you (open issues as of 2026-11-25). Handle the 404 yourself, or move to 2026-07-28.

Surviving a restart used to be something each server and gateway had to build for itself. With 2026-07-28, any copy
can answer any request by design. Until your clients speak that revision, the cloakroom is still open, and the
session-based path still has to survive a restart.

## Sources

- MCP specification: [2025-11-25 transports](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports),
  [2026-07-28 Streamable HTTP](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http),
  [versioning](https://modelcontextprotocol.io/specification/versioning)
- [MCP blog: the 2026-07-28 release](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
- [SEP-2575: Make MCP Stateless](https://modelcontextprotocol.io/seps/2575),
  [SEP-2567: Sessionless MCP via Explicit State Handles](https://modelcontextprotocol.io/seps/2567-sessionless-mcp),
  [PR #206: Streamable HTTP](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/206)
- [Cloudflare: MCP v2](https://blog.cloudflare.com/mcp-v2/),
  [Google Developers Blog on the stateless update](https://developers.googleblog.com/scaling-ai-agent-infrastructure-with-the-mcp-stateless-updates/),
  [Zuplo MCP compatibility matrix](https://zuplo.com/learn/mcp/compatibility),
  [NGINX Plus MCP session affinity](https://community.f5.com/kb/technicalarticles/mcp-session-affinity-with-f5-nginx-plus/341961)
- Client behaviour: [Claude Code #55970](https://github.com/anthropics/claude-code/issues/55970),
  [claude-code #48557](https://github.com/anthropics/claude-code/issues/48557),
  [claude-ai-mcp #583](https://github.com/anthropics/claude-ai-mcp/issues/583),
  [VS Code #253854](https://github.com/microsoft/vscode/issues/253854),
  [Cursor forum (404)](https://forum.cursor.com/t/cursor-mcp-client-does-not-restart-session-on-404-session-not-found/161132),
  [Cursor forum (2026-07-28)](https://forum.cursor.com/t/mcp-client-cannot-connect-to-modern-only-2026-07-28-streamable-http-servers-legacy-initialize-rejected/172536),
  [OpenAI community](https://community.openai.com/t/connector-tool-calls-generating-fresh-mcp-session-each-invocation/1364975),
  [TypeScript SDK #1708](https://github.com/modelcontextprotocol/typescript-sdk/issues/1708),
  [Python SDK #1676](https://github.com/modelcontextprotocol/python-sdk/issues/1676)
- metamcp: [repository](https://github.com/metatool-ai/metamcp),
  [session lifetime manager](https://github.com/metatool-ai/metamcp/blob/05818ec2767b946f98d280ae9cefa401f0362d62/apps/backend/src/lib/session-lifetime-manager.ts),
  [releases](https://github.com/metatool-ai/metamcp/releases),
  [PR #283](https://github.com/metatool-ai/metamcp/pull/283)
