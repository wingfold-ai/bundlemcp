# bundlemcp (library)

The gateway library: it registers upstream MCP servers, composes them into
**bundles**, and exposes each bundle through one or more **endpoints** shaped for
a specific consumer (claude.ai OAuth, ChatGPT re-annotation, API-key scripts).
Everything a deployment runs lives here; `apps/gateway` is a thin composition
root over `create_app`.

This README is a map. Two subsystems carry the bulk of the complexity and have
their own deep-dive docs:

- **[bundlemcp/api/mcp/README.md](bundlemcp/api/mcp/README.md)** — the core: the Streamable-HTTP
  edge, bundling/composition, tool discovery, sessions, multi-replica
  correctness, state propagation, rate limiting.
- **[bundlemcp/api/oauth/README.md](bundlemcp/api/oauth/README.md)** — the four authentication mechanisms:
  MCP-client OAuth 2.1, admin OIDC login, management-API keys, and upstream
  auth to protected MCP servers.

## Layer map

The package is four layers plus a composition root (ADR-0033). Dependencies
point inward only: `api` and `infrastructure` know `application`, `application`
knows `domain`, and nothing knows what is outside it. `uv run lint-imports`
enforces the direction, keeps `domain/` and `application/` free of every
driver, and keeps `api/` from naming an adapter.

```
bundlemcp/
├── domain/          Entities (plain Pydantic models, one per module, grouped by
│                    context: servers, bundles, endpoints, access, oauth,
│                    upstream_oauth, audit, config, sessions), value objects,
│                    enums and the rules they carry (policies/, bundles/
│                    tool_presentation.py, servers/tool_sync.py). No I/O.
├── application/     What the system does, against contracts.
│   ├── contracts/   The interfaces infrastructure must fulfil, grouped by
│   │                subject: persistence/ (UnitOfWork, one repository per
│   │                entity, AuditSink), live_state/ (SessionStore, SignalBus,
│   │                RateLimiter, StreamRegistry, …), upstream/ (UpstreamProbe,
│   │                client factory, OAuth provider), identity/ (OidcProvider,
│   │                metadata fetcher), SecretCipher, ReadinessProbe.
│   ├── metering/    The billing extension point (MeteringHook) and its
│   │                context, decision and idempotency key.
│   ├── management/  ServerService, BundleService, EndpointService, … the
│   │                management-API use cases (NamedResourceService base).
│   ├── auth/ oauth_server/ upstream_oauth/ discovery/ serving/ bootstrap/
│   ├── schemas/     DTOs (Pydantic), one class per file, grouped by resource;
│   │                the OpenAPI document and the web app's TS types come from
│   │                these.
│   ├── settings/    The deploy-time configuration model every layer reads.
│   └── errors/      ServiceError and its subclasses (NotFound, Conflict, …).
├── infrastructure/  One adapter per contract, grouped by technology:
│   ├── postgres/    rows/ (one SQLModel table per entity), SqlAlchemyUnitOfWork,
│   │                SqlAlchemy*Repository mapping rows to entities, the queued
│   │                audit writer, engine plumbing, Alembic migrations/.
│   ├── valkey/      Session and admin-session stores, single-use browser
│   │                state, rate limiters, the signal bus, invalidation pub/sub,
│   │                the refresh lock.
│   ├── fastmcp/     The upstream MCP client factory and the discovery probe.
│   ├── httpx/ oidc/ crypto/ egress/ metering/ readiness/ inprocess/ config/
│   └── memory/      In-memory fakes for every repository and the unit of work;
│                    first-class, and what use-case tests run on.
├── api/             The delivery layer, FastAPI (and, for the MCP edge, the
│   │                MCP protocol library):
│   ├── http/        Controller base, route decorator, providers, ManagementAuth,
│   │                error mapping, pagination, client-IP derivation.
│   ├── management/  controllers/ — the /api/v1 surface.
│   ├── health/      controllers/ — liveness and readiness probes.
│   ├── oauth/       controllers/ — OAuth 2.1 server, admin login, upstream
│   │                connect; pages/ and browser_state/ hold its helpers (README).
│   ├── mcp/         controllers/ — the one MCP route; the rest is the
│   │                Streamable-HTTP edge machinery (README).
│   └── jobs/        Scheduled entrypoints (token purge).
│   Every surface keeps its route classes in controllers/; anything outside
│   such a folder is not a route.
└── main/            The composition root: create_app, CompositionRoot,
                     AppContainer, CompositionOverrides, McpEdgeAssembly, and
                     the OpenAPI export script. The only package that names an
                     adapter beside a use case.
```

## Two kinds of configuration

- **Deploy-time** (`application/settings/`, loaded by
  `infrastructure/config/settings.py` from `BUNDLEMCP_*` env): database and store URLs,
  `public_url`, OIDC client, admin emails, encryption keys, web origins. Fixed
  for the life of the process.
- **Runtime-tunable** (`application/management/config_service.py` + the `config_entries`
  table): timeouts, session lifetime, audit retention. Editable live through
  the API/UI; changes propagate to every replica via the invalidation bus.

## A note on the RESP store: Valkey, not Redis (ADR-0022)

The live-state store ships as **Valkey** (`valkey/valkey:8-alpine`, BSD-3) —
the Linux Foundation's permissively-licensed fork of Redis, chosen so the whole
default stack stays OSI-permissive after Redis's licensing moved to
AGPL/source-available. It is a drop-in RESP server, so:

- the client library is still **`redis-py`** (MIT) — the code imports
  `from redis.asyncio import Redis` unchanged, and the client factory is
  `infrastructure/valkey/client.py`;
- the connection URL keeps the `redis://` scheme and the `BUNDLEMCP_REDIS_URL`
  setting name;
- the Redis key names (`bmcp:…`) are unchanged.

So throughout these docs, `redis-py` / `redis://` / the `bmcp:` keys are the
**client and protocol** (genuinely Redis-named) and stay as written, while the
**store daemon** is Valkey. Any RESP server (Valkey, Redis, Redict, Garnet)
works — point `BUNDLEMCP_REDIS_URL` at whichever you run.

## The one rule worth internalizing first

**No process-local state a request depends on.** Postgres is the durable system
of record (config, tokens, audit); the RESP store (Valkey) holds live
session/stream/rate state. Any replica can serve any request, and a gateway
restart is a non-event for in-flight client sessions. The only replica-local
objects are open streams and in-flight call handles
(`infrastructure/inprocess/stream_registry.py`), and
those are reachable from other replicas through the store-backed `SignalBus`.
This is what the sessions and state-propagation sections of the gateway doc are
really about.

## Where the rest of the documentation lives

- `spec/` — the source of truth: atomic specs with testable requirement IDs
  (`SRV-1`, `EP-3`, `OAS-5`, …). These READMEs cite those IDs.
- `docs/arc42/` — architecture narrative. `docs/adr/` — decision records
  (ADR-0019/0020 explain the service/DTO layering used above).
- `deploy/TESTING.md` — how to run the full compose stack and the test suites.
