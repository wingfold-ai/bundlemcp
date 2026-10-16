# bundlemcp gateway; build from the repo root:
#   docker build -f apps/gateway/Dockerfile .
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder
# optional extras of the library, e.g. --build-arg LIBRARY_EXTRAS=otel for tracing
ARG LIBRARY_EXTRAS=""
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages/bundlemcp/pyproject.toml packages/bundlemcp/pyproject.toml
RUN uv sync --frozen --no-install-workspace --no-dev --all-packages \
    ${LIBRARY_EXTRAS:+--extra $LIBRARY_EXTRAS}
COPY packages/ packages/
# --no-editable installs the library into the venv, so the runtime stage
# needs no source tree
RUN uv sync --frozen --no-dev --all-packages --no-editable \
    ${LIBRARY_EXTRAS:+--extra $LIBRARY_EXTRAS}

FROM python:3.14-slim-bookworm
# names the build; a new value makes a new image from the cached layers, which is
# how the integration suite rolls out "a newly built image"
ARG BUNDLEMCP_BUILD=dev
LABEL org.opencontainers.image.revision=$BUNDLEMCP_BUILD
WORKDIR /app
RUN useradd --system --uid 10001 --create-home bundlemcp
COPY --from=builder --chown=bundlemcp:bundlemcp /app/.venv /app/.venv
COPY packages/bundlemcp/alembic.ini ./alembic.ini
COPY apps/gateway/main.py ./main.py
ENV PATH="/app/.venv/bin:$PATH"
USER bundlemcp
EXPOSE 8000
# the readiness probe is the container's health
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=6 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/readyz', timeout=3).status == 200 else 1)"]
# migrations run as a dedicated step before serving; exec hands the shell's PID to the
# gateway, so a stop signal reaches it and it drains instead of being killed
CMD ["sh", "-c", "alembic -c alembic.ini upgrade head && exec python main.py"]
