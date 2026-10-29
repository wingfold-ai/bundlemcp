#!/usr/bin/env bash
# The whole stack — gateway, admin UI, Postgres, Valkey, Keycloak, the example
# upstreams — with one command, reachable from claude.ai / ChatGPT / Claude
# Desktop through a tunnel. A development setup: see docs/self-hosting/deploy.md
# for what a real deployment sets instead.
#
#   deploy/stack.sh up [compose-up args]   build and start everything (default)
#   deploy/stack.sh down                   stop and remove containers; data stays
#   deploy/stack.sh rebuild                drop the volumes, rebuild, start fresh
#   deploy/stack.sh secrets                generate any secret deploy/.env lacks
#   deploy/stack.sh logs | ps | url
#
# Reads deploy/.env (created from .env.example if missing). TUNNEL selects
# how the stack is exposed:
#   quick  (default) a Cloudflare quick tunnel: no account, a random
#                    https://*.trycloudflare.com URL that changes whenever the
#                    tunnel container restarts (reconnect the client then)
#   ngrok            ngrok with a static domain: NGROK_AUTHTOKEN + NGROK_DOMAIN
#                    in deploy/.env; the URL is stable across restarts
#   none             local only; BUNDLEMCP_PUBLIC_URL from .env (localhost:8000)
#
# Data lives in named volumes and survives stop/start and `down`; only
# `rebuild` (compose down -v) throws it away, and the seed re-applies.
#
# docker-compose.yml falls back to development secrets that are published in
# this repository. They do not leave the host on their own, because every host
# port is bound to 127.0.0.1. Before every `up`, this script replaces them in
# deploy/.env with generated ones, and it refuses to keep a tunnel open while
# the running gateway still accepts the published service key.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  (umask 077 && cp .env.example .env)
  echo "deploy/.env created from .env.example"
fi
# compose interpolates deploy/.env itself; the script needs only the keys that
# decide how to start. A value exported in the shell wins over the file.
from_env_file() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- | tr -d '"' || true; }
TUNNEL="${TUNNEL:-$(from_env_file TUNNEL)}"
TUNNEL="${TUNNEL:-quick}"
NGROK_AUTHTOKEN="${NGROK_AUTHTOKEN:-$(from_env_file NGROK_AUTHTOKEN)}"
NGROK_DOMAIN="${NGROK_DOMAIN:-$(from_env_file NGROK_DOMAIN)}"
BUNDLEMCP_PUBLIC_URL="${BUNDLEMCP_PUBLIC_URL:-$(from_env_file BUNDLEMCP_PUBLIC_URL)}"
SERVICE_KEY_FROM_SHELL="${BUNDLEMCP_INITIAL_SERVICE_KEY:-}"

# The value docker-compose.yml falls back to for a variable: its published default.
published() { sed -n "s/.*\${$1:-\(.*\)}.*/\1/p" docker-compose.yml | head -1; }

# A variable's value in .env as written, without the single quotes set_env adds.
raw_env_value() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- | sed "s/^'\(.*\)'\$/\1/" || true; }

# Set one variable in .env, replacing its line or appending one, through a temporary file.
set_env() {
  local tmp
  tmp=$(mktemp .env.XXXXXX)
  awk -v key="$1" -v line="$1='$2'" '
    index($0, key "=") == 1 { if (!done) print line; done = 1; next }
    { print }
    END { if (!done) print line }
  ' .env >"$tmp"
  chmod 600 "$tmp"
  mv "$tmp" .env
}

# 32 random bytes, URL-safe base64 without padding: the shape of a gateway API key.
random_token() { openssl rand -base64 32 | tr '+/' '-_' | tr -d '=\n'; }
# A Fernet key: 32 random bytes, URL-safe base64 with its padding.
fernet_key() { openssl rand -base64 32 | tr '+/' '-_' | tr -d '\n'; }

# Replace every secret .env lacks, or holds at its published value, with a generated one.
ensure_secrets() {
  local value published_keys
  value=$(raw_env_value BUNDLEMCP_INITIAL_SERVICE_KEY)
  if [ -z "$value" ] || [ "$value" = "$(published BUNDLEMCP_INITIAL_SERVICE_KEY)" ]; then
    value="bmcp_sk_$(random_token)"
    set_env BUNDLEMCP_INITIAL_SERVICE_KEY "$value"
    echo "Generated a service key into deploy/.env: $value"
  fi
  published_keys=$(published BUNDLEMCP_TOKEN_ENCRYPTION_KEYS)
  value=$(raw_env_value BUNDLEMCP_TOKEN_ENCRYPTION_KEYS)
  if [ -z "$value" ] || [ "$value" = "$published_keys" ]; then
    # the published key stays second, so tokens already stored under it still
    # decrypt and are re-encrypted under the new one by the gateway's sweep
    set_env BUNDLEMCP_TOKEN_ENCRYPTION_KEYS "[\"$(fernet_key)\",${published_keys#[}"
    echo "Generated a token encryption key into deploy/.env. Once the gateway reports no stored"
    echo "token under an older key, drop the second entry of BUNDLEMCP_TOKEN_ENCRYPTION_KEYS."
  fi
  value=$(raw_env_value KEYCLOAK_ADMIN_PASSWORD)
  if [ -z "$value" ] || [ "$value" = "$(published KEYCLOAK_ADMIN_PASSWORD)" ]; then
    set_env KEYCLOAK_ADMIN_PASSWORD "$(random_token)"
    echo "Generated the Keycloak admin console password into deploy/.env (KEYCLOAK_ADMIN_PASSWORD)."
  fi
}

compose() { docker compose -f docker-compose.yml "$@"; }
# every profile, so down/logs/ps see the tunnel services whichever mode started them
compose_all() { compose --profile tunnel --profile ngrok "$@"; }

tunnel_url() {
  compose logs --no-log-prefix tunnel 2>/dev/null \
    | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1 || true
}

# The HTTP status the running gateway answers when presented the published service key.
published_key_status() {
  local probe='
import sys, urllib.error, urllib.request
request = urllib.request.Request(
    "http://127.0.0.1:8000/api/v1/upstreams", headers={"Authorization": "Bearer " + sys.argv[1]}
)
try:
    print(urllib.request.urlopen(request, timeout=5).status)
except urllib.error.HTTPError as exc:
    print(exc.code)
except Exception:
    print(0)
'
  compose exec -T gateway python -c "$probe" "$(published BUNDLEMCP_INITIAL_SERVICE_KEY)" \
    2>/dev/null || echo 0
}

# A public tunnel must not serve a gateway that accepts the published service key,
# which an old data volume keeps even after deploy/.env holds a new one.
refuse_published_key() {
  local status
  status=$(published_key_status)
  [ "$status" = 401 ] && return 0
  compose_all stop tunnel ngrok proxy >/dev/null 2>&1 || true
  cat >&2 <<EOF

The tunnel is stopped: the gateway still accepts the service key published in this
repository (it answered $status, not 401), so anyone could manage it through the public URL.
Revoke that key under Admin UI -> API keys at http://localhost:3000, or start from empty
volumes with 'deploy/stack.sh rebuild', then run 'deploy/stack.sh up' again.
EOF
  exit 3
}

up() {
  local public_url profiles=()
  ensure_secrets
  BUNDLEMCP_INITIAL_SERVICE_KEY="${SERVICE_KEY_FROM_SHELL:-$(raw_env_value BUNDLEMCP_INITIAL_SERVICE_KEY)}"
  case "$TUNNEL" in
    none)
      public_url="${BUNDLEMCP_PUBLIC_URL:-http://localhost:8000}"
      ;;
    ngrok)
      : "${NGROK_AUTHTOKEN:?TUNNEL=ngrok needs NGROK_AUTHTOKEN in deploy/.env}"
      : "${NGROK_DOMAIN:?TUNNEL=ngrok needs NGROK_DOMAIN in deploy/.env (a static domain from the ngrok dashboard)}"
      public_url="https://${NGROK_DOMAIN}"
      profiles=(--profile ngrok)
      ;;
    quick)
      profiles=(--profile tunnel)
      # The tunnel decides the public URL, and the gateway needs it at boot,
      # so it starts first and the rest follow once the URL is known.
      compose "${profiles[@]}" up -d tunnel
      public_url=""
      for _ in $(seq 1 60); do
        public_url=$(tunnel_url)
        [ -n "$public_url" ] && break
        sleep 1
      done
      if [ -z "$public_url" ]; then
        echo "no tunnel URL after 60s; cloudflared logs:" >&2
        compose logs --tail=50 tunnel >&2
        exit 1
      fi
      ;;
    *)
      echo "TUNNEL must be quick, ngrok or none (got '$TUNNEL')" >&2
      exit 2
      ;;
  esac

  export BUNDLEMCP_PUBLIC_URL="$public_url"
  compose "${profiles[@]}" up -d --build --wait "$@"
  if [ "$TUNNEL" = quick ] && [ "$(tunnel_url)" != "$public_url" ]; then
    # the tunnel container was recreated during the run (e.g. --force-recreate),
    # so the gateway boots on a hostname that no longer exists: go once more
    echo "tunnel URL changed while starting; re-pointing the stack" >&2
    up "$@"
    return
  fi
  if [ "$TUNNEL" != none ]; then
    refuse_published_key
  fi

  cat <<EOF

bundlemcp is up.

  Admin UI         $public_url$( [ "$TUNNEL" = none ] && echo "  (web at http://localhost:3000)" )
  Gateway          $public_url
  Keycloak login   admin / admin  (dev identity provider at http://localhost:8080; its admin
                   console password is KEYCLOAK_ADMIN_PASSWORD in deploy/.env)
  OAuth demo login demo_user / demo_password  (upstream login page at http://localhost:9000)

  claude.ai / Claude Desktop connector URL:   $public_url/claude/mcp
  ChatGPT connector URL:                      $public_url/chatgpt/mcp

  Every endpoint is served at $public_url/<endpoint name>/mcp, for example:
    curl -H "Authorization: Bearer ${BUNDLEMCP_INITIAL_SERVICE_KEY:-<service key>}" $public_url/demo/mcp
EOF
  if [ "$TUNNEL" = quick ]; then
    echo
    echo "  The quick tunnel URL changes when the tunnel restarts; rerun 'deploy/stack.sh up' to re-point the stack."
  fi
}

cmd="${1:-up}"
[ $# -gt 0 ] && shift
case "$cmd" in
  up) up "$@" ;;
  secrets) ensure_secrets ;;
  down) compose_all down "$@" ;;
  rebuild)
    # everything is gone after down -v, so a plain up recreates it all; never
    # --force-recreate here, which would also recreate the tunnel after its URL
    # was read and leave the gateway on a dead hostname
    compose_all down --volumes
    up "$@"
    ;;
  logs) compose_all logs -f --tail=100 "$@" ;;
  ps) compose_all ps "$@" ;;
  url)
    # what the gateway was started with is what clients must use; a live
    # tunnel on another hostname means the stack needs `up` again
    configured=$(compose exec gateway sh -c 'echo "$BUNDLEMCP_PUBLIC_URL"' 2>/dev/null || true)
    live=$(tunnel_url)
    echo "${configured:-$live}"
    if [ -n "$configured" ] && [ -n "$live" ] && [ "$configured" != "$live" ]; then
      echo "warning: the tunnel now serves $live; run 'deploy/stack.sh up' to re-point the gateway" >&2
    fi
    ;;
  *)
    echo "usage: deploy/stack.sh [up [compose-up args] | down | rebuild | secrets | logs | ps | url]" >&2
    exit 2
    ;;
esac
