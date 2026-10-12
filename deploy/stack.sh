#!/usr/bin/env bash
# The whole stack — gateway, admin UI, Postgres, Valkey, Keycloak, the example
# upstreams — with one command, reachable from claude.ai / ChatGPT / Claude
# Desktop through a tunnel. A development setup: see docs/self-hosting/deploy.md
# for what a real deployment sets instead.
#
#   deploy/stack.sh up [compose-up args]   build and start everything (default)
#   deploy/stack.sh down                   stop and remove containers; data stays
#   deploy/stack.sh rebuild                drop the volumes, rebuild, start fresh
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
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  cp .env.example .env
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
BUNDLEMCP_INITIAL_SERVICE_KEY="${BUNDLEMCP_INITIAL_SERVICE_KEY:-$(from_env_file BUNDLEMCP_INITIAL_SERVICE_KEY)}"

compose() { docker compose -f docker-compose.yml "$@"; }
# every profile, so down/logs/ps see the tunnel services whichever mode started them
compose_all() { compose --profile tunnel --profile ngrok "$@"; }

tunnel_url() {
  compose logs --no-log-prefix tunnel 2>/dev/null \
    | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1 || true
}

up() {
  local public_url profiles=()
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
      # The tunnel decides the public URL, and the gateway needs it at boot
      # (DEP-1), so it starts first and the rest follow once the URL is known.
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

  cat <<EOF

bundlemcp is up.

  Admin UI         $public_url$( [ "$TUNNEL" = none ] && echo "  (web at http://localhost:3000)" )
  Gateway          $public_url
  Keycloak login   admin / admin  (dev identity provider at http://localhost:8080)
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
    echo "usage: deploy/stack.sh [up [compose-up args] | down | rebuild | logs | ps | url]" >&2
    exit 2
    ;;
esac
