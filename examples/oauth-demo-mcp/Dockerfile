# The MCP python-sdk's "simple-auth" example, unmodified, run as one container:
# an OAuth 2.1 authorization server with a demo login form and an MCP resource
# server that accepts only its tokens. serve.py binds both to every interface
# and pre-registers the gateway as a client; see README.md.
FROM python:3.15.1-slim-bookworm@sha256:575f8bc12ec26542e0678bc6b60e385218248019d433157ec327264a78c3a853
WORKDIR /app
ARG SDK_REF=v2.2.0
# git is needed only to fetch the SDK and is purged in the same layer; a pinned Debian
# package version breaks the build as soon as the security archive drops that version
# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && pip install --no-cache-dir \
        "mcp-simple-auth @ git+https://github.com/modelcontextprotocol/python-sdk.git@${SDK_REF}#subdirectory=examples/servers/simple-auth" \
        "mcp @ git+https://github.com/modelcontextprotocol/python-sdk.git@${SDK_REF}" \
    && apt-get purge -y git && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*
COPY serve.py .
EXPOSE 9000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=6 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:9000/.well-known/oauth-protected-resource/mcp', timeout=3).status == 200 else 1)"]
CMD ["python", "serve.py"]
