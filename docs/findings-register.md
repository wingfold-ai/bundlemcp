# Findings register — repository analysis

**Date:** 2026-09-06 · **Method:** five parallel read-only analyses (core skeleton,
MCP gateway edge, auth/OAuth/crypto, ops/config/observability, frontend/API
contract), each verifying library claims against the installed distributions in
`.venv/` and against live package registries rather than from memory.

This is the register; the OAuth work has its own plan in
[oauth-server-migration.md](oauth-server-migration.md). **§9 records what was
done about each item** (2026-09-06, PRs #23–#33).

---

## 0. The headline

**The auth layer is the area with the *least* reducible code.** It is
well-factored and almost nothing in it has a library equivalent that fits. The
reduction opportunities are concentrated elsewhere:

| Area | Reducible | Dependency cost |
|---|---|---|
| **Frontend** — Nuxt UI used for 3 of ~50 components | **~500 LOC** | zero (already installed) |
| **Tests** — one fixture copy-pasted 12× | **~175 LOC** | zero |
| **Frontend** — error decoder copy-pasted 10× | **~110 LOC** | zero |
| **Test tooling** — a hand-maintained JS twin + Playwright reporting | **~150 LOC** | zero (deletes config) |
| **Core** — `TypeAdapter`, `redis.transaction`, `Page.of()` | **~70 LOC** | zero |
| **Gateway** — SDK method/version tables, AESGCM codec | **~55 LOC** | zero |
| **Auth** — the whole OAuth server | **~220 LOC** | zero, but 2–3 days |

Roughly **1,060 LOC removable with no new dependency at all.** Every package
that would have to be *added* was either rejected as stale or rejected as a
poor fit — see §5.

---

## 1. Bugs

Severity is about consequence, not effort. All were read from source.

### HIGH

**B1 · Upstream OAuth exfiltrates the gateway's client secret to a
remote-controlled URL** — `oauth/upstream_client/httpx_upstream_provider.py`

`gateway/egress.py:42` `check_url_allowed` is imported in exactly **one** place
in the codebase (`gateway/upstream.py:13`). It is not applied at `:26,29`
(discovery fetch, SSRF), at `:34-36` (follows
`data["authorization_servers"][0]`, a URL supplied by the *remote upstream*),
or at `:109-110`, which **POSTs the gateway's `client_secret`** (`:107-108`) to
a `token_endpoint` taken from that same remote document. A malicious upstream
harvests the secret by pointing one field at its own host. UPO-8 (issuer
binding) is specced and unimplemented. *Covered as phase 1 of the OAuth plan.*

**B2 · ID-token `aud` and `iss` are never validated** —
`oauth/oidc/authlib_oidc_provider.py:58-59`

`claims.validate()` is called with no `claims_options`, and Authlib's
`_validate_claim_value()` (`rfc7519/claims.py:62-64`) returns immediately when
no option is configured. So only signature + `exp`/`nbf`/`iat` are checked,
while `:63` reads `claims["iss"]` straight from the token and
`user_provisioning_service.py:37` keys user identity on it. On a shared realm —
ultra-mcp's Keycloak — a token minted for a different client of the same realm
passes. OIDC Core §3.1.3.7 steps 3–4 require both. *Phase 0 of the OAuth plan.*

### MEDIUM

**B3 · Authorization-code and refresh-token replay race** —
`services/oauth_server/authorization_code_grant.py:25,31`

Check-then-write with the commit deferred to `token_service.py:52`. Under
READ COMMITTED two concurrent POSTs both see `used = False` and both get a token
pair. Same shape at `refresh_token_grant.py:27-30`. RFC 9700 §4.14.2 also wants
family revocation on replay; today it returns a bare `invalid_grant`.

**B4 · CSRF origin check is a prefix match** — `api/auth.py:60`

`any(origin.startswith(a) for a in allowed)` accepts
`https://mcp.example.com.evil.test`. The correct idiom already exists in this
repo at `oauth/oidc/post_login_redirect.py:9`.

**B5 · Redirect URIs with an existing query string are corrupted** —
`oauth/authorize_controller.py:44`, `oauth/oauth_error_response.py:33`

`f"{redirect_uri}?{urlencode(params)}"` turns a registered
`https://app/cb?tenant=x` into `...?tenant=x?code=…`; the client never sees
`code`. RFC 6749 §3.1.2 permits query components in registered redirect URIs.

**B6 · DCR rate limit keys on the socket peer, not the client IP** —
`oauth/registration_controller.py:27`

`request.client.host` behind the reverse proxy DEP-1 assumes is the *proxy's*
address for every request, so OAS-12's "10/hour per IP" becomes a global
10/hour and the first ten registrations lock out everyone. The correct helper
exists at `gateway/proxy.py:32`.

**B7 · Auth-failure lockout is advisory, not enforcing** —
`oauth/token_controller.py:51-62`

The credential is fully evaluated by `service.exchange(...)` **first**; the
limiter is consulted only afterwards to decide what to render. A locked-out IP
still gets every guess evaluated, and a correct guess still returns a token at
`:64`. The guard belongs *before* `exchange`.

**B8 · Migration `0001` is not a migration** —
`migrations/versions/0001_initial_schema.py:29`

It calls `SQLModel.metadata.create_all(bind)` against **live** metadata, so
revision 0001 produces a different schema in every release. The authors know:
`0002:19-24` and `0003:57-60` each open with a defensive
`inspect(bind).get_columns(...)` guard explaining it. Consequences:
`--autogenerate` cannot produce a meaningful diff; `0001.downgrade()` does
`drop_all` and will drop tables an old database never had; DEP-5's
backward-compatibility rule is unverifiable when revision 1 is a moving target.

**B9 · The admin session id — a live bearer credential — is written to the log**
— `store/admin_sessions/admin_session_store.py:40`

`log.warning("adminsession.malformed", session_id=session_id)`. That value *is*
the credential, replayable for its 12h TTL. Violates SEC-10 / DOM-3 / spec 51.
The correct pattern is 10 lines away at `store/single_use_state.py:49`, which
logs only a prefix.

**B10 · Frontend never recovers from an expired session** —
`apps/web/app/middleware/auth.global.ts:8`

`refresh()` is called only when `!checked.value`. Once a gateway session expires
mid-SPA-session the middleware never re-checks, so every page shows
*"Request failed"* instead of redirecting to login. A
`response.status === 401 → gotoLogin()` branch in an `openapi-fetch` middleware
fixes it (see R3).

**B11 · `service`-kind API keys silently ignore their endpoint scope** —
`models/api_key.py:53`

`if self.kind == ApiKeyKind.ENDPOINT and self.endpoint_ids:` — a service key
with a populated `endpoint_ids` reaches **every** endpoint. KEY-2 treats scope
and kind as orthogonal.

**B12 · `STATUS_BY_ERROR` is an exact-type lookup** — `api/errors.py:32`

`.get(type(exc), 500)`. Any future subclass — `class
NameCollisionError(ConflictError)` — silently returns 500 instead of 409. Walk
`__mro__`, or put `status` on `ServiceError` as a class attribute (which
`OAuthError` already does, `oauth_error.py:7-10`).

### LOW

**B13 · A controller subclass that overrides a route method without
re-decorating silently loses the route** — `http/controller.py:39-44`.
One `if` in `_routes` would catch it.

**B14 · `/oauth/revoke` has no client auth, no ownership check and no rate
limit** — `oauth/token_controller.py:94-99`. RFC 7009 §2.1 wants client auth
for confidential clients.

**B15 · Unhandled `httpx` errors surface as 500s on both OAuth callbacks** —
`authlib_oidc_provider.py:54`, `httpx_upstream_provider.py:111`. An IdP
returning `error=access_denied` produces an unhandled `HTTPStatusError` rather
than the 400 the `except OidcError` at `login_controller.py:76` was written for.
`login_callback` also never inspects the `error` query parameter.

**B16 · `AuthService.resolve_api_key` commits the caller's transaction** —
`services/auth_service/auth_service.py:45`. Called inside a request-scoped
UnitOfWork, it commits whatever else is pending as a side effect of
authenticating.

**B17 · `PkcePair.verifier` lacks `repr=False`** — `crypto/pkce.py:25`. Every
sibling secret field has it. Same for `TokenRequest.code`/`code_verifier`/
`refresh_token` (`services/oauth_server/token_request.py:10,14,15`).

---

## 2. Inconsistencies

**I1 · `RATE_KEY` is defined twice, with different formats, and the exported one
is dead.** `store/redis.py:14` = `bmcp:rate:{endpoint}:{scope}`;
`gateway/ratelimit/rate_limiter.py:12` = `bmcp:rate:{scope}:{bucket}`. The
second is what runs. The first is re-exported from `store/__init__.py` and
imported by nothing. `store/redis.py:1-5` claims key layout is centralised there
"so the live-state footprint stays auditable" — it isn't. `.claude/docs/module-naming.md`
names `rate_limiter.py` as the correct owner.

**I2 · `LIVE_LOG_STREAM` (`store/redis.py:13`) has zero consumers.** LOG-1 is
unimplemented and this is its only trace.

**I3 · Valkey boundaries bypass Pydantic parsing.** Three sites construct models
with `Model(**json.loads(raw))` instead of `model_validate_json`:
`invalidation_subscriber.py:53`, `session_store.py:33`, `session_store.py:77`.
`.claude/docs/pydantic-models.md` explicitly requires the latter with an
explicit `ValidationError` catch. `session_store.py:77` has **no** error
handling, where `:33` degrades gracefully — so the same class of malformed
record behaves differently depending on which method reads it.

**I4 · `config_registry.coerce` hand-rolls what Pydantic does** —
`services/config_service/config_registry.py:25-41`. 17 lines of `isinstance`
ladders including a manual `bool`-is-`int` guard. `TypeAdapter(t).validate_python(v, strict=True)`
is one line with a better error. `DEFAULTS: dict[str, tuple[Any, type]]` is also
a raw tuple crossing a layer, which ADR-0024 prohibits.

**I5 · `Pagination` is a plain class while its sibling `AuditFilter` is a
`BaseModel`,** used identically as a `Depends()`. `api/pagination.py:8-17` vs
`services/audit_service.py:13-52`. Two mechanisms for one job.

**I6 · Auth resolution is written twice** — `api/auth.py:34-44` and
`api/controllers/me_controller.py:24-38` both run cookie-then-API-key with
different outputs.

**I7 · Two HTML mechanisms for two pages.** Consent is a Jinja template
(`oauth/templates/consent.html`); the upstream-connect success page is an inline
f-string (`upstream_connect_controller.py:32-36`).

**I8 · The frontend hand-writes a DTO the schema already generates.**
`apps/web/app/composables/useMe.ts:1-6` declares a local `Me` interface while
`MeRead` exists in `types/api.d.ts` — and the local one omits `user_id` and
`api_key_id`. Directly violates UI-3. `useMe.ts:15` also uses raw `fetch`
instead of the typed client.

**I9 · The committed `openapi.json` is stale.** Regenerated during this review:
it is missing the `input_required` value on `AuditStatus` and its description
(9-line diff). `openapi:export` and `openapi:types` are separate npm scripts
(`package.json:8-9`) that nothing chains and nothing verifies.

**I10 · Published OpenAPI descriptions contradict the enforced rule.** Name
descriptions say *"lowercase letters, digits and hyphens"*; `NAME_PATTERN` is
`^[a-zA-Z0-9_-]+$` (`models/base.py:16`). And because the rules live in
`AfterValidator`s (`schemas/resource_names.py:17-34`), **no `pattern` reaches
the JSON Schema at all** — so the frontend hard-codes them twice
(`endpoints/index.vue:24-36`, `endpoints/[name].vue:29-41`), including all ten
`RESERVED_ENDPOINT_NAMES`. UI-4 is met by copy-paste, not generation.

**I11 · `spec-map.mjs` is a hand-maintained twin of `spec-map.ts`** — its own
header says *"Keep the two in sync."* Node 24 (which `apps/web/Dockerfile:1`
already runs) executes `.ts` natively via type stripping, and `spec-map.ts`
contains only erasable syntax. The twin exists for no reason.

**I12 · Half of production stdout is not JSON.** `_configure_logging`
(`apps/gateway/main.py:15-26`) configures structlog only; `uvicorn.access` and
`uvicorn.error` keep their default text formatters. There is no
`ProcessorFormatter` bridge.

**I13 · `create_app` never configures logging** (`api/app.py:39`) — only
`app_factory` does. Every test and any library embedder runs on structlog's
default `ConsoleRenderer`.

**I14 · `bootstrap/bootstrap_server.py` is `class BootstrapServer(ServerUpsert): pass`**
— an empty subclass plus an `__all__` entry. `BootstrapBundle` earns its
subclass (it adds `servers`); this one adds nothing.

**I15 · The root `README.md` is still the unmodified "Claude project template"
README.** It describes `.claude/settings.json` and "Use this template on
GitHub". DOC-1 is entirely unmet, and this is the first thing any operator
reads. `spec/README.md` is doing the job.

**I16 · `AuditFilter.criteria() -> list[object]`** (`services/audit_service.py:29`)
returns untyped SQLAlchemy clauses into `Repository.page(*criteria: Any)`
(`store/repository.py:42`) — a contained violation of ADR-0024's
"nothing crosses a layer as an untyped value".

**I17 · `route.py`'s `order` is a process-global counter** (`http/route.py:10`).
Within a class it matches source order, which is all that matters today, but the
docstring's promise holds only accidentally across classes. `cls.__dict__`
preserves definition order since Python 3.6.

---

## 3. Reduction opportunities

Ranked by lines removed per unit of risk. **None of these requires a new
dependency.**

**R1 · Adopt the Nuxt UI components already installed — ~500 LOC**

Current usage across `apps/web/app/`: 31 `UButton`, 8 `UBadge`, 1 `UApp` —
three components. Beside them: **11 hand-written `<table>`** (60 `<td>`, 54
`<th>`), **44 raw `<input>`**, 10 `<select>`, 45 `<label>`, 5 `<form>`, and 4
`window.confirm()`. Nuxt UI v4 ships `UTable` (TanStack Table v8: sorting,
filtering, pagination, virtualization), `UPagination`, `UForm` +
`UFormField` with Standard Schema validation, `UModal`, and `useToast()`.

`app/assets/css/main.css:5-22` reimplements table/input/label/card surfaces in
raw Tailwind and does it *worse* — hard-coded `border-gray-300` and
`bg-white dark:bg-gray-900` instead of design tokens, so the wireframe styling
does not follow the color mode that `UButton`/`UBadge` on the same page do.

This also converts "no pagination on any list" from a rewrite into a prop —
every list currently hard-codes `{offset: 0, limit: 100}` and silently truncates
at 100 rows, although the backend returns `total` on every page and allows 500.

**R2 · One `app_client` fixture instead of twelve — ~175 LOC**

`ASGITransport` + `create_app(settings, overrides=CompositionOverrides(...))` +
service-key seeding is copy-pasted in `test_api.py`, `test_audit_api.py`,
`test_gateway.py`, `test_modern_edge.py`, `test_mrtr.py`, `test_oauth.py`,
`test_oidc.py`, `test_relay.py`, `test_runtime_config.py`, `test_upstream_call.py`
(×2), `test_upstream_connect.py`, `test_web_origins.py`. The `test_api.py:20-42`
and `test_audit_api.py:20-42` versions are near-identical. Hoisting one
parameterisable fixture into `conftest.py` means a composition-wiring change
touches one file, not twelve. **Highest-value test refactor available.**

**R3 · Register one `openapi-fetch` middleware — ~110 LOC, and fixes B10**

The error-shape decoder is byte-identical in **ten** files (`errText` in
`servers/index.vue:9`, `servers/[name].vue:14`, `bundles/index.vue:9`,
`bundles/[name].vue:17`; `detailMsg` in `endpoints/index.vue:38`,
`endpoints/[name].vue:43`, `api-keys.vue:13`, `users.vue:14`, `audit.vue:17`,
`settings.vue:8`), plus ~40 manual `errorMsg.value = detailMsg(error)`
assignments and a `<p v-if="errorMsg">` banner in each. `client.use({onResponse})`
centralises it — and is where the 401 → login branch belongs. `healthColor` is
also duplicated (`servers/index.vue:33`, `bundles/[name].vue:110`).

**R4 · Configure a Playwright reporter, delete the staging pipeline — ~150 LOC**

`playwright.config.ts` sets **no `reporter`**, so the default (`list`/`dot`)
never writes a report. That is the actual cause of `stage-recordings.mjs`, whose
header claims *"Playwright wipes test-results/ at the start of every run, so
recordings are copied out"* — the HTML reporter already stages every attachment
durably into a content-hashed `data/` folder. One config line replaces the
copy/rename logic (~55 LOC); `spec-map.mjs` deletes outright (62 LOC, see I11);
`gen-testmap.mjs`'s traceability matrix is real value but belongs in
`testInfo.annotations` + a ~40-line custom Reporter rather than a JSON side-file
joined by **a regex on a truncated directory name** (`stage-recordings.mjs:34`).

Worth noting the ratio as it stands: **665 lines of bespoke test infrastructure
against 383 lines of tests.**

**R5 · Core skeleton, four small wins — ~70 LOC**

- `config_registry.coerce` → `TypeAdapter` (~15, and fixes I4's tuple violation)
- `SessionStore._update` (`store/sessions/session_store.py:64-84`) hand-rolls
  WATCH→GET→MULTI→EXEC→retry-on-`WatchError`. **redis-py 8.0.1, already
  installed**, ships `Redis.transaction(func, *watches, value_from_callable=…)`
  which is that loop (~12)
- `Page.of(rows, total, offset, limit, read_model)` classmethod — the
  `Page(items=[X.from_entity(r) …])` block is written five times
  (`named_resource_service.py:73`, `api_key_service.py:37`, `audit_service.py:66`,
  `user_service.py:25`, `server_service.py:62`) (~20)
- `Pagination` → `BaseModel` (~8, fixes I5) · dead constants (~6, fixes I1/I2)

**R6 · Gateway: delegate deeper into `mcp_types` — ~55 LOC and a real
maintenance win**

`mcp_types` 2.1.1 is already installed and ships **per-revision method tables**:
`CLIENT_REQUESTS` / `CLIENT_NOTIFICATIONS` keyed by `(method, version)`
(`mcp_types/methods.py:57,129`), `HANDSHAKE_PROTOCOL_VERSIONS` /
`MODERN_PROTOCOL_VERSIONS` (`version.py:33,41`), and `CACHEABLE_METHODS` (`:421`).

Against which bundlemcp hand-maintains its own version lists
(`gateway/protocol_version.py:10-11`) and two hard-coded denylists
(`dialect/handshake_dialect.py:19`, `dialect/modern_dialect.py:12-14`).
Deriving `WireDialect.allows()` from the SDK's allowlist — with bundlemcp's
frozensets reduced to the gateway's deliberate *exceptions* — directly
de-risks **PROT-22**, which ADR-0011 itself flags as a known cost
("New MCP protocol revisions must be tracked manually on the server edge").

Separately: `mcp.server.request_state.AESGCMRequestStateCodec` (`:187`) is
public and server-free — AES-256-GCM with an HKDF key ring, a `kid` bound under
the tag, and multi-key rotation. Swapping it for `TokenCipher` in
`mrtr/request_state.py` drops the local `arguments_digest` (~15 LOC) in favour
of the SDK's canonicalisation, so gateway and SDK peers agree by construction.

**R7 · Frontend state — ~14 LOC and one latent SSR bug**

`useMe.ts:8-9` declares `ref`s **outside** the composable — a cross-request
singleton the moment SSR is ever enabled (one user's identity served to
another). `useState('me')` is the Nuxt-native fix at the same line count. Drop
the hand-written `Me` interface with it (I8).

**R8 · Delete `bootstrap/bootstrap_server.py` — 7 LOC, 1 file** (I14).

---

## 4. Unimplemented but specced

These are gaps, not bugs — listed because several are cheap and two have
ready-made implementations sitting in already-installed packages.

| Req | Feature | Note |
|---|---|---|
| **DOC-1** | Repository README | still the template README (I15) |
| **DOC-2** | Six operator guides in `docs/` | none exist; DEP-8's backup runbook and SRV-7's stdio-sidecar doc depend on them |
| **OBS-1** | Request log lines with request id | there are **no** request log lines at all, and no request ID anywhere |
| **OBS-2** | Metrics | no `/metrics` route. `gateway/metrics.py` is a 29-line `defaultdict(int)` with one method, `inc(name, amount)` — **structurally incapable** of the labelled histograms and gauges OBS-2 specifies |
| **OBS-3 / DEP-4** | `/readyz` false until schema-current | `health_controller.py:17-24` checks Postgres + Valkey only; during a rolling deploy a replica on a stale schema reports ready |
| **AUD-3** | Queue-overflow metric | `AuditWriter.dropped` (`gateway/audit.py:20,44`) is incremented and never exported |
| **AUD-5** | Audit retention purge | `audit_retention_days` is registered at `config_registry.py:20`; its only other reference in the repo is a Playwright selector. No purge job. `oauth/token_purger.py` is a working template |
| **AUD-6** | Audit CSV export | frontend hand-rolls a CSV writer (`audit.vue:64-106`); no backend route |
| **LOG-1/2** | Live logs | one dead constant + a 16-line placeholder page |
| **INS-1..4** | Inspector | 16-line placeholder page, no backend |
| **EXP-1..6** | Config export/import | **absent entirely.** Cheap: export = read services → build `BootstrapDocument` → `model_dump_json()`; import = `model_validate_json` → `BootstrapRunner.apply()`, which is *already* transactional via `uow.atomic()`. Only EXP-2 secret placeholders and the dry-run report are new (~120 LOC). Add `version` to `BootstrapDocument` **now**, before documents exist in the wild |
| **BOOT-1** | Inline `BUNDLEMCP_BOOTSTRAP` JSON | only the file source exists; `yaml.safe_load` parses JSON, so this is a ~6-line branch — and inline JSON is the compose-native form for the ultra-mcp consumer |
| **BOOT-3** | `api_keys` in the bootstrap document | only the narrower `initial_service_key` exists |
| **OAS-13** | Client ID Metadata Documents | `fastmcp/server/auth/cimd.py` implements it — ~450 lines avoided |
| **OAS-14** | RFC 9207 `iss` | `fastmcp/server/auth/redirect_validation.py:68` `build_client_redirect` adds it *and* fixes B5 |
| **UPO-8** | Upstream issuer binding | see B1 |
| **DEP-11** | Publish images to ghcr.io on tags | `.github/workflows/` has only `ci.yml`; the `image` job builds the gateway and discards it, and never builds `apps/web/Dockerfile` |
| **TM-5** | Stale/overridden curation badges | `BundleToolRead` has no staleness field |
| **UI-3** | Query caching layer | no TanStack Query, no Pinia, no `useState`; every mutation triggers a manual full refetch |

---

## 5. Packages evaluated and rejected

Recorded so nobody re-proposes them. Recency checked at review time.

**Stale — would be a liability:**

| Package | Last release | Considered for |
|---|---|---|
| `fastapi-utils` (cbv) | 2024-11 | `http/Controller` |
| `fastapi-class` | 2025-01 | `http/Controller` |
| `fastapi-restful` | 2024-05 | `http/Controller` |
| `starsessions` | 2024-10 | admin sessions |
| `fastapi-sessions` | **2021-09** | admin sessions |
| `aiocache` | 2024-09 | invalidation |
| `fastapi-health` | **PyPI 2021-08**, GitHub 2023-07 | `/healthz` |
| `encode/broadcaster` | **archived on GitHub** | live logs |
| `passlib` | effectively unmaintained | API-key hashing |

**Alive but wrong fit — the reason matters more than the date:**

- **Authlib AS framework** — `grep -rn "async def" authlib/oauth2/` returns zero
  matches; integrations are Flask and Django only.
- **`fastapi-pagination`** (very active) — `resolve_params()` reads a
  request-scoped **ContextVar** and `add_pagination()` mutates every route at
  startup. Pagination happens in `services/`, which has no request context by
  contract.
- **`advanced-alchemy`** (monthly releases, explicit SQLModel support) —
  genuinely better than `store/repository.py`, but a 100+-module dependency to
  delete 58 lines. The N+1 patterns the thin repository invites are the real
  problem, and they need fixing either way.
- **`dependency-injector` / `svcs` / `wireup`** — `_compose()` is not doing
  dependency *resolution*; it is ordered async resource acquisition with
  symmetric teardown, and `AsyncExitStack` is already the right primitive.
- **`SQLAlchemy-Continuum` / `-History`** — row-versioning libraries.
  `AuditRecord` is a domain event per tool call (`duration_ms`, `denied_reason`,
  `session_id`), not a version history of any row.
- **FastMCP `RateLimitingMiddleware`** — an unbounded in-process
  `defaultdict` of token buckets (`rate_limiting.py:137`) raising `-32000` with
  no HTTP 429 and no `Retry-After`. **RATE-2 forbids in-process counters by
  name.**
- **`limits`** — its async Redis storage is **coredis**, a second Redis client
  in the process, against ADR-0022.
- **`nuxt-auth-utils` / `@sidebase/nuxt-auth`** — the first stores session state
  in a sealed cookie it owns; the second persists an access token in JS. Both
  are *downgrades* from a gateway-issued `HttpOnly` cross-origin session cookie
  with server-side revocation (ADM-6).
- **`nuxt-open-fetch`** — pre-1.0 with an explicit API-change warning, 6-month
  gap, maintainer handover; its main benefit is SSR-shaped and this app is
  `ssr: false`.
- **`polyfactory` / `respx` / `pytest-httpx`** — the repo already mocks at a
  better seam (`CompositionOverrides.client_factory`), and test data here is
  domain fixtures whose specific values *are* the assertion.
- **Official `@modelcontextprotocol/inspector` embedded in the UI** — it ships
  its own Node proxy backend that connects to MCP servers directly. INS-3
  requires the opposite: the browser never talks to upstreams. It **is** the
  right answer as a CI tool, where `--cli` would replace the hand-written
  `openMcp()` in `apps/web/tests/flows.ts:96-155` (~60 LOC including a
  hand-rolled SSE-vs-JSON body sniffer at `:85-92`).

**Worth adding:**

- **`prometheus-client`** — the only way to satisfy OBS-2; `Counters` cannot
  grow labels or histograms without becoming a metric registry.
- **`sse-starlette`** (released the day before this review) — for the *admin*
  live-log stream only. The MCP edge's 12-line `sse.py` keeps byte-exact control
  and stays.
- **`testcontainers[postgres]`** behind a marker — see §6.
- **OpenTelemetry** as an optional `[otel]` extra — for a *proxy*, one trace
  spanning inbound → endpoint resolution → session load → upstream call is the
  single most valuable diagnostic artifact, and OBS-5 already specs it as
  optional and `OTEL_*`-driven. Caveat: contrib instrumentations are on beta
  versioning (`0.65b0`), which is why the optional-extra shape matters.

---

## 6. Two structural risks

**SQLite in tests, Postgres in production.** `conftest.py:14` uses
`sqlite+aiosqlite://`. Concretely divergent today:

1. The DOM-4 name CHECK constraints are **Postgres-only**
   (`0001_initial_schema.py:28-37`, guarded by a dialect check) and exercised by
   no test.
2. The DEP-4 migration advisory lock (`migrations/env.py:42-60`) — the entire
   multi-replica guard — is skipped on non-Postgres and has **no test at all**.
3. `sa.JSON` maps to Postgres `json` (not `jsonb`) and to SQLite text.
4. `models/utc_datetime.py` exists specifically because SQLite drops `tzinfo`.
5. **The hermetic suite never runs the migrations** — `conftest.py:21` calls
   `create_all`. Migration correctness is covered only by the compose job.

The verdict is *keep the SQLite suite* — it is fast, hermetic per ARC-14, and
gates every change. But add `testcontainers[postgres]` behind a
`@pytest.mark.postgres` marker with ~80 lines covering exactly these five rows,
run in CI's existing Docker-capable `integration` job.

**No CI job touches the frontend at all.** `.github/workflows/ci.yml` has
`backend`, `diagrams`, `image`, `integration` — no `npm ci`, no `nuxt typecheck`,
no eslint, no Playwright, and the `image` job never builds
`apps/web/Dockerfile`. The stale `openapi.json` (I9) is the observable symptom.
A regenerate-and-`git diff --exit-code` step is ~4 lines of YAML and makes the
"generated types, never hand-written" architecture self-enforcing instead of
aspirational. **Cheapest high-leverage fix in this register.**

---

## 7. Deployment hygiene

- **No `.dockerignore` anywhere.** Build context is the repo root
  (`docker-compose.yml:134-136`), which here contains `.venv/`, `.git/`,
  `.import_linter_cache` and `apps/web/node_modules/`. One 8-line file; largest
  build-time win available.
- **Both images run as root.** `node:24-alpine` already ships a `node` user.
- **No `HEALTHCHECK` in either Dockerfile, and no `healthcheck:` on `gateway`
  or `web` in compose** — while postgres, valkey and keycloak all have one.
  `web` uses a bare `depends_on: [gateway]` rather than
  `condition: service_healthy`. DEP-3 requires the probes wired; CI's manual
  readiness-poll loop (`ci.yml:64-68`) is working around this.
- **The runtime stage copies source** (`apps/gateway/Dockerfile:14`) because
  `uv sync` installs the workspace member editable. `--no-editable` lets the
  runtime image drop the source tree.
- **No `restart:` policy** on any compose service.
- **Dev stack and the private ultra-mcp fleet share one compose file**
  (`docker-compose.yml:53-131`), so CI enumerates services in shell to avoid
  private images. Compose `profiles:` expresses this natively.
- **Dev secrets have working inline defaults** — `${VAR:-bmcp_sk_devservicekey…}`
  at `:81,152` and a real Fernet key at `:156`. Fine for dev; the shape means a
  misconfigured production compose boots with a known key rather than failing.

---

## 8. What is genuinely well done

Worth recording, because the register above is one-sided.

- **The layer contract is mechanically enforced and honoured.**
  `uv run lint-imports`: 371 files, 1553 dependencies, both contracts kept,
  **zero `ignore_imports` exceptions**. `services/` truly cannot import FastAPI —
  `AuditFilter` is a bare `BaseModel` in the service and the *controller*
  attaches `Depends()` to it.
- **ADR-0011's central bet re-verifies against FastMCP 4.0.3 / SDK 2.1.1.** The
  SDK's session manager still holds sessions in a process-local dict
  (`streamable_http_manager.py:102-107`) with no store seam, and `stateless=True`
  sets `can_send_request=False`, which would delete the PROT-4 relay. Two
  further blockers have since become as binding: one manager per `Server` versus
  endpoints as runtime DB rows, and per-endpoint token audiences.
- **This is not a hand-rolled protocol stack.** The edge already delegates the
  modern-era validation ladder, the error→status table, the mirrored-header
  validator, the MRTR result types and the subscription filter to
  `mcp.shared.inbound` / `mcp.types` — 15 import sites. What remains is a thin
  shell: 39 lines of dispatch, 44 of rate limiting, 12 of SSE framing.
- **`CompositionRoot` unwinds its `AsyncExitStack` explicitly on a failed
  `__aenter__`** (`api/composition.py:61-64`) — `__aexit__` never runs for one.
  Most codebases get this wrong.
- **`migrations/env.py`'s advisory lock rolls back before unlocking** so the
  *original* migration error propagates (`:56-60`). That comment reflects a bug
  someone already hit.
- **`ClockedFakeRedis`** (`tests/conftest.py:38-64`) pins `FakeRedis.TIME`
  because the limiter buckets on *server* time. No library provides this and
  `freezegun` would not help.
- **94 distinct requirement IDs** appear across the unit tests, always in a
  docstring — the spec-to-test traceability is real.
- **Secret-handling discipline** — `TokenCipher.__repr__` redacts,
  `repr=False` on secret fields, MultiFernet rotation with fail-closed
  decryption, and "no keys configured ⇒ upstream OAuth is off" as an explicit
  deployment state rather than a crash.

---

## 9. Status (2026-09-06)

Every item was either implemented in one of the PRs below or evaluated and
left, with the reason. PR #22 (already open when this register was written)
had implemented OAS-13, OAS-14 and UPO-8, which the register lists as gaps.

| PR | Base | Contents |
|---|---|---|
| #23 `fix(oidc)` | #22 | Phase 0: joserfc, `iss`/`aud`/`exp`/`sub` validated (B2), IdP HTTP errors → 400 (B15), `repr=False` (B17), session id no longer logged (B9), egress on the IdP URLs; ADR-0031 |
| #24 `fix(oauth)` | #23 | Phase 1: egress on the upstream OAuth chain (B1, ADR-0032), atomic burn and rotation + family revocation with migration 0005 (B3), lockout before evaluation (B7), exact-origin CSRF (B4), DCR limit per forwarded IP (B6), `build_client_redirect` (B5) |
| #31 `fix(oauth)` | #24 | Revocation requires client authentication (B14) |
| #25 `refactor(core)` | main | I1–I7, I12–I14, I16, I17, B11, B12, B13, R5, R8 |
| #26 `test` | main | R2: one `serving()` harness |
| #27 `refactor(gateway)` | main | R6: version and method tables from `mcp_types` |
| #28 `chore(deploy)` | main | §6 frontend CI job + OpenAPI diff check, §7 hygiene, I9 |
| #29 `refactor(web)` | main | R3, R7, B10, I8, I10, plus contract fixes `nuxt typecheck` surfaced |
| #30 `fix(migrations)` | main | B8: frozen 0001; one real model/migration drift fixed |
| #32 `feat(bootstrap)` | main | BOOT-1 inline JSON, document `version`, README (I15 / DOC-1) |
| #33 `refactor(e2e)` | main | I11 and the reporter half of R4 |

**Evaluated and not done, with reasons**

- **Phase 2 of the OAuth plan (`mcp.server.auth` handlers).** The plan's own
  gate is that the six regression tests must not change. Reading the SDK:
  `AuthorizationHandler` can only redirect from `provider.authorize()`, so
  the consent page becomes an extra hop and the `_authorize` helper behind
  those tests has to change; SDK-generated error redirects carry no `iss`
  (OAS-14 regression for the errors the SDK raises itself); the
  `ClientAuthenticator` compares plaintext secrets, so the subclass would
  reimplement `OAuthClientAuthenticator`. Net protocol code removed would be
  close to zero. The one behaviour change the plan recommended (revocation
  requires client auth) is in #31. Details in
  [oauth-server-migration.md §"Phase 2 — evaluation"](oauth-server-migration.md).
- **R6, the `AESGCMRequestStateCodec` swap.** The codec seals bytes and
  nothing else; the binding logic the register wanted to drop lives in the
  SDK's `RequestStateBoundary`, which is tied to `ServerRequestContext`. No
  peer ever unseals our state. See #27.
- **R1, Nuxt UI adoption across the eleven tables.** A UI rewrite that needs
  the Playwright suite against the compose stack to verify; not attempted
  without it. #29 removes the copy-pasted plumbing it would have shared.
- **R4, replacing `stage-recordings.mjs` with a custom Reporter.** The
  spec-linked gallery is product value from #1; the HTML reporter is
  configured so recordings are durable, the gallery stays. See #33.
- **B16, `resolve_api_key` commits.** Authentication runs before any handler
  work, so nothing unrelated is pending at that commit; a separate connection
  for the touch would break the SQLite test pool. Left as is.
- **§4 gaps not started:** DOC-2, OBS-1 request ids, OBS-2 metrics
  (`prometheus-client`), OBS-3/DEP-4 schema-current readiness, AUD-3, AUD-5,
  AUD-6, LOG-1/2, INS-1..4, EXP-1..6 (only the `version` field landed),
  BOOT-3 `api_keys`, DEP-11 image publishing, TM-5, UI-3 caching. §6's
  `testcontainers[postgres]` marker was not added; #30 verified the migration
  chain against Postgres by hand and notes the CI step to add once #28 lands.
