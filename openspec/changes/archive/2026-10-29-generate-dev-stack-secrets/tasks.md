# Tasks

## 1. Loopback host ports (DEP-13)

- [x] 1.1 Bind every `ports:` entry in `deploy/docker-compose.yml` to `127.0.0.1` (keycloak, gateway 8000 and 9000, web,
  and the fleet services), and read `KC_BOOTSTRAP_ADMIN_PASSWORD` from `${KEYCLOAK_ADMIN_PASSWORD:-admin}`. Verify with
  `docker compose -f deploy/docker-compose.yml config | grep -A2 'ports:'` showing only `127.0.0.1` host IPs, and with
  the integration job still passing in CI
- [x] 1.2 Add `tools/check_compose_ports.py`, which fails when any host port in a `deploy/docker-compose*.yml` is not
  loopback-bound (it cites DEP-13 in its error message), wire it into the CI docs-checks job, and verify it fails on a
  copy with `"8000:8000"` and passes on the repository

## 2. Generated secrets (DEP-13)

- [x] 2.1 Add `ensure_secrets` and the `secrets` subcommand to `deploy/stack.sh` (`openssl rand`, an `awk` rewrite
  through a temporary file, mode `0600`, published defaults read from `docker-compose.yml`, the new
  encryption key prepended to the published one), and a `secrets` alias in `Makefile`. Verify with a shell
  test `tests/deploy/test_stack_secrets.sh`, run in CI, covering: a fresh `.env` gets three non-default values; a
  published service key is replaced; the key list becomes `[new, published]`; a second run changes nothing;
  an operator's own values are kept
- [x] 2.2 Remove the live key values from `deploy/.env.example` (comments say `stack.sh` generates them), and make `up`
      print the generated service key once. Verify with `docker compose config --format json` over a generated `.env`:
      the gateway receives the generated service key and a two-entry key list that parses as JSON

## 3. No tunnel while the published key works (DEP-13)

- [x] 3.1 After `compose up --wait` in `quick`/`ngrok` modes, probe `GET /api/v1/upstreams` on `127.0.0.1:8000` with
  the published key. On anything but `401`, stop the tunnel service, print the revoke-or-rebuild instructions and exit
  with status 3. Verify the probe against the local stack: a volume provisioned with the published key answers 200
  (refused), and the same probe with an unknown key answers 401 (accepted); record both in the PR

## 4. Documentation

- [x] 4.1 Update `docs/guide/quickstart.md`, `docs/self-hosting/setups.md` (including the LAN compose file) and
  `docs/self-hosting/deploy.md` wherever they quote the dev service key, the Keycloak console password or `0.0.0.0`
  ports, and verify with `python3 tools/check_docs_links.py` and `uv run rumdl check .`

## 5. Gates

- [x] 5.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .`, `uv run lint-imports`, the four
  `tools/check_*.py` scripts, `python3 tools/check_compose_ports.py`, `python3 tools/check_spec_ids.py` and
  `openspec validate --all --strict`; all pass (no DTO or route changes)
