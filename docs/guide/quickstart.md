# Quickstart

This walkthrough brings up the reference Docker Compose stack, signs you in to the admin UI, and calls a demo bundle
through an endpoint. It takes about ten minutes.

## Prerequisites

- Docker Engine with the compose plugin.
- The line `127.0.0.1 keycloak` in `/etc/hosts`. The stack ships a development identity provider (Keycloak), and the
  gateway hands your browser Keycloak URLs under the compose-internal hostname, so the host must resolve it.

```bash
echo "127.0.0.1 keycloak" | sudo tee -a /etc/hosts
```

## 1. Start the stack

```bash
git clone https://github.com/mhoegger/bundlemcp.git
cd bundlemcp
cp deploy/.env.example deploy/.env
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --build --wait
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

`--wait` returns once the gateway reports ready on `/readyz`.

::: tip Not empty on first boot
The stack mounts `deploy/seed.yaml` as a bootstrap file. On startup the gateway registers the `echo` server, creates the
`demo` bundle, and exposes it at the `demo` endpoint with API-key access. See [Bootstrap file](/self-hosting/bootstrap)
for the format.
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
curl -s http://localhost:8000/demo/mcp \
  -H "Authorization: Bearer bmcp_sk_devservicekey000000000000000000000000" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

The reply lists three tools, `echo__echo`, `echo__reverse` and `echo__shout`. The `echo__` prefix is the server name; it
is how the gateway routes a call back to the right upstream. Call one:

```bash
curl -s http://localhost:8000/demo/mcp \
  -H "Authorization: Bearer bmcp_sk_devservicekey000000000000000000000000" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"echo__reverse","arguments":{"text":"bundlemcp"}}}'
```

::: details Why does a plain POST work without an `initialize` handshake?
The gateway serves every MCP protocol revision on the same URL. Modern-era clients (revision 2026-07-28 and later) send
self-contained requests. Clients that still open with `initialize` get a session id back and are served just as well.
Plain `curl` calls like the one above are treated as modern-era requests.
:::

## 4. Register your own server

Register a Streamable HTTP MCP server you run somewhere the gateway can reach. From the UI, go to **Servers → New**, or
use the management API with the same service key:

```bash
curl -s -X PUT http://localhost:8000/api/v1/servers/weather \
  -H "Authorization: Bearer bmcp_sk_devservicekey000000000000000000000000" \
  -H "Content-Type: application/json" \
  -d '{"name":"weather","url":"http://weather-mcp:8080/mcp","description":"Forecasts"}'
```

The gateway probes the server, discovers its tools and stores them. A server that is not up yet is stored with
`health_status: error` and re-probed later.

Then add it to a bundle and expose it:

```bash
KEY=bmcp_sk_devservicekey000000000000000000000000
API=http://localhost:8000/api/v1
curl -s -X PUT $API/bundles/tools -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"name":"tools","description":"Weather and echo tools"}'
curl -s -X PUT $API/bundles/tools/servers/weather -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" -d '{"enabled":true}'
curl -s -X PUT $API/bundles/tools/servers/echo    -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" -d '{"enabled":true}'
curl -s -X PUT $API/endpoints/tools -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"name":"tools","bundle_name":"tools","profile":"default","auth_modes":["api_key"]}'
```

`http://localhost:8000/tools/mcp` now serves both servers' tools.

## 5. Connect a real client

- [claude.ai](/connect/claude) needs an endpoint with the `claude` profile and OAuth; the gateway runs the whole OAuth
  flow, including the consent screen.
- [ChatGPT](/connect/chatgpt) needs the `chatgpt` profile, which re-annotates write tools so ChatGPT accepts them.
- [Scripts and agents](/connect/scripts) use an API key.

## Tear down

```bash
docker compose -f deploy/docker-compose.yml --env-file deploy/.env down
# add -v to also drop the Postgres volume
```

## Next steps

Before you put this in front of other people, read [Production deployment](/self-hosting/deploy): the compose file's
inline secrets, the dev identity provider and the plain-HTTP public URL are for local use only.
