---
title: "MCP sessions: what they were and why the protocol dropped them"
description: How a server restart can cost an AI assistant its tools, what the July 2026 version of MCP changed about that and what to check in your own setup.
date: 2026-11-30
author: Marius Högger
draft: true
---

AI assistants such as Claude or ChatGPT can look up a ticket in your issue tracker, read a file or query a database.
They reach these tools through MCP, the Model Context Protocol, an open standard for how an assistant talks to a program
that offers tools. The assistant is called the client and the program the server. Because every assistant and every
tool server speak the same protocol, one tool server works with all of them.

Over the web, an MCP connection used to start with a check-in. The client sent an `initialize` request that named its
protocol version and the features it supports. The server usually answered with a session ID in the `Mcp-Session-Id`
header. The client then sent that ID with every request, so the server did not need the version and features again.

In July 2026 a new version of MCP removed these sessions. MCP names its versions after their release date, so this one
is called [2026-07-28](https://modelcontextprotocol.io/specification/versioning). Sessions were behind a failure that
users of tool servers know: after a server restart, some assistants lose its tools until they are restarted themselves.

## What a session was

Sessions belong to Streamable HTTP, MCP's transport over HTTP, in the revisions 2025-03-26, 2025-06-18 and 2025-11-25.
The session ID stands for the settings agreed at check-in. The server keeps those settings in its own storage, which
makes the ID worthless the moment the server forgets them.

For that moment the [spec](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports) has a strict rule.
A server that no longer knows a session ID must answer `404 Not Found`. The client must then "start a new session by
sending a new InitializeRequest". A request that carries no session ID at all gets `400 Bad Request` instead. The two
codes let a client tell a lost session from a broken request: only the 404 means that checking in again will help.

The [proposal that introduced the transport](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/206)
allowed several copies of a server to share their session storage. Most servers kept sessions in the memory of one
running program anyway, because the official TypeScript SDK, the library many servers are built on, does that by
default. [SEP-2567](https://modelcontextprotocol.io/seps/2567-sessionless-mcp), one of the proposals that later changed
MCP, notes that the SDK "provides no public API for reconstructing a session on a different node". A server built on
the SDK has no supported way to hand a session to another copy of itself.

## Why it became a problem

Memory is cleared when a program stops. A server that keeps its sessions there loses all of them on every restart, for
example when someone installs an update. The server is back within seconds, but every client still holds an ID the
server no longer knows.

A busy server has a second problem. It runs as several copies behind a load balancer, a program that spreads incoming
requests across them. Only the copy that issued a session ID knows it, so every request with that ID has to reach that
copy. This is called sticky routing.
[NGINX Plus](https://community.f5.com/kb/technicalarticles/mcp-session-affinity-with-f5-nginx-plus/341961), for
example, can route requests by session ID. [SEP-2575](https://modelcontextprotocol.io/seps/2575) counts it among the
"complex and fragile solutions like sticky sessions" and names the price: "if the specific server instance handling a
client session fails, that session state is lost."

The 404 rule turns such a loss into one extra request, provided the client follows it. Public reports up to November
2026 show that several widely used clients do. Claude Code checks in again after a 404, as an
[Anthropic maintainer wrote in May 2026](https://github.com/anthropics/claude-code/issues/55970). VS Code does so on
its next request, according to the [VS Code team in July 2025](https://github.com/microsoft/vscode/issues/253854). The
Cursor editor follows the spec as well, according to
[Cursor staff in May 2026](https://forum.cursor.com/t/cursor-mcp-client-does-not-restart-session-on-404-session-not-found/161132).
For people who use these clients, a server restart costs one request they never see.

Other clients keep failing. According to the same Cursor thread, the Cursor command-line tool still did not check in
again in September 2026, so its users have to restart it after a server restart. The client part of the official
TypeScript SDK does not check in again either
([#1708](https://github.com/modelcontextprotocol/typescript-sdk/issues/1708),
[#3056](https://github.com/modelcontextprotocol/typescript-sdk/issues/3056)). The Python SDK client stops with an error
([#1676](https://github.com/modelcontextprotocol/python-sdk/issues/1676)). All three issues were open on 25 November
2026. Many apps and gateways talk to servers through these SDK clients, so they inherit the failure unless their
developers handle the 404 themselves. I found no source for ChatGPT or Claude Desktop.

claude.ai shows that a server can cause the failure too. It checks in again after a 404. In April 2026 a user
[found it stuck](https://github.com/anthropics/claude-code/issues/48557) on a server that answered a lost session with
400. claude.ai only starts over on a 404, so it kept failing. A server that picks the wrong status code breaks even a
client that follows the spec.

In a chat window this rarely shows. Users report that the
[ChatGPT connector](https://community.openai.com/t/connector-tool-calls-generating-fresh-mcp-session-each-invocation/1364975)
and [claude.ai chat](https://github.com/anthropics/claude-ai-mcp/issues/583) open a new session before nearly every tool
call, which leaves a session no time to go stale. The failures concentrate on clients that keep one session for as long
as they run, such as editors and coding agents.

Gateways are hit hardest. A gateway sits between the assistant and many tool servers and offers all their tools through
one connection. For that it holds a session at each server behind it, so a restart of any one of them can break calls
through the gateway. SEP-2567 calls gateways "the hardest-hit category".

[metamcp](https://github.com/metatool-ai/metamcp) shows how this plays out. It is a widely used open-source gateway that
also runs local servers and offers OpenAPI endpoints. A disclosure: bundlemcp, the gateway I maintain, began as a
rewrite of metamcp's bundling core. As of November 2026 metamcp keeps its sessions in a
[map in its process memory](https://github.com/metatool-ai/metamcp/blob/05818ec2767b946f98d280ae9cefa401f0362d62/apps/backend/src/lib/session-lifetime-manager.ts),
the SDK's standard pattern. Towards assistants it answers an unknown session with the 404 the spec requires, so clients
that follow the rule recover.

The trouble was behind it, where metamcp is the client. In [PR #283](https://github.com/metatool-ai/metamcp/pull/283)
an operator reported "~8k failed tool calls over a few hours" after a server behind metamcp restarted. metamcp kept
sending the forgotten session ID until metamcp itself was restarted. For all that time the tools of that server stayed
unreachable, although the server itself was running again. The fix for the tool-call path was merged in June 2026 and
is in no [tagged release](https://github.com/metatool-ai/metamcp/releases) yet. Both halves of the problem come from the
SDK's defaults: sessions in the memory of one process and a client that does not check in again on its own. Any gateway
built on those defaults has the same weakness.

## What replaced it

The [2026-07-28 transport](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http)
lists the change as "Removal of protocol-level sessions." The
[official announcement](https://blog.modelcontextprotocol.io/posts/2026-07-28/) gives the reason: "Any request can now
land on any server instance behind a plain round-robin load balancer without needing shared storage." Round-robin means
the load balancer hands requests to the copies in turn, without looking inside them. Sticky routing and shared session
storage become unnecessary, because no copy holds anything the others lack.

For that, each request carries what the check-in used to settle. A field called `_meta` holds the protocol version and
the features the client supports, its capabilities. Headers repeat the key values, so a proxy can route a request
without parsing its body. Servers "MUST NOT infer capabilities from prior requests", since the previous request may have
reached a different copy.

A server that needs input from the user during a call, such as a confirmation, now returns a result that asks for it.
The client sends the original call again with the answer attached. Because the second call carries everything, any copy
can finish it.

Data a tool needs across calls becomes an argument. SEP-2567's example is a shop: `create_basket()` returns a
`basket_id` that the assistant passes into every later call about that basket. Any copy can answer those calls, as long
as the basket lives in storage all copies reach, as a web shop's data already does. The ID opens nothing by itself. A
server that checks who is calling still does so on every call, whatever ID it receives.

[Cloudflare](https://blog.cloudflare.com/mcp-v2/) sums it up: "There is no protocol session to store." The protocol
keeps nothing between requests. State that a task needs, like the basket, stays with the tool, whose developers decide
where to store it.

## The in-between year

The major official SDKs shipped 2026-07-28 support on release day, some
[in beta](https://developers.googleblog.com/scaling-ai-agent-infrastructure-with-the-mcp-stateless-updates/), so
servers can adopt it now. Clients are slower. [Zuplo's compatibility matrix](https://zuplo.com/learn/mcp/compatibility),
last checked for clients on 31 July 2026, lists Claude's apps as "initialize era" and VS Code at 2025-11-25. On 21
September 2026
[Cursor staff wrote](https://forum.cursor.com/t/mcp-client-cannot-connect-to-modern-only-2026-07-28-streamable-http-servers-legacy-initialize-rejected/172536)
that its client "currently speaks the 2025-11-25 revision and earlier" and added: "No timeline at the moment!" A server
that wants to reach these clients has to keep the session-based revision next to the new one, which the spec allows.
Sessions stay a problem for server operators until their clients move.

A gateway has to do the same on one URL. [bundlemcp](https://github.com/wingfold-ai/bundlemcp), a v0.4 public preview
that speaks Streamable HTTP only, decides per request. A request that carries `_meta` in the new style is stored nowhere
and gets no session ID. A session-based request loads its session from Valkey, a key-value store that runs beside the
gateway and that every copy can reach. Any copy can therefore continue a session, including the same copy after a
restart. bundlemcp keeps its own session IDs at the servers behind it in Valkey too, so a gateway restart costs none of
those either. As long as Valkey keeps its data, a client gets a 404 only for a session that has really expired.

You can watch a session survive a restart on the local Docker Compose stack from bundlemcp's
[quickstart](https://github.com/wingfold-ai/bundlemcp#quickstart). The commands open a session, restart the gateway and
reuse the old session ID:

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

# Same session ID, no new initialize
curl -s http://localhost:8000/demo/mcp -H "Authorization: Bearer $KEY" -H "Mcp-Session-Id: $SID" \
  -H 'MCP-Protocol-Version: 2025-11-25' -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
```

The last call answers with the four tools behind the demo endpoint (`echo__countdown`, `echo__echo`, `echo__reverse` and
`echo__shout`) on the session opened before the restart. A session ID the gateway never issued still gets 404, so a
client that sends a wrong ID learns that it has to check in.

The guarantee covers sessions. A single request can still fail during a restart. The
[integration tests](https://github.com/wingfold-ai/bundlemcp/blob/main/tests/integration/test_replicas.py) run two
gateway copies and restart both, then update both to a new version, while clients send a request every 50 ms. For each
request they accept an answer or a 503, which asks the client to retry. Afterwards every session must work without a
new check-in. The tests prove that no session is lost, which is less than proving that no request fails.

The default stack runs a single gateway copy, so requests fail for a few seconds while it restarts, although running
calls finish first. A session-based client that holds a connection open for messages from the server has to reopen it
after a restart. If Valkey loses its data, the sessions are gone. Clients then get an ordinary 404, which helps only the
clients that act on it.

## What to check in your own setup

Find out which revision your clients speak. A client that opens with `initialize` still depends on sessions, so
everything above applies to it. To see how it handles a lost session, restart your server while the client is connected
and make another tool call. If the call fails until you restart the client, your users will see the same after every
update.

On the server side, answer an unknown or expired session ID with exactly 404. Only a 404 tells a client to check in
again, as the claude.ai case shows. Use 400 only when the ID is missing and never answer with 500.

If you run a gateway, restart a server behind it and check that the next call through the gateway works. If you build
on the TypeScript or Python SDK client and still use sessions, handle the 404 in your own code, because neither client
did so on 25 November 2026. Moving to 2026-07-28 removes the problem, since there is no session left to lose.
