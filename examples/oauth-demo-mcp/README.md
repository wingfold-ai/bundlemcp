# oauth-demo-mcp

An upstream MCP server that is **itself OAuth-protected**, for exercising the
gateway's upstream OAuth end to end: connecting an upstream account, per-user
tokens, the "connect first" error a client sees, refresh on 401.

It is the MCP python-sdk's own
[`examples/servers/simple-auth`](https://github.com/modelcontextprotocol/python-sdk/tree/main/examples/servers/simple-auth),
installed from the pinned SDK tag and run unmodified:

- an **authorization server** (RFC 8414 metadata, PKCE, dynamic client
  registration, RFC 7662 introspection) whose only user is a demo login form:
  `demo_user` / `demo_password`;
- a **resource server** (RFC 9728 protected-resource metadata at
  `/.well-known/oauth-protected-resource/mcp`) that rejects every MCP request
  without a token that server issued for it, and offers one tool, `get_time`.

`serve.py` only supplies configuration the example hard-codes: it binds both
servers to every interface on one port, gives them the URL the gateway and the
browser share, and registers the gateway as a public client (`bundlemcp`,
PKCE, no secret), because the gateway presents a pre-registered client rather
than registering itself.

## In the compose stack

The service runs as a network sidecar of the gateway (`network_mode:
service:gateway`), so `http://localhost:9000` reaches it from the gateway, from
a browser on the host, and satisfies the SDK's rule that a plain-http issuer
must be `localhost`. The seed registers it as server `oauth-demo` with
`auth_mode: upstream_oauth`, `identity_mode: per_user` and the client id, and
puts it in the `demo` bundle next to the echo server:

1. Until someone has connected an account, the gateway cannot list the
   server's tools, so the bundle offers a connect-account tool for it instead.
   Calling it (or opening `<gateway>/oauth/upstream/oauth-demo/connect?as=me`)
   shows the demo login form.
2. After signing in, the gateway re-discovers the server with that account,
   `oauth-demo__get_time` appears in the bundle, and calls run with each
   user's own token. Every other user connects their own account the same
   way.

Tokens live in the demo server's memory: restarting the container invalidates
them, and the gateway reports "connect again".

## Standalone

```bash
docker build -t oauth-demo-mcp .
docker run --rm -p 9000:9000 \
  -e OAUTH_DEMO_REDIRECT_URIS=http://localhost:8000/oauth/upstream/callback \
  oauth-demo-mcp
```

| Variable | Default | Meaning |
|---|---|---|
| `OAUTH_DEMO_PUBLIC_URL` | `http://localhost:9000` | The issuer, as every party reaches it. Plain http is only accepted for `localhost`. |
| `OAUTH_DEMO_PORT` | `9000` | Listen port. |
| `OAUTH_DEMO_CLIENT_ID` | `bundlemcp` | Client id the gateway is registered under. |
| `OAUTH_DEMO_REDIRECT_URIS` | *(empty)* | Comma-separated redirect URIs of that client: the gateway's `/oauth/upstream/callback`. |
