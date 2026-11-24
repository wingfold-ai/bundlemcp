#!/bin/sh
# Starts Postgres, Valkey, the echo-mcp upstream and the gateway, waits until
# the gateway is ready, then replaces itself with the stdio bridge. stdout is
# the MCP channel, so everything before the bridge writes to stderr.
set -eu
# the development key the compose stack ships with; it opens only this container's demo endpoint
BUNDLEMCP_INITIAL_SERVICE_KEY=${BUNDLEMCP_INITIAL_SERVICE_KEY:-bmcp_sk_devservicekey000000000000000000000000} # gitleaks:allow
export BUNDLEMCP_INITIAL_SERVICE_KEY
exec 3>&1 1>&2

as_app() { setpriv --reuid=bundlemcp --regid=bundlemcp --init-groups "$@"; }

pg_version=$(ls /usr/lib/postgresql)
pg_ctlcluster "$pg_version" main start

as_app valkey-server --bind 127.0.0.1 --port 6379 --save "" --appendonly no --dir /tmp &

as_app alembic -c /app/alembic.ini upgrade head

as_app python /app/echo/server.py &
(cd /app && as_app python main.py) &
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
exec setpriv --reuid=bundlemcp --regid=bundlemcp --init-groups \
    /opt/bridge/bin/mcp-proxy --transport streamablehttp \
    -H Authorization "Bearer ${BUNDLEMCP_INITIAL_SERVICE_KEY}" \
    http://127.0.0.1:8000/demo/mcp
