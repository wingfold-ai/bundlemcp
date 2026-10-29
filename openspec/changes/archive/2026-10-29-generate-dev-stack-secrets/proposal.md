# Proposal

## Why

`make up` (`deploy/stack.sh`) creates `deploy/.env` from `.env.example` and then publishes the stack through a public
Cloudflare quick tunnel by default. The Caddy proxy routes `/api/*` through that tunnel to the gateway. Three defaults
make this dangerous:

- **A published service key.** `.env.example` sets `BUNDLEMCP_INITIAL_SERVICE_KEY=bmcp_sk_devservicekey000…`. Anyone
  who has read the repository and learns the tunnel URL has full management access, including
  `GET /api/v1/export?include_secrets=true`.
- **A published encryption key.** The token encryption key falls back to a fixed value in `docker-compose.yml`.
- **Services open on the LAN.** Keycloak (bootstrap admin `admin/admin`), the gateway, the web app and the side
  services publish their host ports on every interface, so they are also reachable from the local network.

The 2026-10-29 code audit found this (finding M5).

## What Changes

- **Generated secrets** (DEP-13, added):
  - On every `up`, `stack.sh` fills in any of the following that `deploy/.env` lacks, or that still holds the value
    the repository publishes, with a freshly generated random value: the initial service key, the token encryption key
    and the Keycloak bootstrap admin password.
  - An existing token encryption key is rotated, not replaced: the new key is prepended (DEP-9), so stored upstream
    tokens stay readable.
  - It prints the generated service key once, so the developer can use it.
- **No tunnel while the published key works** (DEP-13). In `quick` and `ngrok` modes, `stack.sh` checks two things
  before it reports the stack as up:
  - `.env` holds no published default;
  - the running gateway refuses the published service key.

  If either check fails, it stops the tunnel and tells the developer how to fix it. A key provisioned into an old data
  volume survives a new `.env`, which is why the live check is needed.
- **Host ports on loopback** (DEP-13): every host port in `deploy/docker-compose.yml` binds to `127.0.0.1`. The tunnel
  and the containers reach each other over the compose network and need no host port.
- `docker compose -f deploy/docker-compose.yml up` without `stack.sh` keeps its built-in development defaults, so ARC-13
  and CI keep working. It only listens on loopback and opens no tunnel.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `deployment`: DEP-13 (added: the development stack never exposes a published credential).

## Impact

- **Resolves:** audit finding M5 (2026-10-29). No GitHub issue.
- **Files:**
  - `deploy/stack.sh` (secret generation, the exposure check and a `secrets` subcommand)
  - `deploy/.env.example` (no live key values; comments say `stack.sh` generates them)
  - `deploy/docker-compose.yml` (loopback ports, `KC_BOOTSTRAP_ADMIN_PASSWORD` from `.env`)
  - `Makefile` (a `secrets` alias)
- **CI:** `ci.yml` and `restore-rehearsal.yml` call compose directly with the built-in defaults, so they are unchanged.
  `tests/integration/conftest.py` already reads the key from the environment.
- **Developers:** an existing checkout whose data volume was provisioned with the published key is refused a tunnel
  until that key is revoked (Admin UI → API keys) or the stack is rebuilt. The refusal message says so.
- **Docs:** `docs/guide/quickstart.md`, `docs/self-hosting/setups.md` and `docs/self-hosting/deploy.md` (where they
  quote the dev key or `admin/admin` for the Keycloak console). CI writes the CHANGELOG entry (DEP-12). No ADR: this
  changes the dev tooling, not the architecture.
- **Not covered:** the Keycloak realm's own demo users (`admin/admin` in the `bundlemcp` realm). With Keycloak on
  loopback they are reachable only from the developer's machine. The static OIDC client secret
  (`dev-gateway-secret`) is useless without that Keycloak.
