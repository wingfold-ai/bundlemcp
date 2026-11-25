# bundlemcp as one stdio MCP server, for registries that evaluate a server by
# starting it in a single container (Glama). It runs the real gateway with its
# own Postgres and Valkey, the echo-mcp example as the upstream, and a bridge
# that turns stdin/stdout into Streamable HTTP calls to the gateway's demo
# endpoint. Build from the repo root:
#   docker build -f deploy/glama/Dockerfile -t bundlemcp-glama .
#   docker run -i --rm bundlemcp-glama
# Demo values only; this is not a deployment.
#
# Glama does not build this file: it generates a Dockerfile of its own around a
# clone of the repository, from the settings under Admin -> Dockerfile. These
# settings make that image run the same entrypoint:
#   Base image   debian:trixie-slim (Node.js and Python versions left at their defaults)
#   Build steps  ["apt-get update && apt-get install -y --no-install-recommends postgresql valkey-server",
#                 "uv sync --locked --no-dev --all-packages",
#                 "UV_PROJECT_ENVIRONMENT=/opt/bridge uv sync --locked --no-dev --project deploy/glama/bridge",
#                 "deploy/glama/prepare-db.sh"]
#   CMD          ["mcp-proxy", "--", "deploy/glama/entrypoint.sh"]
# The environment schema and the placeholder parameters stay empty.

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
# The bridge needs the 1.x MCP SDK, the gateway the 2.x one, so it is a project of its own,
# installed from its own lock into its own venv
COPY deploy/glama/bridge/pyproject.toml deploy/glama/bridge/uv.lock /bridge/
RUN UV_PROJECT_ENVIRONMENT=/opt/bridge uv sync --locked --no-dev --project /bridge

FROM python:3.15.2-slim-trixie@sha256:63bb298d2b7b88f176f51b5189f54ce6535c997682ea70885d2132f5d473a8a5
# Debian pins each package within a release, so the trixie base already fixes the versions
# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql valkey-server \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --create-home bundlemcp
# The files keep their repository paths, as in the clone Glama builds from, so
# one entrypoint serves both images
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /opt/bridge /opt/bridge
COPY packages/bundlemcp/alembic.ini packages/bundlemcp/alembic.ini
COPY apps/gateway/main.py apps/gateway/main.py
COPY examples/echo-mcp/server.py examples/echo-mcp/server.py
COPY deploy/glama/ deploy/glama/
RUN deploy/glama/prepare-db.sh
ENV HOME=/home/bundlemcp
# Postgres must start as its own user and the gateway as bundlemcp, so the
# entrypoint starts as root and drops privileges for each process
ENTRYPOINT ["/app/deploy/glama/entrypoint.sh"]
