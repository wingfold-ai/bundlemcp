# stdio servers behind a sidecar

bundlemcp talks to upstream servers over **Streamable HTTP only**. It never spawns processes, which keeps the gateway
image small and the failure modes simple. Many MCP servers, especially those published on npm or PyPI, still speak
stdio. Run them behind a small HTTP sidecar and register the sidecar's URL.

## The pattern

The gateway talks HTTP to a sidecar container, and the sidecar talks stdio to the MCP server process it started. The
sidecar lives next to the gateway on the same network, owns the process, restarts it if it dies, and exposes `/mcp`.
From the gateway's point of view it is an ordinary Streamable HTTP server.

## Sidecar options

Any of these work; pick the one whose runtime you already have in the image.

| Sidecar | Runtime | Command shape |
|---|---|---|
| [mcp-proxy](https://github.com/sparfenyuk/mcp-proxy) | Python | `mcp-proxy --port=8080 -- <server command>` |
| [Supergateway](https://github.com/supercorp-ai/supergateway) | Node | `supergateway --stdio "<server command>" --outputTransport streamableHttp --port 8080` |
| FastMCP proxy | Python | A few lines of Python; see below. |

## Compose example

Wrapping the filesystem server from npm with Supergateway:

```yaml
services:
  fs-mcp:
    image: node:22-alpine
    command: >
      npx -y supergateway
        --stdio "npx -y @modelcontextprotocol/server-filesystem /data"
        --outputTransport streamableHttp
        --port 8080
        --streamableHttpPath /mcp
    volumes:
      - ./shared:/data:ro
    expose:
      - "8080"
    restart: unless-stopped
```

Then register `http://fs-mcp:8080/mcp` as a server. Because the sidecar sits on the compose network, no credential is
needed between gateway and sidecar; if the wrapped server needs a token, give it to the sidecar container as an
environment variable rather than through `static_headers`.

## A FastMCP proxy

If you prefer to control the wrapper, FastMCP can proxy a stdio server as HTTP in a few lines:

```python
from fastmcp.server import create_proxy

proxy = create_proxy(
    {"mcpServers": {"fs": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "/data"]}}},
    name="fs-proxy",
)

if __name__ == "__main__":
    proxy.run(transport="http", host="0.0.0.0", port=8080, path="/mcp", allowed_hosts=["fs-mcp", "fs-mcp:8080"])
```

```dockerfile
FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir "fastmcp>=3.4"
COPY proxy.py .
EXPOSE 8080
CMD ["python", "proxy.py"]
```

The example `echo` server in the repository (`examples/echo-mcp`) is the same idea without the stdio hop: a FastMCP
server run directly with `transport="http"`.

## Things to watch

- **Host header checks.** Recent FastMCP versions reject requests whose `Host` is not localhost unless allowed. If your
  sidecar is FastMCP-based, pass `allowed_hosts=["fs-mcp", "fs-mcp:8080"]` to `run()`, or the gateway's probes fail with
  a 421.
- **Protocol era.** A wrapped stdio server negotiates through the sidecar. If its tools rely on server-initiated
  requests such as elicitation, set the registered server's `protocol_mode` to `legacy`.
- **Identity.** The sidecar receives `X-MCP-User` and any forwarded headers like any upstream, but a stdio server behind
  it usually cannot read them. Use `shared` semantics for such servers.
- **One process per sidecar.** Run one sidecar per stdio server rather than multiplexing; it keeps health status per
  server meaningful.
