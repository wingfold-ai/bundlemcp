# Quickstart

This walkthrough brings up the reference Docker Compose stack, signs you in to the admin UI, and calls a demo bundle
through an endpoint. It takes about ten minutes.

## Prerequisites

- Docker Engine 24 or newer with the compose plugin.
- Ports 8000, 3000 and 8080 free on the host.
- About 4 GB of free RAM and 5 GB of disk. The first `up` builds a Python and a
  Nuxt image from source, which takes a few minutes.

Nothing else: the stack brings its own Postgres, Valkey and identity provider.
For what a production deployment needs instead, see
[Requirements](/self-hosting/requirements).

## 1. Start the stack

```bash
git clone https://github.com/wingfold-ai/bundlemcp.git
cd bundlemcp
cp deploy/.env.example deploy/.env
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --build --wait --wait-timeout 300
```

The core stack starts six containers:

| Service | Port | Purpose |
|---|---|---|
| `gateway` | 8000 | The bundlemcp gateway: MCP endpoints, OAuth server, management API |
| `web` | 3000 | The admin UI |
| `postgres` | internal | Durable configuration, tokens, audit log |
| `valkey` | internal | Live sessions, rate limits, cross-replica signalling |
| `keycloak` | 8080 | Development OIDC identity provider (`admin` / `admin`) |
| `echo-mcp` | internal | A tiny example MCP server with three tools |

`--wait` returns once the gateway reports ready on `/readyz`. A timeout on the
first run usually means the image build is still going, not that anything
failed.

::: tip Not empty on first boot
The stack mounts `deploy/seed.yaml` as a bootstrap file. On startup the
gateway registers the `echo` server, creates the `demo` bundle, and exposes
it at the `demo` endpoint with API-key access. See
[Bootstrap file](/self-hosting/bootstrap) for the format.

The same seed also registers four private servers the maintainers use, which
the default stack does not start. They appear on the Servers page with
`health_status: error`; delete them, or remove them from your copy of the seed.
:::

## 2. Sign in to the admin UI

Open <http://localhost:3000>. You are redirected to the gateway's login route, which forwards you to Keycloak. Sign in
with `admin` / `admin`.

That account's email (`admin@example.com`) is listed in `BUNDLEMCP_ADMIN_EMAILS` in the compose file, so it lands on the
dashboard with admin rights. Any other account sees the catalogue instead: the bundles it can connect an MCP client to,
and nothing to manage.

Browse **Servers**, **Bundles** and **Endpoints** to see what the seed created.

## 3. Call the demo endpoint

Every endpoint is served at `<public url>/<endpoint name>/mcp`. The `demo` endpoint accepts API keys, and the compose
file provisions a development service key on first boot:

```bash
KEY=bmcp_sk_devservicekey000000000000000000000000
V=2026-07-28

curl -s http://localhost:8000/demo/mcp \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -H "MCP-Protocol-Version: $V" -H "Mcp-Method: tools/list" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{"_meta":{
        "io.modelcontextprotocol/protocolVersion":"'"$V"'",
        "io.modelcontextprotocol/clientCapabilities":{}}}}'
```

The reply lists three tools, `echo__echo`, `echo__reverse` and `echo__shout`.
The `echo__` prefix is the server name; it is how the gateway routes a call
back to the right upstream. Call one — a `tools/call` also mirrors the tool
name into `Mcp-Name`, and answers with an SSE stream rather than a JSON body:

```bash
curl -s -N http://localhost:8000/demo/mcp \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -H "MCP-Protocol-Version: $V" -H "Mcp-Method: tools/call" \
  -H "Mcp-Name: echo__reverse" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{
        "name":"echo__reverse","arguments":{"text":"bundlemcp"},
        "_meta":{"io.modelcontextprotocol/protocolVersion":"'"$V"'",
                 "io.modelcontextprotocol/clientCapabilities":{}}}}'
```

The last `data:` event carries the result, `pcmeldnub`.

::: details Why all that ceremony in a plain POST?
The gateway serves two MCP eras on one URL, and each request has to say which
one it belongs to. A stateless-era request (revision 2026-07-28) repeats its
protocol version and client capabilities in `params._meta` and mirrors three
values into headers, so no session is needed. A session-era client instead
opens with `initialize` and gets an `Mcp-Session-Id` to send from then on.

A POST carrying neither is refused with `400`. Every MCP SDK builds one or the
other for you — the ceremony is only visible when you use `curl`. The full
contract is in [Request envelope](/integrate/http-surface#request-envelope).
:::

::: warning The list can be empty on a cold start
Bootstrap discovers an upstream's tools in the background, so on a first boot
the seed can finish before `echo-mcp` is listening. If `tools` comes back
empty, force a probe:

```bash
curl -s -X POST http://localhost:8000/api/v1/servers/echo:refresh-tools \
  -H "Authorization: Bearer $KEY"     # -> {"discovered": 3, ...}
```

If it still reports nothing, `GET /api/v1/servers/echo` shows `health_status`
and `last_error`. More symptoms in
[Troubleshooting](/self-hosting/troubleshooting).
:::

## 4. Register your own server

Register a Streamable HTTP MCP server you run somewhere the gateway can reach. From the UI, go to **Servers → New**, or
use the management API with the same service key:

```bash
curl -s -X PUT http://localhost:8000/api/v1/servers/my-server \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"name":"my-server","url":"http://host.docker.internal:9000/mcp","description":"My tools"}'
```

::: warning The gateway dials this URL from inside its container
Two consequences, and between them they account for most first-time failures:

- **`localhost` is not your machine.** Inside the container it is the container.
  Worse, the gateway's egress policy blocks loopback outright, so a
  `http://localhost:9000/mcp` URL is refused rather than merely unreachable.
- **Reach your host by name.** Use `http://host.docker.internal:9000/mcp`. On
  Linux, add `extra_hosts: ["host.docker.internal:host-gateway"]` to the
  `gateway` service first. Alternatively attach your server to the compose
  network and use its service name, as `echo-mcp` does.

See [Network egress](/self-hosting/deploy#network-egress) for the policy and
how to widen it.
:::

The gateway probes the server, discovers its tools and stores them. A server
that is not up yet is stored with `health_status: error` and re-probed later;
`GET /api/v1/servers/my-server` shows `last_error` if the probe failed.

Then add it to a bundle and expose it:

```bash
API=http://localhost:8000/api/v1
curl -s -X PUT $API/bundles/tools -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"name":"tools","description":"My tools and the echo tools"}'
curl -s -X PUT $API/bundles/tools/servers/my-server -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" -d '{"enabled":true}'
curl -s -X PUT $API/bundles/tools/servers/echo    -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" -d '{"enabled":true}'
curl -s -X PUT $API/endpoints/tools -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"name":"tools","bundle_name":"tools","profile":"default","auth_modes":["api_key"]}'
```

`http://localhost:8000/tools/mcp` now serves both servers' tools.

## 5. Connect a real client

[Scripts and agents](/connect/scripts) work against this local stack as-is: an
API key over plain HTTP is all they need.

claude.ai and ChatGPT do not. They connect *from the internet*, so they need
your endpoint on a publicly resolvable HTTPS URL — either
[a real deployment](/self-hosting/deploy), or a tunnel in front of this stack
with `BUNDLEMCP_PUBLIC_URL` set to the tunnel's URL. Every OAuth URL the
gateway advertises derives from that setting, so it must match the URL the
client actually dialled.

- [claude.ai](/connect/claude) needs an endpoint with the `claude` profile
  and OAuth; the gateway runs the whole OAuth flow, including the consent
  screen.
- [ChatGPT](/connect/chatgpt) needs the `chatgpt` profile, which re-annotates
  write tools so ChatGPT accepts them.

## Tear down

```bash
docker compose -f deploy/docker-compose.yml --env-file deploy/.env down
# add -v to also drop the Postgres volume
```

## Next steps

Before you put this in front of other people, read
[Production deployment](/self-hosting/deploy): the compose file's inline
secrets, the dev identity provider and the plain-HTTP public URL are for local
use only.

- [Core concepts](/guide/concepts) — servers, bundles, endpoints and profiles.
- [Troubleshooting](/self-hosting/troubleshooting) — if a step above did not
  behave as described.
