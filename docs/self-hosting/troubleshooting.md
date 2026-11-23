---
description: "Troubleshoot bundlemcp by symptom: for each common problem the usual cause, the command that confirms it
  and the fix."
---

# Troubleshooting

Symptom first. Each entry gives the usual cause, the command that confirms it,
and the fix.

Two commands are worth knowing before anything else:

```bash
# what the gateway thinks happened
docker compose -f deploy/docker-compose.yml logs gateway --tail 100

# whether it considers itself healthy at all
curl -fsS http://localhost:8000/readyz && echo ready
```

## `tools/list` comes back empty

**Cause.** Bootstrap discovers an upstream's tools in the background, so on a
cold start the seed can finish before the upstream is listening.

```bash
KEY=bmcp_sk_devservicekey000000000000000000000000
curl -s -X POST http://localhost:8000/api/v1/upstreams/echo:refresh-tools \
  -H "Authorization: Bearer $KEY"        # -> {"discovered": 3, ...}
```

**Fix.** That call forces a probe. If it still reports nothing, the upstream
itself is the problem — read on.

## A server shows `health_status: error`

```bash
curl -s http://localhost:8000/api/v1/upstreams/my-server \
  -H "Authorization: Bearer $KEY" | python3 -m json.tool | grep -A1 last_error
```

`last_error` names the cause. The three common ones:

| `last_error` mentions | Cause |
|---|---|
| egress, blocked range | The URL resolves to loopback or a link-local address, which the egress policy blocks |
| DNS, name resolution | The hostname does not resolve **inside the gateway container** |
| connection refused, timeout | It resolves but nothing is listening there |

**Fix.** The gateway dials the URL from inside its container, so `localhost` is
the container, not your machine — and loopback is blocked deliberately. Use
`http://host.docker.internal:9000/mcp` (on Linux add
`extra_hosts: ["host.docker.internal:host-gateway"]` to the `gateway` service),
or attach your server to the compose network and use its service name. See
[Network egress](/self-hosting/deploy#network-egress).

## The management API answers `401` or `403`

**`401 admin session or service API key required`.** No valid credential reached the gateway: no key, a mistyped or
deactivated key, or a browser session that expired or whose user was deactivated. Sign in again, or check the key.

**`403`.** The gateway knows the caller, who may not manage it:

1. `403 key is not service-kind`: an `endpoint`-kind key. The management API takes `service` keys only.
2. `403 signed in, but not an administrator`: neither your email is in `BUNDLEMCP_ADMIN_EMAILS` nor your ID token's
   admin claim carries the admin value.
3. `403 CSRF origin check failed`: a browser mutation from an origin outside `BUNDLEMCP_WEB_ORIGINS`.

```bash
curl -s http://localhost:8000/api/v1/me -H "Authorization: Bearer $KEY"
```

`GET /api/v1/me` answers for any signed-in caller and reports `kind` as `admin`, `user` or `service`. If it says `user`,
add the address to `BUNDLEMCP_ADMIN_EMAILS` or the admin group at your identity provider (see
[Who is an admin](/self-hosting/identity-provider#who-is-an-admin)), and log in again.

## Login redirects, then bounces back — the cookie never sticks

**Cause.** `BUNDLEMCP_PUBLIC_URL` is not the URL you actually reached the
gateway on. The session cookie's `Domain` and `Secure` attributes and every
OAuth URL derive from it, never from the `Host` header.

**Fix.** Set it to exactly what the browser uses, including scheme and port,
and register `<public url>/login/callback` as the redirect URI at the identity
provider.

## The login callback answers `400` "login was not started in this browser"

**Cause.** A login can be finished only in the browser that started it. `/login` sets a short-lived binding cookie
(`__Host-bmcp_login` on https, `bmcp_login` on plain http), and the callback refuses a browser that does not present
the one belonging to that login. This happens when a callback link is opened in another browser or profile, when a
second login was started in another tab of the same browser (only the latest one can finish), when more than 10
minutes passed at the identity provider, or once for a login that was in flight while the gateway was upgraded.

**Fix.** Open `/login` again and finish it in the same browser. If it keeps failing, check that the browser accepts
cookies for the gateway's host and that `BUNDLEMCP_PUBLIC_URL` matches the address in the address bar: on an https
public URL the cookie is `Secure`, so a browser that reached the gateway over plain http never sends it back.

## Login sends me to `http://keycloak:8080`, which does not resolve

**Cause.** Keycloak derives the URLs it advertises from the request's `Host`,
so a discovery fetch over the compose network hands the browser a
compose-internal name. The compose file pins `KC_HOSTNAME: http://localhost:8080`
to prevent this.

**Fix.** Confirm that pin is present on the `keycloak` service. If you removed
it, add `127.0.0.1 keycloak` to `/etc/hosts` instead — but the pin is the better
fix, because it needs no host changes.

## I signed in but see the catalogue, not the dashboard

**Cause.** Either the address is not in `BUNDLEMCP_ADMIN_EMAILS`, or the
identity provider is not releasing the `email` claim at all — in which case the
user is created and can never match the list.

```bash
curl -s http://localhost:8000/api/v1/me -b "cookie-jar"   # email: null is the tell
```

**Fix.** Admin status is re-evaluated at **every** login, so after editing the
list the user must log out and back in.

## claude.ai will not connect

Check in this order:

1. **Is the URL reachable from the internet?** claude.ai cannot reach
   `localhost`. You need a real deployment or a tunnel, with
   `BUNDLEMCP_PUBLIC_URL` set to the tunnel's URL.
2. **Is the profile `oauth_only`?** And is `auth_modes` exactly `["oauth"]`? The
   gateway refuses any other combination for that profile, so if the endpoint
   saved, this is already true.
3. **Does `BUNDLEMCP_PUBLIC_URL` match the URL claude.ai dialled?** The OAuth
   metadata is derived from it, so a mismatch fails during authorization rather
   than at connection.

## A raw HTTP client gets `400` on every request

**Cause.** A hand-built request must carry the stateless-era envelope —
`params._meta` with a protocol version and client capabilities, plus mirrored
`MCP-Protocol-Version`, `Mcp-Method` and (for `tools/call`) `Mcp-Name` headers.
A request with neither that envelope nor an `Mcp-Session-Id` is refused.

The error code says which rung failed: `-32602` for a missing envelope,
`-32020` for a header that disagrees with the body. See
[Request envelope](/integrate/http-surface#request-envelope).

**Fix.** Use an SDK, or copy the working `curl` from
[Scripts and CI](/connect/scripts).

## `/readyz` never turns green

**Cause.** Postgres or Valkey is unreachable, or the schema is behind the image (a migration failed or has not run
yet). The response body names which:

```bash
curl -s http://localhost:8000/readyz            # {"status": "not ready", "failing": [...], "checks": {...}}
docker compose -f deploy/docker-compose.yml logs gateway | grep -i alembic
```

Migrations run in the container's entrypoint before the server binds, so a
failing migration means the port never opens at all — which looks identical to
a crash loop. The alembic output is the difference.

## Every request is attributed to one IP, and rate limits behave oddly

**Cause.** `BUNDLEMCP_TRUSTED_PROXIES` is unset, so `X-Forwarded-For` is
ignored and every request appears to come from the proxy.

**Fix.** Set it to the CIDRs your proxies connect from.

If it is set and requests are attributed to one address that is not the proxy's,
a second proxy in the chain (a CDN or load balancer in front of your own) is not
listed. The gateway takes the rightmost `X-Forwarded-For` entry that is not a
trusted proxy, so an unlisted hop becomes the client. Add its ranges too.

## Large tool payloads fail, but only in production

**Cause.** The proxy's body limit, not the gateway's. The gateway accepts 4 MiB;
nginx's default `client_max_body_size` is 1 MB. If the `413` carries a JSON-RPC
error naming the limit, it is the gateway's own: the request is over
`max_request_bytes`.

**Fix.** The three proxy numbers are in
[Reverse proxy](/self-hosting/deploy#reverse-proxy). To accept larger bodies,
raise `max_request_bytes` in [runtime settings](/self-hosting/configuration#runtime-settings)
and the proxy's limit together.

## A tool call fails with "upstream response too large"

**Cause.** One message from the upstream server was larger than
`max_upstream_response_bytes` (16 MiB by default). The gateway stops reading it
rather than holding it in memory.

**Fix.** Make the tool return less, or raise `max_upstream_response_bytes` in
[runtime settings](/self-hosting/configuration#runtime-settings), up to 64 MiB.

## A server with `auth_mode: upstream_oauth` cannot be used

**Cause.** `BUNDLEMCP_TOKEN_ENCRYPTION_KEYS` is empty. The gateway boots
without it, but it will not store an upstream token it cannot encrypt.

**Fix.** Generate a Fernet key ([Secrets](/self-hosting/deploy#secrets)) and
restart. Existing connections are unaffected; new ones become possible.

## A change I made in the UI reverted after a restart

**Cause.** A bootstrap file is authoritative for every field it names, and it is
re-applied at every startup.

**Fix.** Either edit the document rather than the UI, or remove that resource
from the document. See [Bootstrap file](/self-hosting/bootstrap).

## Finding the log lines of one request

Every response carries an `X-Request-Id` header. Every gateway log line written while serving that request carries the
same value as `request_id`, so one filter finds them all:

```bash
docker compose -f deploy/docker-compose.yml logs gateway | grep '"request_id": "<the id>"'
```

A client that only kept the time of a failure can be found by its `client_ip` and the `endpoint` instead.

## Still stuck

Collect the gateway logs for the failing request (find them by its `X-Request-Id`; they carry the endpoint and the
caller, and never secrets), the output of
`GET /api/v1/upstreams/{name}` for an upstream problem, and
[open an issue](https://github.com/wingfold-ai/bundlemcp/issues).
