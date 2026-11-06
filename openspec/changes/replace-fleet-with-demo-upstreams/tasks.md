# Tasks

## 1. The identity demo upstream

- [x] 1.1 Create `examples/identity-demo-mcp/server.py`. It is a FastMCP server on port 9000 at `/mcp`, with
  `allowed_hosts` for `identity-demo` and `identity-demo:9000`. In front of the app sits an ASGI check: a bearer equal
  to `DISCOVERY_TOKEN` is the caller `discovery`; any other bearer is introspected against `INTROSPECTION_URL` with
  HTTP Basic `INTROSPECTION_CLIENT_ID` / `INTROSPECTION_CLIENT_SECRET`; a missing bearer or `active: false` gets a
  bare `401`. Verify by running it locally against nothing: a request without a bearer gets `401`, and one with the
  discovery token lists `whoami`.
- [x] 1.2 Add the `whoami` tool, returning the fields in design.md ("What `whoami` returns") from the request's full
  header set. It never returns a credential value, and the server logs no header value. Verify by calling it with the
  discovery token and an `X-Tenant: t` header and reading back `caller: discovery`, `tenant: t` and the header names.
- [x] 1.3 Add `examples/identity-demo-mcp/Dockerfile`, a copy of echo-mcp's with the same pinned
      `python:<tag>@sha256:<digest>` base, plus `fastmcp>=4.1.2`, `httpx` and `uvicorn`, which FastMCP 4 no longer
      installs. Add the directory to:
  - the docker entries of `.github/dependabot.yml`;
  - the hadolint list in `ci.yml`;
  - `packages/bundlemcp/tests/infrastructure/test_runtime_versions.py`.

  Verify that `docker build examples/identity-demo-mcp` succeeds and that `uv run pytest -q
  packages/bundlemcp/tests/infrastructure/test_runtime_versions.py` passes.

## 2. Seed and compose (DOC-3)

- [x] 2.1 Add the `identity-demo` service to `deploy/docker-compose.yml`, with no profile:
  - `build: ../examples/identity-demo-mcp`, `expose: 9000`, no host port;
  - `INTROSPECTION_URL=http://gateway:8000/oauth/introspect`, `INTROSPECTION_CLIENT_ID=bundlemcp`;
  - `INTROSPECTION_CLIENT_SECRET=${BUNDLEMCP_INITIAL_SERVICE_KEY:-<dev default>}`;
  - a `DISCOVERY_TOKEN` with a fixed demo value.

  Update the header comment's list of core services. Verify that `python3 tools/check_compose_ports.py` passes and
  that `docker compose -f deploy/docker-compose.yml config` is valid.
- [x] 2.2 Register the upstream `identity-demo` in `deploy/seed.yaml`:
  - `url: http://identity-demo:9000/mcp`;
  - `forward_headers: {authorization: authorization, x-tenant-id: x-tenant}`;
  - `static_headers: {authorization: Bearer <discovery token>}`, with lowercase keys on both maps so the forwarded
    value replaces the static one;
  - the bundle `identity` and the endpoint `identity` (profile `default`, auth modes `oauth` and `api_key`).

  Leave every existing entry untouched.
- [x] 2.3 Add a hermetic test, `test_demo_seed_keeps_the_identity_demo_apart` (DOC-3), to
  `packages/bundlemcp/tests/infrastructure/test_bootstrap.py`. It loads `deploy/seed.yaml` and asserts that:
  - `identity-demo` is only in the `identity` bundle;
  - the `demo` bundle still has exactly `echo` and `oauth-demo`;
  - the static and forwarded `authorization` keys are the same string.

  Verify it passes.
- [x] 2.4 In `ci.yml`, extend the step "Discover the seeded demo upstream" so it also forces and confirms discovery of
  `identity-demo`, with the same retry loop. Verify on a local core stack under its own `COMPOSE_PROJECT_NAME`: the
  loop reports `identity-demo discovered 1 tools`.
- [x] 2.5 Document the new service and endpoint:
  - a row in the services table of `docs/guide/quickstart.md`;
  - the seed description in `docs/self-hosting/bootstrap.md`;
  - `docs/integrate/upstream-identity.md`, whose `hyperframes` and `seo-gsc` examples become the identity demo, with
    `whoami` shown as what an upstream sees.

  Verify that `python3 tools/check_docs_links.py` and `python3 tools/check_docs_symbols.py` pass and that the docs
  build.

## 3. Identity-forwarding tests (DEP-17)

- [x] 3.1 Move `_oauth_token_for` and the PKCE, cookie and consent helpers it needs from `test_fleet_bundles.py` and
  `test_oauth_flow.py` into `tests/integration/oauth_login.py`, a module of their own because they import `GATEWAY_URL`
  from conftest, which `helpers.py` does not. Repoint `test_oauth_flow.py`, and drop its `noqa: TID251` import. Verify
  that `uv run ruff check tests/integration` is clean.
- [x] 3.2 Write `tests/integration/test_identity_forwarding.py` with the six tests in the design.md table, each citing
  its codes in its name or docstring (UPS-17, AUTH-5, AUTH-27, AUTH-29, AUTH-30, AUTH-31) and with no marker. Verify
  on the local core stack: `BUNDLEMCP_INTEGRATION=1 uv run pytest tests/integration/test_identity_forwarding.py -q`
  passes.
- [x] 3.3 Prove the tests can fail. Temporarily remove `x-tenant-id` from the seeded `forward_headers` and turn
  `send_identity_header` off, then check that the mapping and identity-header tests fail with a readable message.
  Restore both.
- [x] 3.4 Run the same file against a stack started by `deploy/stack.sh up`, which generates a service key. Pass the
  key through `BUNDLEMCP_INITIAL_SERVICE_KEY`, and verify the tests pass there too (design.md: the stack works with
  plain compose and with stack.sh).

## 4. Remove the fleet (DEP-15, DEP-16, UI-13)

- [x] 4.1 Delete `tests/integration/test_fleet_bundles.py` and the `fleet` marker in `pyproject.toml`. In `ci.yml`:
  - drop `-m "not fleet"`, the fleet comments, and "(core; fleet needs private GHCR images)" from the step name;
  - change `npx playwright test --grep-invert @fleet` to `npx playwright test`, and reword its comment (UI-13).

  Verify with `uv run pytest -q`, and that `grep -n fleet .github/workflows/ci.yml pyproject.toml` finds nothing.
- [x] 4.2 Clean up `deploy/docker-compose.yml`:
  - remove the services `seo-psi`, `seo-gsc`, `dataforseo`, `seaweedfs` and `hyperframes`, and the volumes `gscdata`
    and `seaweed-data`;
  - remove the fleet sentence of the header comment, the `seed.fleet.yaml` mount and its comment at
    `BUNDLEMCP_BOOTSTRAP_FILE`, keeping `${BUNDLEMCP_SEED_FILE:-seed.yaml}`.

  Delete `deploy/seed.fleet.yaml` and `deploy/seaweedfs/`. Verify that `docker compose -f deploy/docker-compose.yml
  config --profiles` lists no `fleet` profile.
- [x] 4.3 Clean up `deploy/.env.example`:
  - remove the fleet lines, the seo-gsc and dataforseo sections, and `SEO_PSI_IMAGE`, `SEO_GSC_IMAGE`,
    `HYPERFRAMES_IMAGE` and `PSI_API_KEY`;
  - keep `BUNDLEMCP_SEED_FILE`, documented as "your own seed".

  Verify that `bash tests/deploy/test_stack_secrets.sh` passes.
- [x] 4.4 Delete the scenario "An operator-chosen fleet image may float" from DEP-15 in
  `openspec/specs/deployment/spec.md`, by hand (design.md: OpenSpec cannot drop a scenario through MODIFIED). Verify
  that `openspec validate replace-fleet-with-demo-upstreams --strict` now passes.
- [x] 4.5 Remove the fleet exception from `packages/bundlemcp/tests/infrastructure/test_image_pins.py`
  (`FLEET_PROFILE`, `OPERATOR_CHOSEN`). Turn its fixture around so that a `${X_IMAGE:-example/image:latest}` default
  fails under any profile (DEP-15, scenario "A variable-chosen image is pinned too"). Add a test that every compose
  service builds from this repository or names a digest-pinned public image (DEP-16). Verify both pass, and that the
  fixture fails without the change.
- [x] 4.6 Delete `test_fleet_seed_extends_the_demo_seed_unchanged` from `test_bootstrap.py`. Verify that `uv run pytest
  -q packages/bundlemcp/tests/infrastructure` passes.
- [x] 4.7 Remove the fleet from the docs:
  - `README.md`: the two fleet notes;
  - `CONTRIBUTING.md`: the integration command, the marker note, the `@fleet` sentence and the image-pin exception;
  - `deploy/TESTING.md`: the fleet start command, the `seed.fleet.yaml` paragraph, the `@fleet` note and "Connecting
    Google Search Console". Add a short paragraph on the identity-forwarding tests;
  - `docs/self-hosting/bootstrap.md`: the sentence about the maintainers' fleet;
  - `docs/arc42/07-deployment-view.md`: the image-pins row.

  Rename the generic `fleet` bundle example in `docs/integrate/management-api.md` to `all-servers`, so the word means
  only "all replicas". Verify that `grep -rni fleet . --exclude-dir={.git,node_modules,.venv}` finds only "fleet-wide"
  (discovery lock, ADR-0063) and `openspec/changes/archive/`, and that `uv run rumdl check .` and the four
  `tools/check_*.py` docs scripts pass.

## 5. Verification

- [x] 5.1 Run the gates:
  - `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .` and `uv run lint-imports`;
  - `python3 tools/check_docs_links.py`, `check_docs_symbols.py`, `check_docs_settings.py`, `check_adr_graph.py`,
    `check_compose_ports.py` and `check_spec_ids.py`;
  - `bash tests/deploy/test_stack_secrets.sh` and `openspec validate --all --strict`.

  No DTO or route changes, so check that `cd apps/web && npm run openapi` leaves no diff.
- [x] 5.2 On a fresh local core stack plus the replica overlay, under its own `COMPOSE_PROJECT_NAME`:
  - run the CI discovery step;
  - run `BUNDLEMCP_INTEGRATION=1 uv run pytest tests/integration -q` with no marker filter;
  - run `cd apps/web && npx playwright test`.

  Verify that everything passes, and that the overhead report still reads echo on port 9100.
