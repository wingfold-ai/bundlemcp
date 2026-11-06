# Design

## Context

See proposal.md, "Why". Facts from the current tree that shape the approach:

- **What the fleet tests prove.** Two of the five tests in `tests/integration/test_fleet_bundles.py`
  (`test_seo_bundle_serves_psi_tools_with_api_key`, `test_dataforseo_tools_listed`) prove nothing the echo smoke tests
  do not already prove. The other three need an upstream that does one of the following:
  - introspects a forwarded bearer (seo-gsc);
  - refuses discovery without a credential (seo-gsc, through its static `authorization` header);
  - receives `X-MCP-User` (hyperframes).
- **The fleet seed's static header breaks under `deploy/stack.sh`.** `seed.fleet.yaml` puts the published dev
  service key, `bmcp_sk_devservicekey…`, in a literal static header. `deploy/stack.sh` replaces that key with a
  generated one ([DEP-13](../../specs/deployment/spec.md)), so on a stack started that way the seeded header no
  longer authenticates. A seed has no way to reference an environment variable in a header value: `static_headers`
  takes a string or a `$secret` reference, and only API keys have `value_from_env`.
- **How callers authenticate in the tests.** The integration helpers send API keys as `Authorization: Bearer …`, so
  with `authorization → authorization` an API-key caller's key is forwarded and introspects as `api_key:<id>`
  ([AUTH-5](../../specs/auth/spec.md)).
- **What uses the echo server.** Its tool list is what the quickstart, the `demo`, `claude` and `chatgpt` endpoints
  and the curation browser scenario (`apps/web/tests/curation.spec.ts`) see. The overhead report
  (`test_overhead_budget.py`) calls it directly on host port 9100.
- **Lists that name every example image:**
  - the hadolint step in `ci.yml`;
  - `.github/dependabot.yml` (docker directories);
  - `test_runtime_versions.py`, which checks that each example uses the declared Python
    ([ARC-2](../../specs/architecture/spec.md)).

## Goals / Non-Goals

**Goals:**

- Every behaviour the fleet tests meant to cover runs in CI, and runs more strictly. The `X-MCP-User` value and the
  introspected `sub` are asserted, not just "tools/list answers".
- The development stack works the same whether it is started by plain compose (CI) or by `deploy/stack.sh` with
  generated secrets.
- After the change, `grep -rni fleet` finds only "fleet-wide" (the discovery lock and ADR-0063) and archived OpenSpec
  changes.

**Non-Goals:**

- No change to gateway behaviour. Every requirement the tests cite (AUTH-5, AUTH-27, AUTH-29, AUTH-30, AUTH-31,
  UPS-17) is already implemented.
- No replacement for the private servers' own features (Google Search Console data, rendering). They are not gateway
  behaviour.
- No rewrite of git history, and no edit to the ADRs that mention seo-gsc or hyperframes.
- The maintainer's private deployment with the real servers lives outside this repository and is not planned here.

## Decisions

### One new example upstream; echo stays unchanged

`examples/identity-demo-mcp` covers introspection, the static discovery header, `X-MCP-User` and header mapping in
one server. It is registered in its own bundle and endpoint, `identity`.

- *Alternative: add a `whoami` tool to echo, plus a separate introspection server.* Rejected. It changes the tool list
  of the demo bundle, so the quickstart and its three endpoints change, and every scenario that names echo's tools
  needs review. Two servers would also do the work of one.
- *Alternative: put the identity demo in the `demo` bundle.* Rejected for the same reason. Its discovery and calls
  also depend on the gateway's own introspection, so it would make the quickstart's bundle fail in ways a first-time
  user cannot read.

### The demo refuses requests without a credential, and discovery uses a demo-only token

The demo accepts a request if its bearer is either of these:

- the fixed discovery token it is configured with (`DISCOVERY_TOKEN`), which it reports as the caller `discovery`;
- a token that the gateway's `/oauth/introspect` reports `active`.

Anything else gets `401`. The seed gives the upstream a static header, `authorization: Bearer <discovery token>`. At
call time the forwarded `authorization` replaces it, which the gateway already does.

- *Alternative: the static header carries the service key, as with seo-gsc.* Rejected, because it breaks under
  `deploy/stack.sh` (see Context). It would also put a gateway credential in the seed, where DEP-13 removes published
  credentials.
- *Alternative: let discovery through unauthenticated.* Rejected. Then nothing proves the static header is sent on
  discovery.
- **Why the token is safe to publish.** It is a credential of the demo alone. It unlocks the demo's own tool list and
  a `whoami` that reports "discovery". The demo is not published on a host port, so the token grants nothing on the
  gateway and opens no path outside the compose network. DEP-13's rule covers the gateway's service key, the
  encryption key and the IdP password, and this token is none of them.

### Introspection with the stack's service key, read from the environment

The demo calls `INTROSPECTION_URL` (`http://gateway:8000/oauth/introspect`) as an RFC 7662 client, with client id
`bundlemcp` and the service key as the client secret. In compose that secret is
`${BUNDLEMCP_INITIAL_SERVICE_KEY:-<dev default>}`, the same expression the gateway's own setting uses. So both the CI
stack and a `stack.sh` stack with a generated key work without editing the seed
([UPS-31](../../specs/upstreams/spec.md)).

### A small ASGI check in front of the FastMCP app, not FastMCP's token verifier

The credential check is a few lines of middleware in the example's `server.py`. `whoami` reads the request headers
through FastMCP's HTTP request dependency, with all headers included, so `authorization` and `x-mcp-user` are visible.

- *Alternative: FastMCP's introspection token verifier.* Rejected for two reasons:
  - it cannot also accept the discovery token;
  - its `401` carries OAuth protected-resource metadata. The gateway's inspection would then classify the server as
    `upstream_oauth` ([UPS-11](../../specs/upstreams/spec.md)) instead of `static_headers`.

  A bare `401` keeps the registration what the seed says.

### What `whoami` returns

A JSON object with these fields:

| Field | Value |
|---|---|
| `caller` | The introspected `sub`, or `discovery` |
| `client_id` | From introspection |
| `has_oidc_subject` | Whether `oidc_iss` and `oidc_sub` are present |
| `x_mcp_user` | The value received |
| `tenant` | The value of `x-tenant`, the upstream name of the mapped `x-tenant-id` |
| `header_names` | The sorted names of every header received |

It never returns the value of `authorization` or any other credential header. The demo logs no header values.

The tests check one invariant: for both an OAuth caller and an API-key caller, `caller` equals `x_mcp_user`. With
`BUNDLEMCP_IDENTITY_SUBJECT=internal`, both are the gateway's subject for the caller (AUTH-5, AUTH-29). That proves
both paths without the test having to look up user or key ids.

### Tests

`tests/integration/test_identity_forwarding.py` has no marker, and each test cites its code:

| Test | What it checks | Code |
|---|---|---|
| discovery through the static header | `POST /api/v1/upstreams/identity-demo:refresh-tools` returns `error: null` and `discovered > 0` | UPS-17, AUTH-5 |
| forwarded bearer is introspected | An OAuth token for the `identity` endpoint, from the DCR, PKCE and consent helper in `test_oauth_flow.py`, gives `caller == x_mcp_user`, no `api_key:` prefix, and `has_oidc_subject` true | AUTH-30, AUTH-5 |
| API-key caller | `caller` starts with `api_key:` and equals `x_mcp_user` | AUTH-5 |
| spoofed identity header | Sending `X-MCP-User: spoofed` returns `x_mcp_user == "api_key:…"` | AUTH-29 |
| header mapping | `X-Tenant-Id: tenant-42` and `X-Unlisted: 1` give `tenant == "tenant-42"`, and `x-unlisted` is absent from `header_names` | AUTH-27 |
| no crossing | OAuth, API key, OAuth, API key on one gateway: each reply reports its own caller | AUTH-31 |

The OAuth token helper `_oauth_token_for` moves out of the deleted fleet test into `tests/integration/helpers.py`, so
the new tests and any later ones share it.

### Removing the fleet

The removal follows the checklist in tasks.md, group 5. Three details need care:

- **`BUNDLEMCP_SEED_FILE` is kept.** The gateway's `BUNDLEMCP_BOOTSTRAP_FILE` still reads it, so an operator can point
  the dev stack at a seed of their own. Only the fleet comment and the second mount go. The variable stays documented
  in `.env.example` without the fleet example.
- **The image-pin test loses its exception.** `FLEET_PROFILE`, `OPERATOR_CHOSEN` and the fixture that asserts a
  floating fleet image passes are removed. The fixture is turned around to show that a variable-chosen default without
  a digest fails (DEP-15).
- **`test_fleet_seed_extends_the_demo_seed_unchanged` is deleted.** In its place, a hermetic test loads
  `deploy/seed.yaml` and asserts the identity demo sits only in its own bundle (DOC-3).

### DEP-15's fleet scenario is deleted by hand in the implementation PR

OpenSpec will not let a MODIFIED requirement drop a scenario: both `validate` and `archive` refuse a block that lacks
one of the current spec's scenarios. DEP-15's scenario "An operator-chosen fleet image may float" has to go, so the
implementation PR deletes that one scenario from `openspec/specs/deployment/spec.md`, in the same commit as the
image-pin test loses its exception. After that the delta's MODIFIED DEP-15 validates, and archiving replaces the rest
of the block. Until then, `openspec validate` reports this one error on the change.

- *Alternative: retire DEP-15 and add the rule again as DEP-18.* Rejected. It moves every citation of DEP-15 and loses
  the requirement's history, all for one scenario.
- *Alternative: keep the scenario name with a new body.* Rejected. The title would say the opposite of the scenario.

## Risks / Trade-offs

- **The demo checks less than a real introspecting server could.** It is maintained in this repository, so a gateway
  change that breaks a real upstream's expectations could pass if the demo is too lenient. → It uses the same RFC 7662
  call seo-gsc makes, with HTTP Basic client authentication, and the tests assert exact values, not just "an answer".
- **Discovery at boot can race the demo's startup**, as it does with echo. → CI forces its discovery in the same step
  that forces echo's, with the same retry loop.
- **The demo depends on the gateway's introspection at call time.** If introspection breaks, the `identity` endpoint
  fails while `demo` still works. That is the intended signal, and the quickstart's bundle is unaffected.
- **Maintainers lose `--profile fleet`.** → The proposal makes moving it to the private deployment a precondition.
  Nothing in the repository depends on the fleet.
