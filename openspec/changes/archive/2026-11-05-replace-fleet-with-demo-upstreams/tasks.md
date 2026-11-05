# Tasks

## 1. Demo upstream

- [x] 1.1 Add `examples/introspect-demo-mcp/` (`server.py`, `Dockerfile` on the same pinned Python image as
  `echo-mcp`): introspect every request's bearer at `INTROSPECTION_URL` with the service key, answer 401 when it is
  not active, and serve a `whoami` tool that reports the subject, `X-MCP-User`, the mapped tenant header and the header
  names. Verify with `uv run ruff check examples/`
- [x] 1.2 Add the `introspect-demo` service to `deploy/docker-compose.yml` (no profile), and the upstream, the
  `passthrough` bundle and the `passthrough` endpoint to `deploy/seed.yaml`. Verify with `test_seed_file_parses`
- [x] 1.3 Add the Dockerfile to the hadolint list in `ci.yml` and the directory to Dependabot's `docker` ecosystem

## 2. Tests

- [x] 2.1 Add `tests/integration/test_header_passthrough.py` (UPS-17, AUTH-5, AUTH-27, AUTH-29, AUTH-30, AUTH-31)
  without a marker, and delete `tests/integration/test_fleet_bundles.py`
- [x] 2.2 CI forces a discovery of `introspect-demo` beside `echo`, and runs the whole integration suite and every
  browser scenario
- [x] 2.3 `test_image_pins.py`: no exception for an image chosen through a variable (DEP-15);
  `test_bootstrap.py`: drop `test_fleet_seed_extends_the_demo_seed_unchanged`. Verify with `uv run pytest -q`

## 3. Remove the fleet

- [x] 3.1 Delete `deploy/seed.fleet.yaml` and `deploy/seaweedfs/`; remove the fleet services, volumes, mount and
  `BUNDLEMCP_SEED_FILE` from the compose file and the fleet settings from `deploy/.env.example`
- [x] 3.2 Remove the `fleet` pytest marker and the CI filters and comments
- [x] 3.3 Update `README.md`, `CONTRIBUTING.md`, `deploy/TESTING.md`, `docs/arc42/07-deployment-view.md`,
  `docs/self-hosting/bootstrap.md`, and rename the example bundle in `docs/integrate/management-api.md`. Verify that
  `grep -rni fleet` finds only "fleet-wide" and the archived changes

## 4. Specs and gates

- [x] 4.1 Delta specs for DEP-15, UI-13 and MGMT-13; `openspec validate --all --strict`
- [x] 4.2 All gates: `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .`, `uv run lint-imports`,
  `python3 tools/check_spec_ids.py` and the docs checks locally; the integration suite and the browser suite against
  the compose stack in CI
