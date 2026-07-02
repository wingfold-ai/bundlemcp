# bundlemcp gateway (spec 71 DEP-11); build from the repo root:
#   docker build -f services/gateway/Dockerfile .
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages/bundlemcp/pyproject.toml packages/bundlemcp/pyproject.toml
RUN uv sync --frozen --no-install-workspace --no-dev
COPY packages/ packages/
RUN uv sync --frozen --no-dev

FROM python:3.13-slim-bookworm
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY packages/ packages/
COPY services/gateway/main.py ./main.py
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
# DEP-4: migrations run as a dedicated step before serving
CMD ["sh", "-c", "cd packages/bundlemcp && alembic upgrade head && cd /app && python main.py"]
