---
title: "MCP sessions: what they were and why the protocol dropped them"
description: How a server restart can cost an AI assistant its tools, what the July 2026 version of MCP changed about that and what to check in your own setup.
date: 2026-11-30
author: Marius Högger
draft: true
---

AI assistants such as Claude or ChatGPT can look up a ticket in your issue tracker, read a file or query a database. To
reach these tools they use MCP, the Model Context Protocol. MCP is an open standard that describes how an assistant
talks to a program that offers tools. In MCP terms, the assistant is the client and the program with the tools is the
server.

When client and server talk over the web, a connection used to begin with a check-in. The client sent a first request
called `initialize`, in which it named the protocol version it speaks and the features it supports. The server answered
and usually handed out a session ID in a header called `Mcp-Session-Id`. From then on the client sent that ID with every
request, so the server knew which check-in a request belonged to.

In July 2026 a new version of MCP removed these sessions. MCP names its versions after the date of their release, so
this version is called [2026-07-28](https://modelcontextprotocol.io/specification/versioning). Sessions had caused a
specific failure. When a server restarted, some assistants lost access to its tools until they were restarted
themselves.

## What a session was

Sessions belong to Streamable HTTP, the part of MCP that defines how client and server exchange messages over HTTP.
They exist in the three revisions 2025-03-26, 2025-06-18 and 2025-11-25. The session ID itself carries no information.
It points to the settings the two sides agreed at check-in, above all the protocol version and the features each side
supports. The server keeps these settings in its own storage and looks them up whenever a request arrives with the ID.

Sometimes a server no longer knows a session ID it handed out. For that case the
[spec](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports) is strict. The server must answer with
the HTTP status `404 Not Found`. The client must then "start a new session by sending a new InitializeRequest", which
means it checks in again and receives a new ID. A request that carries no session ID at all gets a different answer,
`400 Bad Request`. The two codes mean different things. 404 says the server does not know the ID. 400 says the request
did not include one.

The [proposal that introduced this transport](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/206)
allowed several copies of a server to share one storage for their sessions. In practice most servers kept their
sessions in the memory of a single running program. The official TypeScript SDK, the library many MCP servers are built
on, does exactly that by default. [SEP-2567](https://modelcontextprotocol.io/seps/2567-sessionless-mcp), one of the
proposals that later changed MCP, notes that the SDK "provides no public API for reconstructing a session on a different
node". A node here is one running copy of the server, so a session cannot move from one copy to another.

## Why it became a problem

Memory belongs to one running program and is cleared when that program stops. A server that keeps its sessions in
memory therefore loses all of them when it restarts, for example when someone installs an update. The server is back
within seconds, but every session ID it handed out before the restart is now unknown to it.

Larger setups have a second problem. A busy server runs as several copies. In front of them sits a load balancer, a
program that receives every incoming request and passes it on to one of the copies, so the work is spread across them.
With sessions in memory, only the copy that issued a session ID knows it. Every request with that ID must therefore
reach the same copy. This is called sticky routing.
[NGINX Plus](https://community.f5.com/kb/technicalarticles/mcp-session-affinity-with-f5-nginx-plus/341961), for
example, offers it by reading the session ID from each request. [SEP-2575](https://modelcontextprotocol.io/seps/2575)
counts sticky routing among the "complex and fragile solutions like sticky sessions". It also names the risk that
remains: "if the specific server instance handling a client session fails, that session state is lost."

The 404 rule from the spec was meant to make such a loss cheap. A client that receives a 404 checks in again, gets a
new session ID and carries on, at the cost of one extra request. That only works if the client follows the rule. Public
reports up to November 2026 show that many clients do and some do not.

Three widely used clients follow the rule. Claude Code checks in again after a 404, according to an
[Anthropic maintainer in May 2026](https://github.com/anthropics/claude-code/issues/55970). VS Code starts a new
session on its next request, according to the
[VS Code team in July 2025](https://github.com/microsoft/vscode/issues/253854). The Cursor editor follows the spec as
well, according to
[Cursor staff in May 2026](https://forum.cursor.com/t/cursor-mcp-client-does-not-restart-session-on-404-session-not-found/161132).

Other clients keep failing. In the same Cursor thread, users reported in September 2026 that the Cursor command-line
tool still does not check in again. Neither does the client part of the official TypeScript SDK
([#1708](https://github.com/modelcontextprotocol/typescript-sdk/issues/1708),
[#3056](https://github.com/modelcontextprotocol/typescript-sdk/issues/3056)). The Python SDK client treats the 404 as a
final error and stops ([#1676](https://github.com/modelcontextprotocol/python-sdk/issues/1676)). All three SDK issues
were still open on 25 November 2026. The SDK clients matter beyond the SDKs, because many apps and gateways use them to
talk to servers. For ChatGPT and Claude Desktop I found no source either way.

claude.ai shows a second trap, this time on the server side. It checks in again after a 404, as the spec requires. In
April 2026 a user [found it stuck](https://github.com/anthropics/claude-code/issues/48557) on a server that answered a
lost session with 400 instead. To claude.ai, a 400 means that the request carried no session ID. It only checks in again
after a 404, so it kept failing. A server that answers with the wrong status code can break a client that would
otherwise recover.

People who use these assistants in a chat window rarely notice any of this. Users report that the
[ChatGPT connector](https://community.openai.com/t/connector-tool-calls-generating-fresh-mcp-session-each-invocation/1364975)
and [claude.ai chat](https://github.com/anthropics/claude-ai-mcp/issues/583) open a new session before nearly every tool
call. A session that lives for only one call has no time to go stale. The failures hit clients that keep one session for
as long as they run, such as editors and coding agents.

Gateways are hit hardest. A gateway is a program that sits between the assistant and many tool servers. It offers all
their tools to the assistant through one connection. To do that it holds a session at each server behind it, so towards
those servers the gateway is itself a client. Every one of those sessions can go stale. SEP-2567 calls gateways "the
hardest-hit category".

[metamcp](https://github.com/metatool-ai/metamcp) shows what this looks like in practice. It is a widely used
open-source gateway that also runs local servers and offers OpenAPI endpoints. A disclosure: bundlemcp, the gateway I
maintain, began as a rewrite of metamcp's bundling core. As of November 2026 metamcp keeps its sessions in a
[map in the memory of its process](https://github.com/metatool-ai/metamcp/blob/05818ec2767b946f98d280ae9cefa401f0362d62/apps/backend/src/lib/session-lifetime-manager.ts).
This is the standard pattern of the TypeScript SDK. Towards the assistants that connect to it, metamcp behaves as the
spec requires and answers an unknown session ID with 404.

The failure was on the other side, where metamcp is the client. In
[PR #283](https://github.com/metatool-ai/metamcp/pull/283) an operator reported "~8k failed tool calls over a few
hours". A server behind metamcp had restarted and forgotten metamcp's session ID. metamcp did not check in again. It
kept sending the forgotten ID, so every call failed until someone restarted metamcp itself. A fix for the tool-call path
was merged in June 2026. It is not yet part of a [tagged release](https://github.com/metatool-ai/metamcp/releases). Both
behaviours follow from the SDK's defaults: sessions in the memory of one process and a client that does not check in
again on its own.

## What replaced it

The
[2026-07-28 version of the transport](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http)
describes the change in one line: "Removal of protocol-level sessions." The
[official announcement](https://blog.modelcontextprotocol.io/posts/2026-07-28/) gives the reason: "Any request can now
land on any server instance behind a plain round-robin load balancer without needing shared storage." Round-robin is the
simplest way to spread requests. The load balancer hands them to the copies in turn, without looking at what they
contain. For that to work, every copy must be able to answer every request on its own.

Each request therefore carries the information that the check-in used to settle. A field called `_meta` inside the
request holds the protocol version and the features the client supports. The key values are repeated in HTTP headers.
A proxy or load balancer can then read them without parsing the body of the request. The spec also says that servers
"MUST NOT infer capabilities from prior requests". The reason is the round-robin rule: the next request may reach a copy
that never saw the earlier one.

Some exchanges used to depend on the session as well. A server sometimes needs input from the user in the middle of a
call, for example a confirmation. In the new version the server returns a result that asks for this input. The client
collects the answer and sends the original call again, this time with the answer attached. Any copy of the server can
handle that second call.

Tools can still remember things between calls. They do it with an ID that the assistant passes as an ordinary argument.
SEP-2567 uses a shop as its example. A tool called `create_basket()` returns a `basket_id`. The assistant passes
that ID into every later call about that basket. Any copy of the server can answer those calls, provided the basket is
stored somewhere all copies can reach. Web shops already store their data that way. The ID grants no access by itself.
A server that checks who is calling still does so on every call, whatever ID it receives.

[Cloudflare](https://blog.cloudflare.com/mcp-v2/) sums up the result in one line: "There is no protocol session to
store." The word protocol is the important part. The protocol keeps no state between requests any more. State that a
task needs, such as the basket, still exists. The tool keeps it in storage of its own.

## The in-between year

The major official SDKs shipped support for 2026-07-28 on the day of the release, some of them
[in beta](https://developers.googleblog.com/scaling-ai-agent-infrastructure-with-the-mcp-stateless-updates/). Server
authors could adopt it right away. Clients move slower. [Zuplo](https://zuplo.com/learn/mcp/compatibility) keeps a
compatibility matrix of MCP clients. Its last check, on 31 July 2026, lists Claude's apps as "initialize era" and VS
Code at 2025-11-25. Both still open every connection with the old check-in. On 21 September 2026
[Cursor staff wrote](https://forum.cursor.com/t/mcp-client-cannot-connect-to-modern-only-2026-07-28-streamable-http-servers-legacy-initialize-rejected/172536)
that its client "currently speaks the 2025-11-25 revision and earlier". They added: "No timeline at the moment!"

For the people who run servers, this means supporting two revisions at once. A server that must work with today's
clients keeps implementing the session-based revision next to the new one. The spec allows this.

A gateway faces the same task. It has to accept both kinds of request on one URL.
[bundlemcp](https://github.com/wingfold-ai/bundlemcp) is one example. It is a v0.4 public preview and speaks Streamable
HTTP only. For each incoming request it checks which revision the request uses. A request in the new style carries its
`_meta`. The gateway stores nothing for it and hands out no session ID.

A session-based request is handled differently. Its session is stored in Valkey, a key-value store that runs as a
separate service. Every copy of the gateway can reach it. After a restart, or on another copy, the gateway loads the
session from Valkey and continues it. bundlemcp keeps its own session IDs at the servers behind it in Valkey too, for
the same reason. As long as Valkey keeps its data, the gateway answers 404 only for a session that has expired. A
restart alone never causes one.

You can try this on the local Docker Compose stack from bundlemcp's
[quickstart](https://github.com/wingfold-ai/bundlemcp#quickstart). The commands below open a session, restart the
gateway and then reuse the old session ID:

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

The last command lists the four tools behind the demo endpoint: `echo__countdown`, `echo__echo`, `echo__reverse` and
`echo__shout`. It runs on the session that was opened before the restart, with no new check-in. A session ID that the
gateway never issued still gets a 404, as the spec requires.

The guarantee covers sessions. A single request can still fail while a copy restarts. The
[integration tests](https://github.com/wingfold-ai/bundlemcp/blob/main/tests/integration/test_replicas.py) show where
the line is. They run two gateway copies and restart both while clients send a request every 50 milliseconds. A second
test updates both copies to a new version under the same load. For each request the tests accept either an answer or
the status 503, which asks the client to try again. After the restart, every session must work without a new check-in.

The default stack runs only one copy of the gateway. While that copy restarts, requests fail for a few seconds, although
it first lets running calls finish. A session-based client can also keep a connection open so that the server can send
it messages. That connection breaks on a restart. The client has to open it again. If Valkey itself loses its data, the
sessions are gone. Clients then get an ordinary 404, which helps only the clients that act on a 404.

## What to check in your own setup

Start with the revision your clients speak. A client that opens with `initialize` still uses sessions, so everything
above applies to it. Then test what happens when a session is lost. Restart your server while a client you rely on is
connected. Then make another tool call from that client and see whether it checks in again.

If you run a server, check its status codes. An unknown or expired session ID must get exactly 404, because only 404
tells a client to check in again. Use 400 only when the request carries no session ID. Never answer with 500.

If you run a gateway, test the connection behind it as well. Restart one of the servers behind the gateway and check
that the next call through the gateway still works. If you build on the TypeScript or Python SDK client and still use
sessions, the client will not check in again for you. Both issues were still open on 25 November 2026. Until they are
fixed, handle the 404 in your own code or move to 2026-07-28, where there is no session to lose.
