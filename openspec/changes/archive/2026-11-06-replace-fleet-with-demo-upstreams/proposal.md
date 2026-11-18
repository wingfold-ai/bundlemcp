# Proposal

## Why

Three identity-forwarding behaviours have no test that CI runs: forwarding a caller's bearer to an upstream that
introspects it ([AUTH-27](../../specs/auth/spec.md), [AUTH-30](../../specs/auth/spec.md)), authenticating tool
discovery through a static `authorization` header ([AUTH-5](../../specs/auth/spec.md)), and the injected
`X-MCP-User` header ([AUTH-29](../../specs/auth/spec.md)). Their only end-to-end tests,
`tests/integration/test_fleet_bundles.py`, run against four of the maintainers' own MCP servers, the
"fleet". The fleet sits behind `--profile fleet` and private
images, so CI skips those tests with `-m "not fleet"`. Locally they need real Google OAuth and paid
third-party credentials. Even then, the X-MCP-User test checks only that `tools/list` answers, not the header.

The repository is about to become public. The fleet does not belong there: outsiders see services, seed entries and
documentation for images they cannot pull. On 2026-11-02 the maintainer decided to move what the fleet tests cover
onto dummy servers in `examples/`, then remove the fleet from the repository.

## What Changes

- **A new example upstream, `examples/identity-demo-mcp`.** It is a small MCP server that reports what it learns about
  its caller. It introspects the bearer it receives against the gateway's `/oauth/introspect`, authenticating with the
  stack's service key, exactly as the fleet's introspecting server did. Its `whoami` tool returns the introspected `sub`
  and `client_id`, the `X-MCP-User` value, the value of one forwarded tenant header, and the names of the other headers
  it received. It never returns a token or a header value that is a credential.
- **The demo seed registers it.** `deploy/seed.yaml` adds the upstream `identity-demo` with these settings:
  - `forward_headers`: `authorization → authorization`, `x-tenant-id → x-tenant`;
  - a static discovery header;
  - its own bundle and endpoint, `identity`, accepting `oauth` and `api_key`.

  The `demo`, `claude` and `chatgpt` bundles and endpoints, and the echo server, stay exactly as they are.
- **The core compose stack runs it** with no profile. CI forces its discovery the same way it forces echo's.
- **New integration tests**, with no marker, replace `test_fleet_bundles.py`:
  - discovery passes the static header ([UPS-17](../../specs/upstreams/spec.md));
  - an OAuth caller's forwarded bearer is introspected to the user's `sub`, and an API-key caller's to `api_key:<id>`
    ([AUTH-5](../../specs/auth/spec.md), [AUTH-30](../../specs/auth/spec.md));
  - a mapped header arrives under its upstream name and an unlisted one does not
    ([AUTH-27](../../specs/auth/spec.md));
  - a spoofed `X-MCP-User` is replaced ([AUTH-29](../../specs/auth/spec.md));
  - two callers on one upstream each see only their own identity ([AUTH-31](../../specs/auth/spec.md)).
- **The fleet is removed** from the repository:
  - `deploy/seed.fleet.yaml`, `deploy/seaweedfs/`, and the five fleet services and two volumes in
    `deploy/docker-compose.yml`;
  - the fleet lines in `deploy/.env.example` and `deploy/TESTING.md`, and the `fleet` pytest marker;
  - `-m "not fleet"` and `--grep-invert @fleet` in CI;
  - the fleet notes in the README, CONTRIBUTING, `docs/self-hosting/bootstrap.md` and `docs/arc42`;
  - the fleet example servers in `docs/integrate/upstream-identity.md`, which point to `identity-demo` instead;
  - the fleet exception in the image-pin test.
- **Modifies DEP-15.** Every compose image is pinned to a digest, without the operator-chosen fleet exception.
- **Modifies UI-13.** There is one stack, so the "stack without the fleet profile" wording and the title-marker
  exclusion go.
- **Modifies DOC-3.** The demo seed also registers the identity demo.
- **Adds DEP-16.** The dev stack runs no service whose image CI cannot pull or build.
- **Adds DEP-17.** The integration suite verifies identity forwarding against the identity demo on every pull
  request.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `deployment`: modifies DEP-15 (drops the fleet exception); adds DEP-16 (no service CI cannot run) and DEP-17
  (identity forwarding verified in CI against a demo upstream).
- `admin-ui`: modifies UI-13 (one stack, no title-marker exclusion).
- `documentation`: modifies DOC-3 (the demo seed also registers the identity demo, with its own bundle and endpoint).

## Impact

- **Code:**
  - `examples/identity-demo-mcp/` (new), `deploy/seed.yaml`, `deploy/docker-compose.yml` and `deploy/.env.example`;
  - `.github/workflows/ci.yml` and `pyproject.toml` (markers);
  - `tests/integration/`, `packages/bundlemcp/tests/infrastructure/test_image_pins.py` and `test_bootstrap.py`.
- **Docs:**
  - `README.md`, `CONTRIBUTING.md` and `deploy/TESTING.md`;
  - `docs/self-hosting/bootstrap.md`, `docs/integrate/upstream-identity.md` and `docs/arc42/07-deployment-view.md`.
- **No gateway code changes and no API changes.** The OpenAPI document and the generated types are unaffected.
- **No ADR.** No architectural decision is made or reversed. ADRs 0008, 0016, 0039 and 0041 mention fleet servers
  as historical context, and they stay as written, because ADRs are append-only.
- **Maintainers who run `--profile fleet` locally** move that setup into their private deployment before or with this
  change. The repository keeps no fleet entry point.
- **Git history:** the old fleet references stay in history. They hold image names and the published development
  service key only, which `deploy/stack.sh` already replaces.
- **No GitHub issue.** This comes from the pre-publication checklist.
