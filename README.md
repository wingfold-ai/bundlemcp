# bundlemcp

A self-hostable **MCP bundling gateway**. Register upstream MCP servers
(Streamable HTTP), compose them into **bundles**, and expose each bundle
through one or more **endpoints** shaped for the client that will use it:
an OAuth profile for claude.ai, a re-annotation profile for ChatGPT, API-key
access for scripts. One gateway, any number of replicas: sessions, rate
limits and cross-replica signalling live in Valkey, configuration, tokens and
the audit log in Postgres, so a restart or a second replica is a non-event.

It is a focused rewrite of the bundling core of
[metamcp](https://github.com/metatool-ai/metamcp), built to be consumed by an
application layer such as [application-layer](the application layer's repository)
(identity provider, billing, discovery) but fully usable on its own with any
OIDC provider.

## Quickstart

Prerequisites: Docker with the compose plugin, and `127.0.0.1 keycloak` in
`/etc/hosts` (the gateway hands the browser Keycloak URLs under the compose
hostname):

```bash
echo "127.0.0.1 keycloak" | sudo tee -a /etc/hosts
cp deploy/.env.example deploy/.env
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --build --wait
```

Then:

1. Open the admin UI at <http://localhost:3000> and sign in through the
   bundled dev identity provider with `admin` / `admin`.
2. The seed (`deploy/seed.yaml`) has already registered the `echo` example
   server, bundled it as `demo`, and exposed it at the `demo` endpoint with
   API-key access. Call it with the dev service key:

   ```bash
   curl -s http://localhost:8000/demo/mcp \
     -H "Authorization: Bearer bmcp_sk_devservicekey000000000000000000000000" \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
   ```

3. Create an endpoint with the `claude` profile and connect it in claude.ai;
   the gateway runs the OAuth authorization server and the consent screen
   itself.

The management API is documented at <http://localhost:8000/api/v1/docs>. The
application-layer fleet of upstreams (private images) starts with
`--profile fleet`; see [deploy/TESTING.md](deploy/TESTING.md).

## Where things are

| | |
|---|---|
| [spec/](spec/README.md) | The source of truth: one atomic spec per capability, with testable requirement IDs; the decision log of what was deliberately left out |
| [docs/arc42/](docs/arc42/) | Architecture rationale, arc42 sections |
| [docs/adr/](docs/adr/README.md) | Architecture decision records, append-only |
| [docs/likec4/](docs/likec4/) | Diagrams as a LikeC4 model |
| [packages/bundlemcp/](packages/bundlemcp/) | The library: services, the OAuth server, the MCP edge, the management API |
| [apps/gateway/](apps/gateway/) | The gateway entrypoint |
| [apps/web/](apps/web/) | The Nuxt admin UI |
| [deploy/](deploy/) | The compose stack, the dev Keycloak realm, the demo seed |

## Development

```bash
uv sync --all-packages
uv run pytest -q          # hermetic unit tests: in-memory SQLite + fakeredis
uv run ruff check .
uv run lint-imports       # the layer contract
cd apps/web && npm ci && npm run typecheck
```

Integration and browser tests run against the compose stack; see
[deploy/TESTING.md](deploy/TESTING.md). Contributor conventions are in
[CLAUDE.md](CLAUDE.md).
