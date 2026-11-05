# Proposal

## Why

Three gateway behaviours have no test that CI runs: discovery that authenticates to an upstream with a static
`authorization` header, a caller's bearer forwarded to an upstream that introspects it back at the gateway, and the
injected `X-MCP-User` header. The only tests for them drive the maintainers' private fleet (`seo-psi`, `seo-gsc`,
`dataforseo`, `hyperframes`): private images CI cannot pull, real Google OAuth and paid DataForSEO credentials. CI
skips them with `-m "not fleet"`, and locally they depend on third-party services. The fleet is also the last thing in
the repository that is about one maintainer's own deployment rather than about bundlemcp, and it has to go before the
repository is made public.

## What Changes

- **A demo upstream that verifies its callers** (`examples/introspect-demo-mcp`), part of the core compose stack: it
  introspects the bearer it receives at the gateway, refuses a request whose bearer is not active, and has a `whoami`
  tool that reports the subject the gateway vouched for, the `X-MCP-User` header, a mapped tenant header and the names
  of the headers that arrived. It never returns a bearer.
- **The demo seed registers it** with `forward_headers` (`authorization`, and `x-tenant-id → x-tenant`) and a static
  `authorization` header for discovery, in a bundle and endpoint of its own (`passthrough`, oauth + api_key). The `demo`
  bundle and its endpoints are unchanged.
- **Integration tests without a marker** replace `tests/integration/test_fleet_bundles.py`: discovery through the static
  header (UPS-17, AUTH-5), a forwarded user bearer introspected as that user (AUTH-27, AUTH-30), an API-key caller
  introspected as `api_key:<id>` (AUTH-5), `X-MCP-User` injected and a spoofed one replaced (AUTH-29), a mapped header
  forwarded and an unlisted one not (AUTH-27), and two callers taking turns each seen with their own bearer (AUTH-31).
- **The fleet is removed**: `deploy/seed.fleet.yaml`, the `fleet` compose profile and its services and volumes,
  `deploy/seaweedfs/`, the fleet settings in `deploy/.env.example`, the `fleet` pytest marker, the `-m "not fleet"` and
  `--grep-invert @fleet` filters in CI, and every mention in the docs.
- **No image floats any more** (DEP-15, modified): the exception for an operator-chosen fleet image goes, so every image
  the compose files run is pinned by digest.
- **One stack for the browser suite** (UI-13, modified): there is no longer a "stack without the fleet profile", and no
  scenario is left out by a title marker.
- **The demo seed covers header passthrough** (MGMT-13, modified): a scenario says the dev stack ships an upstream that
  introspects forwarded bearers, so the passthrough behaviour is tested without third-party servers.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `deployment`: DEP-15 (modified: no image is exempt from the digest pin).
- `admin-ui`: UI-13 (modified: every scenario runs against the one compose stack).
- `management`: MGMT-13 (modified: the demo seed includes an introspecting upstream).

## Impact

- **Resolves:** the knowledge-base task "Replace the bundlemcp fleet with dummy MCP servers for integration testing",
  a step toward making the repository public. No GitHub issue.
- **Files:**
  - `examples/introspect-demo-mcp/` (new), `deploy/docker-compose.yml`, `deploy/seed.yaml`, `deploy/.env.example`;
    `deploy/seed.fleet.yaml` and `deploy/seaweedfs/` deleted
  - `tests/integration/test_header_passthrough.py` (new), `tests/integration/test_fleet_bundles.py` (deleted)
  - `packages/bundlemcp/tests/infrastructure/test_image_pins.py`, `test_bootstrap.py`
  - `.github/workflows/ci.yml` (filters, discovery step, hadolint list), `.github/dependabot.yml`, `pyproject.toml`
  - `README.md`, `CONTRIBUTING.md`, `deploy/TESTING.md`, `docs/arc42/07-deployment-view.md`,
    `docs/self-hosting/bootstrap.md`, `docs/integrate/management-api.md` (the example bundle `fleet` renamed
    `all-servers`)
- **Operators:** `BUNDLEMCP_SEED_FILE` is gone; the compose stack always applies `deploy/seed.yaml`. A deployment that
  wants other upstreams sets its own bootstrap file, as before.
- **No ADR:** this changes the test setup and the demo seed, not the architecture.
