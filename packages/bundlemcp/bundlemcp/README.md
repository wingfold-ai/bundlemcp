# bundlemcp (library)

The gateway library: it registers upstream MCP servers, composes them into
**bundles**, and exposes each bundle through one or more **endpoints** shaped for
a specific consumer (claude.ai OAuth, ChatGPT re-annotation, API-key scripts).
Everything a deployment runs lives here; `apps/gateway` is a thin composition
root over `create_app`.

This README is a map. Two subsystems carry the bulk of the complexity and have
their own deep-dive docs:

- **[gateway/README.md](gateway/README.md)** — the core: the Streamable-HTTP
  edge, bundling/composition, tool discovery, sessions, multi-replica
  correctness, state propagation, rate limiting.
- **[oauth/README.md](oauth/README.md)** — the four authentication mechanisms:
  MCP-client OAuth 2.1, admin OIDC login, management-API keys, and upstream
  auth to protected MCP servers.

## Layer map

The package is split by responsibility. The rule (ADR-0019/0020) is that
**business logic and DTOs are framework-free** — they never import FastAPI —
so the HTTP layer, the MCP edge, the OAuth endpoints, and bootstrap all consume
them as peers.

```
bundlemcp/
├── models/          SQLModel entities — the single source of truth for the
│                    schema. Tables AND Pydantic models (ARC-3). Everything
│                    else derives from these.
├── schemas/         Management-API DTOs (Pydantic), one class per file grouped
│                    by resource. Enforce the domain rules table models can't
│                    (name patterns, endpoint auth modes, profile/auth matrix).
│                    Frontend TS types are generated from these via OpenAPI.
├── services/        Framework-free business logic, one service class per
│                    resource (ServerService, BundleService, …, AuthService).
│                    Take plain values, return DTOs, raise the domain errors in
│                    services/errors/. This is where invariants live.
├── store/           Persistence accessors: db.py (async engine), redis.py,
│                    sessions.py (SessionStore), invalidation.py (the
│                    cross-replica cache-invalidation bus).
├── gateway/         The MCP serving edge and everything behind it — see
│                    gateway/README.md.
├── oauth/           OAuth 2.1 server, admin OIDC login, upstream OAuth client —
│                    see oauth/README.md.
├── api/             FastAPI wiring ONLY: routers (thin controllers that
│                    delegate to services), providers.py (DI), auth.py
│                    (ManagementAuth edge), pagination.py, app.py (the
│                    application factory + lifespan).
├── bootstrap.py     Declarative seed: registers servers/bundles/endpoints from
│                    a YAML file on boot, reusing the services (spec 41).
├── crypto.py        Fernet/MultiFernet encryption at rest for upstream tokens.
├── security.py      API-key generation, SHA-256 hashing, constant-time compare.
├── settings.py      Deploy-time config via BUNDLEMCP_ env vars. Runtime-tunable
│                    settings live in the Config table, not here.
└── migrations/      Alembic. 0001 creates from the live metadata; later
                     revisions are explicit diffs.
```

## Two kinds of configuration

- **Deploy-time** (`settings.py`, `BUNDLEMCP_*` env): database/Redis URLs,
  `public_url`, OIDC client, admin emails, encryption keys, web origins. Fixed
  for the life of the process.
- **Runtime-tunable** (`gateway/runtime_config.py` + the `config_entries`
  table): timeouts, session lifetime, audit retention. Editable live through
  the API/UI; changes propagate to every replica via the invalidation bus.

## The one rule worth internalizing first

**No process-local state a request depends on.** Postgres is the durable system
of record (config, tokens, audit); Redis holds live session/stream/rate state.
Any replica can serve any request, and a gateway restart is a non-event for
in-flight client sessions. The only replica-local objects are open streams and
in-flight call handles (`gateway/streams.py`), and those are reachable from
other replicas through the Redis `SignalBus`. This is what the sessions and
state-propagation sections of the gateway doc are really about.

## Where the rest of the documentation lives

- `spec/` — the source of truth: atomic specs with testable requirement IDs
  (`SRV-1`, `EP-3`, `OAS-5`, …). These READMEs cite those IDs.
- `docs/arc42/` — architecture narrative. `docs/adr/` — decision records
  (ADR-0019/0020 explain the service/DTO layering used above).
- `deploy/TESTING.md` — how to run the full compose stack and the test suites.
