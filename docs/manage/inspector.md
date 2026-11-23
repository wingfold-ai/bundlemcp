---
description: "Try an MCP server's tools from the bundlemcp admin UI: connect, list its tools, fill in arguments and
  call them, without a separate MCP client."
---

# Inspector

The Inspector page tries a server's tools without a separate MCP client: connect, see what the server offers, fill in
a tool's arguments and call it. Everything goes through the management API, so stored credentials never reach the
browser and the server needs no CORS headers.

## Targets

| Target | What it reaches | Credentials |
|---|---|---|
| **Upstream** | A registered upstream server, as the gateway reaches it for tool calls | The stored static headers and upstream OAuth, applied by the gateway |
| **Endpoint** | One of this gateway's endpoints, through its public MCP route | What a client of that endpoint presents, entered on the page |
| **URL** | Any Streamable HTTP MCP URL that is not registered | Headers entered on the page, one `Name: value` per line |

An **upstream** with upstream OAuth uses the shared account, or, when each person connects their own, the account you
connected. A service key has no account, so it cannot inspect such an upstream and gets `409`.

An **endpoint** is inspected exactly as its clients see it: its authentication, its profile's annotations, the bundle's
curation and its rate limits all apply. Enter an API key for that endpoint, or an OAuth access token issued for it; an
endpoint that accepts anonymous calls needs nothing. The credential is used for that one request and never stored.

A **URL** must pass the gateway's egress policy, like every address an admin supplies; a URL in a blocked range is
refused with `egress_denied` before anything is sent. The headers are used for that one request and never stored or
logged.

## What you can do

- **Connect** initialises a connection and shows the server's name and version, the MCP revision negotiated and the
  capabilities it advertises, then lists its tools.
- **Ping** checks that the server answers. Ping belongs to the handshake-era revisions; a server on the stateless
  revision answers it as unsupported, and the page shows that answer.
- **Tools** shows each tool's description, annotations and input schema. The call form is generated from the schema:
  required fields are marked, and *Raw JSON* shows the same arguments as a JSON object to edit. A schema the form
  cannot express (nested objects, arrays) opens in raw JSON.
- **Call** sends `tools/call`. Progress notifications appear as they arrive, then the result, or the error: a result
  with `isError: true` and a JSON-RPC error are both shown as errors. A tool annotated `destructiveHint: true` asks
  for confirmation first.

Every request connects, runs its one operation and disconnects, so the time a call took is shown beside the time
connecting took. Nothing about an inspector session is kept on the gateway.

## Logging, audit and metering

| Target | Logged | Audited | Metered |
|---|---|---|---|
| Upstream, URL | Yes, with `source=inspector` and who inspected | No | No |
| Endpoint | As any client's request | Yes, as any client's call | Yes, through the metering hook |

Calls through an endpoint are ordinary client calls, so an application layer may bill them. Use a test key or a test
endpoint when that matters. The inspector advertises no client capabilities: a tool that asks the client for input
(elicitation or sampling) fails rather than prompting you.

## API

The page uses four management routes, each with a `target` naming the kind and the server:

```bash
curl -s https://gw.example.com/api/v1/inspector:list-tools \
  -H "Authorization: Bearer $SERVICE_KEY" -H "Content-Type: application/json" \
  -d '{"target": {"kind": "upstream", "name": "weather"}}'
```

| Route | Answers |
|---|---|
| `POST /api/v1/inspector:connect` | Server info, protocol revision, capabilities, instructions and how long connecting took |
| `POST /api/v1/inspector:ping` | How long connecting and the ping took |
| `POST /api/v1/inspector:list-tools` | Every tool with its schemas and annotations |
| `POST /api/v1/inspector:call-tool` | Server-Sent Events: a `progress` event per notification, then one `result` or `failure` |

A target that gives no MCP answer is `502` with a `detail` that starts with its connection state, such as
`unreachable` or `credential_required`; in a call's stream it is the `failure` event.
