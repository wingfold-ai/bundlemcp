# bundlemcp gateway; build from the repo root:
#   docker build -f apps/gateway/Dockerfile .

# uv as a stage of its own, so the image it comes from is a FROM line an update tool reads
FROM ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 AS uv

FROM python:3.15.2-slim-bookworm@sha256:4e03260adeeebafccd084f3584e6b84823aba5651cfb53ef8a078ed441ddf9cd AS builder

# The builder shares the runtime's base, so the .venv it builds runs there unchanged
# (astral-sh/uv publishes no bookworm image for this Python). uv is pinned at or above
# 0.13.4, which stopped trusting the distrusted eMudhra emSign CAs, and uses the image's
# own interpreter, the one the runtime stage has at the same path.
COPY --from=uv /uv /uvx /usr/local/bin/
ENV UV_PYTHON_DOWNLOADS=never
# optional extras of the library, e.g. --build-arg LIBRARY_EXTRAS=otel for tracing
ARG LIBRARY_EXTRAS=""
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages/bundlemcp/pyproject.toml packages/bundlemcp/pyproject.toml
RUN uv sync --locked --no-install-workspace --no-dev --all-packages \
    ${LIBRARY_EXTRAS:+--extra $LIBRARY_EXTRAS}
COPY packages/ packages/
# --no-editable installs the library into the venv, so the runtime stage
# needs no source tree
RUN uv sync --locked --no-dev --all-packages --no-editable \
    ${LIBRARY_EXTRAS:+--extra $LIBRARY_EXTRAS}

FROM python:3.15.2-slim-bookworm@sha256:4e03260adeeebafccd084f3584e6b84823aba5651cfb53ef8a078ed441ddf9cd
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
USER 10001
EXPOSE 8000
# the readiness probe is the container's health
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=6 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/readyz', timeout=3).status == 200 else 1)"]
# migrations run as a dedicated step before serving; exec hands the shell's PID to the
# gateway, so a stop signal reaches it and it drains instead of being killed
CMD ["sh", "-c", "alembic -c alembic.ini upgrade head && exec python main.py"]
