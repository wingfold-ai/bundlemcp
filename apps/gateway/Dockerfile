# bundlemcp gateway (spec 71 DEP-11); build from the repo root:
#   docker build -f apps/gateway/Dockerfile .
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages/bundlemcp/pyproject.toml packages/bundlemcp/pyproject.toml
RUN uv sync --frozen --no-install-workspace --no-dev --all-packages
COPY packages/ packages/
# --no-editable installs the library into the venv, so the runtime stage
# needs no source tree
RUN uv sync --frozen --no-dev --all-packages --no-editable

FROM python:3.13-slim-bookworm
WORKDIR /app
RUN useradd --system --uid 10001 --create-home bundlemcp
COPY --from=builder --chown=bundlemcp:bundlemcp /app/.venv /app/.venv
COPY packages/bundlemcp/alembic.ini ./alembic.ini
COPY apps/gateway/main.py ./main.py
ENV PATH="/app/.venv/bin:$PATH"
USER bundlemcp
EXPOSE 8000
# DEP-3: the readiness probe is the container's health
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=6 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/readyz', timeout=3).status == 200 else 1)"]
# DEP-4: migrations run as a dedicated step before serving
CMD ["sh", "-c", "alembic -c alembic.ini upgrade head && python main.py"]
