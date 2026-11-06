---
layout: home

hero:
  text: One gateway for all your MCP servers
  tagline: Register Streamable HTTP MCP servers, compose them into bundles, and expose each bundle through endpoints shaped for claude.ai, ChatGPT or your own scripts. Self-hosted, restart-safe, horizontally scalable.
  image:
    src: /banner.svg
    alt: "bundlemcp: unified mcp server bundler"
  actions:
    - theme: brand
      text: Quickstart
      link: /guide/quickstart
    - theme: alt
      text: What is bundlemcp?
      link: /guide/what-is-bundlemcp
    - theme: alt
      text: GitHub
      link: https://github.com/wingfold-ai/bundlemcp

features:
  - icon: 🧩
    title: Bundle many servers into one
    details: A bundle aggregates the tools of several upstream MCP servers into a single virtual server, with per-bundle tool curation and overrides.
    link: /manage/bundles
    linkText: Bundles and curation
  - icon: 🎯
    title: Per-client endpoints
    details: Expose the same bundle several times, each with its own sign-in method, client profile and rate limits. claude.ai gets OAuth, ChatGPT gets re-annotated tools, scripts get an API key.
    link: /manage/endpoints
    linkText: Endpoints
  - icon: 🔐
    title: OAuth 2.1 built in
    details: The gateway runs its own authorization server with dynamic client registration, PKCE, consent and introspection. Humans log in through any OIDC provider.
    link: /connect/claude
    linkText: Connect claude.ai
  - icon: ♻️
    title: Restarts are non-events
    details: Nothing a request needs is kept in a single process's memory. Any replica serves any session, so you can roll out new versions and scale out without dropping clients.
    link: /self-hosting/deploy
    linkText: Deploy it
  - icon: 🛠️
    title: Everything is an API
    details: The admin UI is a client of the same versioned REST API you can script against. Provision from a declarative bootstrap file or drive it from CI.
    link: /integrate/management-api
    linkText: Management API
  - icon: 🧾
    title: Audit and metering
    details: Every tool call is recorded. A documented metering hook lets an application layer plug in billing without forking the gateway.
    link: /integrate/metering-hook
    linkText: Metering hook
---

## See it run

<RepositoryNotice />

Ten minutes from clone to a working bundle, with Docker and ports 8000, 3000
and 8080 free. The compose stack ships a demo server, bundle and endpoint, so
the first call needs nothing but a key.

::: code-group

```bash [1. start]
git clone https://github.com/wingfold-ai/bundlemcp.git && cd bundlemcp
cp deploy/.env.example deploy/.env
docker compose -f deploy/docker-compose.yml --env-file deploy/.env \
  up -d --build --wait --wait-timeout 300
```

```bash [2. call]
KEY=bmcp_sk_devservicekey000000000000000000000000
V=2026-07-28
curl -s -N http://localhost:8000/demo/mcp \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -H "MCP-Protocol-Version: $V" -H "Mcp-Method: tools/call" \
  -H "Mcp-Name: echo__reverse" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{
       "name":"echo__reverse","arguments":{"text":"bundlemcp"},
       "_meta":{"io.modelcontextprotocol/protocolVersion":"'"$V"'",
                "io.modelcontextprotocol/clientCapabilities":{}}}}'
```

```json [3. result]
// arrives as the last `data:` event of an SSE stream
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": { "content": [{ "type": "text", "text": "pcmeldnub" }] }
}
```

:::

An MCP SDK builds that envelope for you — the headers and `_meta` above are
what a hand-rolled client has to send. See
[Request envelope](/integrate/http-surface#request-envelope).

Then open the admin UI at `localhost:3000` and register your own upstream
servers. To try it from claude.ai or ChatGPT, `deploy/stack.sh up` puts the
same stack behind a tunnel ([Local, tunnel or production](/self-hosting/setups)).
The whole path is in the [Quickstart](/guide/quickstart).
