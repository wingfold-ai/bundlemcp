# Design

## Context

See [proposal.md](proposal.md). `deploy/stack.sh` is the entry point behind `make up`.

- **Configuration:** it copies `.env.example` to `.env` when missing, reads `TUNNEL` (default `quick`), starts the
  tunnel first in `quick` mode to learn its URL, and then runs `compose up -d --build --wait`.
- **Compose defaults:** `docker-compose.yml` interpolates `.env`, with built-in fallbacks:
  - `${BUNDLEMCP_INITIAL_SERVICE_KEY:-bmcp_sk_devservicekey…}`;
  - `${BUNDLEMCP_TOKEN_ENCRYPTION_KEYS:-["Uqw2…"]}`;
  - `KC_BOOTSTRAP_ADMIN_PASSWORD: admin`.
- **Key provisioning:** the gateway provisions `BUNDLEMCP_INITIAL_SERVICE_KEY` only when no service key exists
  (MGMT-10). A key provisioned into an existing Postgres volume therefore survives a change to `.env`.
- **Where the dev key is also used:**
  - CI (`ci.yml`, `restore-rehearsal.yml`) runs `docker compose` directly and uses the published key;
  - `tests/integration/conftest.py` reads it from the environment, with the published value as fallback.

## Goals / Non-Goals

**Goals:**

- `make up` from a fresh clone never serves a credential an outsider can read in the repository.
- An existing developer setup either upgrades itself or refuses to go public, with a message that says what to do.
- CI and bare `docker compose up` keep working unchanged.

**Non-Goals:**

- Hardening the Keycloak realm's demo users. They stay documented, reachable only on loopback.
- Changing any gateway code. The gateway gets no list of "known dev values". Detection lives in the dev tooling.

## Decisions

### Generate in `stack.sh`, not in compose or in the gateway

`stack.sh` gains an `ensure_secrets` step that runs before every `up`. It also becomes a `secrets` subcommand
(`make secrets`). For each managed variable, it generates a value when the variable is missing from `.env` or equals the
published default, and rewrites that one line in place, keeping the rest of the file:

- `BUNDLEMCP_INITIAL_SERVICE_KEY`: `bmcp_sk_` followed by 32 random URL-safe bytes.
- `BUNDLEMCP_TOKEN_ENCRYPTION_KEYS`: a new Fernet key, written as `["<new>","<published>"]`. The published key stays
  second, so tokens already stored under it, whether in an old volume or under the compose fallback, still decrypt and
  are re-encrypted by the DEP-9 sweep. The script prints how to drop it once the gateway reports zero dependants.
- `KEYCLOAK_ADMIN_PASSWORD`: 24 random URL-safe bytes. Compose reads it as `${KEYCLOAK_ADMIN_PASSWORD:-admin}`.

Values are generated with `openssl rand`. That avoids a host Python dependency, which the script does not have today.
Base64url output is converted for the Fernet key, which is 32 bytes in URL-safe base64. Writes go through a temporary
file and `mv`, and `.env` is created with mode `0600`. The published defaults are read from `.env.example` and
`docker-compose.yml` at run time, not copied into the script, so they cannot drift.

Alternatives considered:

- **Generating in the gateway at first boot.** The gateway would have to persist and reveal a secret, and it would
  need to know "dev" values, which would mix dev tooling into the product.
- **Removing the compose fallbacks.** That breaks ARC-13's one-command `docker compose up` and CI. With loopback-only
  ports and no tunnel, those fallbacks are not reachable from outside.

### A live check before going public

After `compose up --wait`, in `quick` and `ngrok` modes, `stack.sh` calls `GET http://127.0.0.1:8000/api/v1/upstreams`
with the published key as the bearer token, from inside the gateway container with its own Python, so the script still
needs nothing on the host beyond bash, Docker and `openssl`. A `200` means a service key with the published value exists
in the database. The script then runs `compose stop tunnel` (or `ngrok`), prints the two fixes, and exits with status 3.
The two fixes are revoking the key under Admin UI → API keys, or `deploy/stack.sh rebuild`. A `401` passes the check.
Any other answer fails closed, with the same stop.

This is the only check that catches a key living in an old volume, which `.env` cannot reveal.

### Loopback host ports

Every `ports:` entry becomes `127.0.0.1:<host>:<container>`, matching `echo-mcp`, which already does this. The quick
tunnel, ngrok and Caddy reach `gateway:8000` and `web:3000` over the compose network. Browsers on the developer's
machine use `localhost`, as the docs already say.

## Risks / Trade-offs

- [A developer used the stack from another device on the LAN] → this now needs their own compose file passed after
  the stack's (`-f deploy/docker-compose.yml -f <file>`; with `-f` compose loads no override file on its own), which
  `docs/self-hosting/setups.md` documents as a deliberate, trusted-network-only choice.
- [`sed -i` differs between GNU and BSD] → the script rewrites the file with `awk` into a temporary file, which works
  the same on macOS and Linux.
- [The live check races the gateway's readiness] → it runs after `--wait`, which waits for the gateway health check.
- [In `quick` mode the tunnel starts before the gateway, because the gateway needs its URL at boot] → an old volume
  holding the published key is reachable for the seconds `compose up --wait` takes, at a URL nobody else has been told
  yet. The check then stops the tunnel. Checking before the tunnel starts would need a second gateway boot.

## Migration Plan

Existing checkouts: the next `make up` rewrites the published values in `.env`. If the old volume holds the published
key, the live check refuses the tunnel with instructions. Rollback is the previous `stack.sh` from git, and `.env`
keeps the generated values, which also work with the old script.
