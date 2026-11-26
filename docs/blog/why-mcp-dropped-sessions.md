---
title: "MCP sessions: what they were and why the protocol dropped them"
description: How a server restart can cost an AI assistant its tools, what the July 2026 version of MCP changed about that and what to check in your own setup.
date: 2026-11-30
author: Marius Högger
draft: true
---

<script setup>
import McpRevisionTimeline from "./components/McpRevisionTimeline.vue";
</script>

AI assistants such as Claude or ChatGPT can look up a ticket in your issue tracker, read a file or query a database.
They reach these tools through MCP, the Model Context Protocol, an open standard for how an assistant talks to a program
that offers tools. The assistant is called the client and the program the server. Because every assistant and every
tool server speak the same protocol, one tool server works with all of them.

Over the web, an MCP connection used to start with a check-in. The client sent an `initialize` request that named its
protocol version and the features it supports. The server usually answered with a session ID in the `Mcp-Session-Id`
header. The client then sent that ID with every request, so the server did not need the version and features again.

The agreement from this check-in is the session. The server remembers it for as long as the client keeps working with
it, and ties more to it over time: an open channel on which it can send the client notices such as "my tools changed",
and sometimes a tool list it adapted to what the client did earlier in the session. The session ID is only the claim
ticket. It is worth something as long as the server still holds what the ticket stands for.

<LikeC4Diagram view="sessionCheckIn" />

In July 2026 a new version of MCP removed sessions from the protocol. MCP names its versions after their release date,
so this one is called [2026-07-28](https://modelcontextprotocol.io/specification/versioning). The proposals behind the
change give two reasons. A session ties each client to the one running copy of a server that holds it, which makes a
busy server hard to spread across several copies; [SEP-2575](https://modelcontextprotocol.io/seps/2575), the proposal
that removed sessions, calls that "the most critical issue". And
[SEP-2567](https://modelcontextprotocol.io/seps/2567-sessionless-mcp), a second proposal, found that "after more than a
year in the spec, sessions have not converged on a consistent meaning across clients." Users know the result as a
familiar failure: a tool server restarts for an update, and an assistant that was connected to it loses its tools until
the assistant is restarted too.

## What a session was

Sessions belong to Streamable HTTP, MCP's transport over HTTP, in the revisions 2025-03-26, 2025-06-18 and 2025-11-25.
The server keeps each session in its own storage, which makes the ID worthless the moment the server forgets it.

For that moment the [spec](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports) has a strict rule.
A server that no longer knows a session ID must answer `404 Not Found`. The client must then "start a new session by
sending a new InitializeRequest". A request that carries no session ID at all gets `400 Bad Request` instead. The two
codes let a client tell a lost session from a broken request: only the 404 means that checking in again will help.

A server that few people use runs as one program. A busy one runs as several identical copies of that program, often on
several machines. In front of them sits a load balancer, a program that spreads incoming requests across the copies.
That way a service handles more users by adding copies, and keeps running when one copy fails. The catch is that what
one copy remembers, the others do not know.

For sessions that leaves two ways out. The copies can share one session storage, so that any copy can look up any
session; the
[proposal that introduced the transport](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/206)
allowed exactly that. Or the load balancer sends every request of a session to the copy that issued it, which is called
sticky routing. Shared storage works, but few servers used it. The official TypeScript SDK, the library many servers are
built on, keeps sessions in the memory of one running program by default, and SEP-2567 notes that it "provides no public
API for reconstructing a session on a different node". The spec left room to share sessions. The most common library
offered no supported way to do it, and most servers kept its default.

## Why it became a problem

A server can lose a session in two common ways. The first is a restart. Memory is cleared when a program stops, so a
server that keeps its sessions there loses all of them every time, for example when someone installs an update.

The second comes with growth. Servers that run as several copies mostly chose sticky routing over shared storage.
[NGINX Plus](https://community.f5.com/kb/technicalarticles/mcp-session-affinity-with-f5-nginx-plus/341961), for example,
can route requests by session ID. Each session then lives on one copy only. SEP-2575 counts sticky routing among the
"complex and fragile solutions like sticky sessions" and names the price: "if the specific server instance handling a
client session fails, that session state is lost."

Both ways end in the same place. The server is back within seconds, but the client still holds an ID the server no
longer knows. What happens next depends on the client. The 404 rule turns the loss into one extra request, provided the
client follows it. Public reports up to November 2026 show that several widely used clients do. Claude Code checks in
again after a 404, as an
[Anthropic maintainer wrote in May 2026](https://github.com/anthropics/claude-code/issues/55970). VS Code does so on its
next request, according to the [VS Code team in July 2025](https://github.com/microsoft/vscode/issues/253854). The
Cursor editor follows the spec as well, according to
[Cursor staff in May 2026](https://forum.cursor.com/t/cursor-mcp-client-does-not-restart-session-on-404-session-not-found/161132).
For people who use these clients, a server restart costs one request they never see.

<LikeC4Diagram view="sessionLost" />

Other clients keep failing. According to the same Cursor thread, the Cursor command-line tool still did not check in
again in September 2026, so its users have to restart it after a server restart. The client part of the official
TypeScript SDK does not check in again either
([#1708](https://github.com/modelcontextprotocol/typescript-sdk/issues/1708),
[#3056](https://github.com/modelcontextprotocol/typescript-sdk/issues/3056)). The Python SDK client stops with an error
([#1676](https://github.com/modelcontextprotocol/python-sdk/issues/1676)). All three issues were open on 25 November
2026. Many apps and gateways talk to servers through these SDK clients, so they inherit the failure unless their
developers handle the 404 themselves. No public source covers ChatGPT or Claude Desktop.

claude.ai shows that a server can cause the failure too. It checks in again after a 404. In April 2026 a user
[found it stuck](https://github.com/anthropics/claude-code/issues/48557) on a server that answered a lost session with
400. claude.ai only starts over on a 404, so it kept failing. A server that picks the wrong status code breaks even a
client that follows the spec.

In a chat window this rarely shows. Users report that the
[ChatGPT connector](https://community.openai.com/t/connector-tool-calls-generating-fresh-mcp-session-each-invocation/1364975)
and [claude.ai chat](https://github.com/anthropics/claude-ai-mcp/issues/583) open a new session before nearly every tool
call, which leaves a session no time to go stale. The failures concentrate on clients that keep one session for as long
as they run, such as editors and coding agents.

A new session for every call is no fix, though. Each one repeats the check-in and fetches the tool list again, SEP-2567
notes, "even when the server's tool set is fixed at build time and never changes, which is the common case". For an
assistant that starts many short-lived helper agents, that overhead "can exceed the protocol traffic of the actual tool
calls." Starting over also throws away what a session could build up. Take a database server as an example: within a
session it could offer a `query` tool only after the client had called `connect_database`. A client that starts a new
session before every call never gets to see that `query` tool.

Gateways are hit hardest. A gateway sits between the assistant and many tool servers and offers all their tools through
one connection. For that it holds a session at each server behind it, so a restart of any one of them can break calls
through the gateway. SEP-2567 calls gateways "the hardest-hit category".

[metamcp](https://github.com/metatool-ai/metamcp) shows how this plays out. It is a widely used open-source gateway that
also runs local servers and offers OpenAPI endpoints. As of November 2026 metamcp keeps its sessions in a
[map in its process memory](https://github.com/metatool-ai/metamcp/blob/05818ec2767b946f98d280ae9cefa401f0362d62/apps/backend/src/lib/session-lifetime-manager.ts),
the SDK's standard pattern. Towards assistants it answers an unknown session with the 404 the spec requires, so clients
that follow the rule recover.

The trouble was on the other side of the gateway: the connection from metamcp to the servers behind it. On that
connection metamcp is the client, and it holds the session IDs. In
[PR #283](https://github.com/metatool-ai/metamcp/pull/283) an operator reported "~8k failed tool calls over a few hours"
after a server behind metamcp restarted. metamcp kept sending the forgotten session ID until metamcp itself was
restarted. For all that time the tools of that server stayed unreachable, although the server itself was running again.
The fix for the tool-call path was merged in June 2026 and is in no
[tagged release](https://github.com/metatool-ai/metamcp/releases) yet. Both halves of the problem come from the SDK's
defaults: sessions in the memory of one process and a client that does not check in again on its own. Any gateway built
on those defaults has the same weakness.

## What replaced it

The [2026-07-28 transport](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http)
lists the change as "Removal of protocol-level sessions." The
[official announcement](https://blog.modelcontextprotocol.io/posts/2026-07-28/) puts the goal in one sentence: "Any
request can now land on any server instance behind a plain round-robin load balancer without needing shared storage."
Round-robin means the load balancer hands requests to the copies in turn, without looking inside them. Sticky routing
and shared session storage become unnecessary, because no copy holds anything the others lack.

For that, each request carries what the check-in used to settle. A field called `_meta` holds the protocol version and
the features the client supports, its capabilities. Headers repeat the key values, so a proxy can route a request
without parsing its body. Servers "MUST NOT infer capabilities from prior requests", since the previous request may have
reached a different copy.

The other direction changed too. A client that wants to know up front what a server offers can call `server/discover`,
which returns the versions and capabilities the server supports; it may also skip that and call a tool straight away.
A tool list now comes with a time to live (`ttlMs`), so a client can reuse it instead of fetching it on every
connection. For change notices, a client opens one long-lived request, `subscriptions/listen`, and names what it wants
to hear about. When the tools change, the server sends `notifications/tools/list_changed` on that request, and the
client fetches the list again.

A server can still change its tools over time, and it may show different tools to different callers, based on the
credentials each request carries. What it may no longer do is change the list because of what a client did before. The
[tools spec](https://modelcontextprotocol.io/specification/2026-07-28/server/tools) says the list "MUST NOT vary
per-connection or as a side effect of other requests on the connection." The reason follows from the rest of the
change. Without a session there is no connection a changed list could belong to, and the next request may reach a copy
that never saw the earlier one. Credentials are allowed to matter, the spec explains, because they are "per-request
input, not connection state": they arrive with every request. A list that depends only on the request is also one a
client can safely cache.

The rule has a cost. It ends the database example from earlier, in which `query` appeared only after a
`connect_database` call. A server can no longer grow its tool list as a conversation explores. SEP-2567 rewrites that
example with `query` and `list_tables` tools that are always offered and take a `connection_id`. What changes during a
conversation now has to live inside tools that stay fixed. Taken to its end, a server could offer one tool that lists
the actions currently available, with an answer that changes over time, and a second tool that runs one of those
actions by name with free-form arguments. Exploring stays possible. It just no longer happens at the protocol level,
and actions reached this way lose what a listed tool has: a schema the client knows in advance.

A server that needs input from the user during a call, such as a confirmation, now returns a result that asks for it.
The client sends the original call again with the answer attached. Because the second call carries everything, any copy
can finish it.

Data a tool needs across calls becomes an argument. SEP-2567's example is a shop: `create_basket()` returns a
`basket_id` that the assistant passes into every later call about that basket. Any copy can answer those calls, as long
as the basket lives in storage all copies reach, as a web shop's data already does. The ID opens nothing by itself. A
server that checks who is calling still does so on every call, whatever ID it receives.

A `basket_id` does the job a session ID did: it names state the server keeps. The difference is where it lives. A
session ID was part of the protocol, so every client and every server had to handle it, even a server with nothing to
remember. A `basket_id` is an ordinary tool argument. Only a tool that needs state introduces one, and the assistant
sees it like any other value. By default a server keeps no state, and where it does, the state is in plain sight.

[Cloudflare](https://blog.cloudflare.com/mcp-v2/) sums it up: "There is no protocol session to store." The protocol
keeps nothing between requests, but MCP is not stateless as a whole. Asked whether it now is, SEP-2575 answers: "Not
entirely (hence 'by default')." State that a task needs, like the basket in the shop example, stays with the tool, whose
developers decide where to store it.

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

<McpRevisionTimeline />

A gateway can take that work off the servers. [bundlemcp](https://github.com/wingfold-ai/bundlemcp), a v0.4 public
preview that speaks Streamable HTTP only, speaks both revisions, towards the assistants and towards the servers behind
it, and translates between them where the features match. A server that only implements the sessionless 2026-07-28
revision can then serve a client that only knows sessions, and the other way round. The sessions such a client needs
live in the gateway, not in each server.

<LikeC4Diagram view="sessionTranslation" />

That moves the restart problem to the gateway, and a session storage alone does not solve it. If the storage sits in
the memory of the program, as with the SDK's default, a restart empties it. The storage has to live outside the
program, in a database that every copy can reach and that keeps running while the copies restart.

bundlemcp decides per request. A request that carries `_meta` in the new style is stored nowhere and gets no session ID.
A session-based request loads its session from a session storage outside the gateway, which every copy reads. Any copy
can therefore continue a session, including the same copy after a restart. bundlemcp keeps
the session IDs it holds at the servers behind it in the same storage, so a gateway restart costs none of those either.
A client gets a 404 only for a session that has really expired.

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

Three limits remain. The default stack runs a single gateway copy, so new requests fail for a few seconds while it
restarts; calls already running finish first. A client that keeps a connection open to receive notices from the server
has to open it again after the restart. And if the session storage itself loses its data, every session is gone, and
clients get an ordinary 404, which helps only the clients that act on it.

## What the change says about MCP

The most striking thing about this change is its cause. The session design was not broken. The spec allowed shared
storage and had a clear rule for lost sessions. The failures came from the implementations: an SDK whose defaults keep
sessions in the memory of one program, and clients, the SDK's own among them, that ignore the 404. MCP changed the
protocol because too few implementations used it correctly.

The same weakness shows in how much of MCP is optional. A client may or may not let a server ask the user a question,
use the client's model or send it notices. That openness undercuts the point of a protocol: a server cannot rely on a
client having the features it needs, so it has to design for the smallest set every client supports.

The change is still the right one. MCP spread widely, but mostly in its simplest form. When a protocol is adopted
broadly and shallowly, its complexity is too high, and lowering it is a valid answer. Nothing essential is lost either.
A server can still keep state, as the shop example from SEP-2567 shows with its `basket_id`. It has to say so in its
tools, and it carries the complexity that comes with that, above all once it runs as several copies.

## What to check in your own setup

Find out which revision your clients speak. A client that opens with `initialize` still depends on sessions, so
everything above applies to it. To see how it handles a lost session, restart your server while the client is connected
and make another tool call. If the call fails until you restart the client, your users will see the same after every
update.

On the server side, answer an unknown or expired session ID with exactly 404. Only a 404 tells a client to check in
again, as the claude.ai case above shows. Use 400 only when the ID is missing and never answer with 500.

If you run a gateway, restart a server behind it and check that the next call through the gateway works. If you build
on the TypeScript or Python SDK client and still use sessions, handle the 404 in your own code, because neither client
did so on 25 November 2026. Moving to 2026-07-28 removes the problem, since there is no session left to lose.

Your servers do not have to wait for your clients. Behind a gateway that translates between the revisions, such as
bundlemcp, a server can move to 2026-07-28 now, while clients that still need sessions keep working through the
gateway.
