#!/bin/sh
# Starts Postgres, Valkey, the echo-mcp upstream and the gateway, waits until
# the gateway is ready, then replaces itself with the stdio bridge. stdout is
# the MCP channel, so everything before the bridge writes to stderr.
#
# Paths are the repository's own, from the checkout this script sits in, so the
# same script runs in deploy/glama/Dockerfile and in the Dockerfile Glama
# generates around a clone of the repository.
set -eu
exec 3>&1 1>&2

repo=$(cd "$(dirname "$0")/../.." && pwd)
PATH="$repo/.venv/bin:$PATH"

export BUNDLEMCP_DATABASE_URL="${BUNDLEMCP_DATABASE_URL:-postgresql+asyncpg://bundlemcp:bundlemcp@127.0.0.1:5432/bundlemcp}"
export BUNDLEMCP_REDIS_URL="${BUNDLEMCP_REDIS_URL:-redis://127.0.0.1:6379/0}"
export BUNDLEMCP_PUBLIC_URL="${BUNDLEMCP_PUBLIC_URL:-http://127.0.0.1:8000}"
export BUNDLEMCP_BOOTSTRAP_FILE="${BUNDLEMCP_BOOTSTRAP_FILE:-$repo/deploy/glama/bootstrap.yaml}"
export BUNDLEMCP_EGRESS_ALLOW_CIDRS="${BUNDLEMCP_EGRESS_ALLOW_CIDRS:-[\"127.0.0.0/8\"]}"
# the development key the compose stack ships with; it opens only this container's demo endpoint
BUNDLEMCP_INITIAL_SERVICE_KEY=${BUNDLEMCP_INITIAL_SERVICE_KEY:-bmcp_sk_devservicekey000000000000000000000000} # gitleaks:allow
export BUNDLEMCP_INITIAL_SERVICE_KEY

# Drop to the bundlemcp user where the image has one. Glama's image has none:
# its Python lives under /root, which another user cannot run.
# The prefix stays unquoted where it is used, so it splits into words, or vanishes when empty.
as_app=""
if id bundlemcp >/dev/null 2>&1; then
    as_app="setpriv --reuid=bundlemcp --regid=bundlemcp --init-groups"
fi

pg_ctlcluster "$(ls /usr/lib/postgresql)" main start

$as_app valkey-server --bind 127.0.0.1 --port 6379 --save "" --appendonly no --dir /tmp &

$as_app alembic -c "$repo/packages/bundlemcp/alembic.ini" upgrade head

$as_app python "$repo/examples/echo-mcp/server.py" &
(cd "$repo/apps/gateway" && $as_app python main.py) &
gateway=$!

tries=0
until python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/readyz', timeout=2)" 2>/dev/null; do
    if ! kill -0 "$gateway" 2>/dev/null; then
        echo "glama: the gateway exited before it was ready" >&2
        exit 1
    fi
    tries=$((tries + 1))
    if [ "$tries" -ge 120 ]; then
        echo "glama: the gateway was not ready after 60 seconds" >&2
        exit 1
    fi
    sleep 0.5
done
echo "glama: gateway ready, starting the stdio bridge" >&2

exec 1>&3 3>&-
exec $as_app /opt/bridge/bin/mcp-proxy --transport streamablehttp \
    -H Authorization "Bearer ${BUNDLEMCP_INITIAL_SERVICE_KEY}" \
    http://127.0.0.1:8000/demo/mcp
