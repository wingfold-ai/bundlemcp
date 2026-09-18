# Connect scripts and agents

Anything that cannot run a browser-based OAuth flow, or should not act as a person, connects with an **API key**: cron
jobs, CI pipelines, automation platforms such as n8n, backend services, and coding agents on a developer machine.

## 1. An endpoint that accepts API keys

```bash
curl -s -X PUT https://gw.example.com/api/v1/endpoints/assistant-ci \
  -H "Authorization: Bearer $SERVICE_KEY" -H "Content-Type: application/json" \
  -d '{"name":"assistant-ci","bundle_name":"assistant","profile":"default","auth_modes":["api_key"]}'
```

An endpoint can list both `oauth` and `api_key`, serving humans and scripts from one URL. Keep a separate endpoint when
you want separate rate limits.

## 2. An endpoint key

Create an `endpoint`-kind key scoped to that endpoint, from **API keys** in the UI or:

```bash
curl -s -X POST https://gw.example.com/api/v1/api-keys \
  -H "Authorization: Bearer $SERVICE_KEY" -H "Content-Type: application/json" \
  -d '{"name":"nightly-report","kind":"endpoint","endpoint_ids":["<assistant-ci id>"]}'
```

Copy the `key` from the response; it is shown once. See
[API keys](/manage/api-keys).

## 3. Call the endpoint

Send the key as a bearer or in `X-API-Key`. The endpoint speaks Streamable HTTP: JSON-RPC over `POST`.

**Use an SDK if you can.** The SDK tabs below open a session with `initialize`
and handle the protocol for you. A raw `curl` has to build the stateless-era
envelope itself — every request repeats its protocol version in `params._meta`
and mirrors three values into headers, and a request carrying neither that
envelope nor an `Mcp-Session-Id` is refused with `400`. The full contract is in
[Request envelope](/integrate/http-surface#request-envelope).

::: code-group

```bash [curl]
URL=https://gw.example.com/assistant-ci/mcp
KEY=bmcp_sk_…
V=2026-07-28

curl -s $URL \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -H "MCP-Protocol-Version: $V" -H "Mcp-Method: tools/list" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{"_meta":{
        "io.modelcontextprotocol/protocolVersion":"'"$V"'",
        "io.modelcontextprotocol/clientCapabilities":{}}}}'

# tools/call also mirrors the tool name into Mcp-Name
curl -s $URL \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -H "MCP-Protocol-Version: $V" -H "Mcp-Method: tools/call" \
  -H "Mcp-Name: weather__forecast" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{
        "name":"weather__forecast","arguments":{"city":"Zurich"},
        "_meta":{"io.modelcontextprotocol/protocolVersion":"'"$V"'",
                 "io.modelcontextprotocol/clientCapabilities":{}}}}'
```

```python [Python (fastmcp)]
import asyncio
from fastmcp import Client

async def main() -> None:
    async with Client("https://gw.example.com/assistant-ci/mcp", auth="bmcp_sk_…") as client:
        tools = await client.list_tools()
        print([t.name for t in tools])
        result = await client.call_tool("weather__forecast", {"city": "Zurich"})
        print(result)

asyncio.run(main())
```

```python [Python (mcp SDK)]
import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def main() -> None:
    headers = {"Authorization": "Bearer bmcp_sk_…"}
    async with streamablehttp_client("https://gw.example.com/assistant-ci/mcp", headers=headers) as (r, w, _):
        async with ClientSession(r, w) as session:
            await session.initialize()
            tools = await session.list_tools()
            print([t.name for t in tools.tools])

asyncio.run(main())
```

```ts [TypeScript]
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";

const transport = new StreamableHTTPClientTransport(
  new URL("https://gw.example.com/assistant-ci/mcp"),
  { requestInit: { headers: { Authorization: "Bearer bmcp_sk_…" } } },
);
const client = new Client({ name: "nightly-report", version: "1.0.0" });
await client.connect(transport);
console.log(await client.listTools());
```

:::

One URL serves both eras. The SDK examples call `initialize` and get a session;
the `curl` examples send the stateless envelope and get no session. Note that a
`tools/call` answers with an SSE stream rather than a JSON body, so a raw client
reads the last `data:` event as the result.

## Coding agents

Claude Code and similar tools register remote MCP servers by URL with a header. For Claude Code:

```bash
claude mcp add --transport http assistant https://gw.example.com/assistant-ci/mcp \
  --header "Authorization: Bearer bmcp_sk_…"
```

Other agents take an equivalent `url` plus `headers` block in their MCP configuration.

## Identity

An API key call is identified as `api_key:<key id>`. Upstream servers see that value in `X-MCP-User`, audit records
carry the key id, and the metering hook receives it as `sub`. If an upstream server introspects the forwarded bearer,
the gateway reports an API key as active with that `sub`.

## Errors you will meet

| Response | Cause |
|---|---|
| `401` with `WWW-Authenticate` | Missing, wrong or deactivated key, or the key is scoped to other endpoints. |
| `404` | The endpoint name is wrong or the endpoint is disabled. |
| `429` with `Retry-After` | A rate limit on the endpoint. |
| `400` with code `-32602` or `-32020` | A hand-built request whose `params._meta` envelope is missing, or whose mirrored headers disagree with the body. |
| JSON-RPC error on `tools/call` | The tool is disabled in the bundle, the metering hook denied the call, or the upstream failed. The message says which. |

[Error responses](/integrate/errors) lists every code and which are worth
retrying.

## Next steps

- [Request envelope](/integrate/http-surface#request-envelope) — the raw wire contract.
- [API keys](/manage/api-keys) — key kinds, scoping and rotation.
- [Endpoints](/manage/endpoints) — rate limits and auth modes.
