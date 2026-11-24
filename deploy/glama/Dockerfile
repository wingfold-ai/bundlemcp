# bundlemcp as one stdio MCP server, for registries that evaluate a server by
# starting it in a single container (Glama). It runs the real gateway with its
# own Postgres and Valkey, the echo-mcp example as the upstream, and a bridge
# that turns stdin/stdout into Streamable HTTP calls to the gateway's demo
# endpoint. Build from the repo root:
#   docker build -f deploy/glama/Dockerfile -t bundlemcp-glama .
#   docker run -i --rm bundlemcp-glama
# Demo values only; this is not a deployment.

FROM ghcr.io/astral-sh/uv:0.13.9@sha256:d3b601f0c7b118bc1753febf7c41cc80981df678445e0254284eecf84db79a7d AS uv

FROM python:3.15.2-slim-trixie@sha256:63bb298d2b7b88f176f51b5189f54ce6535c997682ea70885d2132f5d473a8a5 AS builder
COPY --from=uv /uv /uvx /usr/local/bin/
ENV UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages/bundlemcp/pyproject.toml packages/bundlemcp/pyproject.toml
RUN uv sync --locked --no-install-workspace --no-dev --all-packages
COPY packages/ packages/
RUN uv sync --locked --no-dev --all-packages --no-editable
# The bridge needs the 1.x MCP SDK, the gateway the 2.x one, so it gets a venv of its own
RUN uv venv /opt/bridge && uv pip install --python /opt/bridge/bin/python "mcp-proxy==0.15.0"

FROM python:3.15.2-slim-trixie@sha256:63bb298d2b7b88f176f51b5189f54ce6535c997682ea70885d2132f5d473a8a5
# Debian pins each package within a release, so the trixie base already fixes the versions
# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql valkey-server \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --create-home bundlemcp \
    && pg_ctlcluster "$(ls /usr/lib/postgresql)" main start \
    && su postgres -c "psql -q -c \"CREATE ROLE bundlemcp LOGIN PASSWORD 'bundlemcp'\" -c 'CREATE DATABASE bundlemcp OWNER bundlemcp'" \
    && pg_ctlcluster "$(ls /usr/lib/postgresql)" main stop
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /opt/bridge /opt/bridge
COPY packages/bundlemcp/alembic.ini ./alembic.ini
COPY apps/gateway/main.py ./main.py
COPY examples/echo-mcp/server.py ./echo/server.py
COPY deploy/glama/bootstrap.yaml deploy/glama/entrypoint.sh ./glama/
ENV PATH="/app/.venv/bin:$PATH" \
    HOME=/home/bundlemcp \
    BUNDLEMCP_DATABASE_URL=postgresql+asyncpg://bundlemcp:bundlemcp@127.0.0.1:5432/bundlemcp \
    BUNDLEMCP_REDIS_URL=redis://127.0.0.1:6379/0 \
    BUNDLEMCP_PUBLIC_URL=http://127.0.0.1:8000 \
    BUNDLEMCP_BOOTSTRAP_FILE=/app/glama/bootstrap.yaml \
    BUNDLEMCP_EGRESS_ALLOW_CIDRS='["127.0.0.0/8"]'
# Postgres must start as its own user and the gateway as bundlemcp, so the
# entrypoint starts as root and drops privileges for each process
ENTRYPOINT ["/app/glama/entrypoint.sh"]
