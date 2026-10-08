# Error responses

The gateway serves two protocols, so it has two error vocabularies: HTTP with
a JSON body on the management API and the OAuth server, JSON-RPC on the MCP
edge. A client that treats them as one shape will mis-parse the other.

## The four body shapes

| Shape | Emitted by | Example |
|---|---|---|
| `{"detail": "<message>"}` | A domain rule on the management API | `{"detail": "server 'echo' not found"}` |
| `{"detail": [{"loc": …, "msg": …, "type": …}]}` | Request validation, always `422` | `{"detail":[{"loc":["body","url"],"msg":"invalid URL","type":"value_error"}]}` |
| `{"error": "<code>", "error_description": "…"}` | The OAuth server (RFC 6749 §5.2) and auth-failure lockouts | `{"error":"invalid_grant","error_description":"code expired"}` |
| `{"jsonrpc":"2.0","id":…,"error":{"code":…,"message":…,"data":…}}` | The MCP edge | `{"jsonrpc":"2.0","id":1,"error":{"code":-32000,"message":"insufficient_credits"}}` |

Note that `detail` is a string on a domain error and a **list of objects** on a
validation error. Branch on the type, not on the key.

Two MCP-edge responses are HTTP-shaped rather than JSON-RPC, because they are
refused before any JSON-RPC message is parsed: an unknown endpoint answers
`404 {"error": "not found"}`, and a dead or foreign session id answers
`404 {"error": "session not found"}`. A session is foreign when it was opened on
another endpoint or by another caller: only the user or API key that opened a
session can use or end it, and the answer does not reveal that it exists. A body over the size cap answers `413`
with a plain-text body and no JSON at all.

## Management API status codes

| Status | Meaning |
|---|---|
| `400` | A precondition of the operation does not hold. |
| `401` | No credential, an invalid credential, **or a signed-in user who is not an administrator**. |
| `403` | An endpoint-kind API key was used, or a cookie-authenticated mutation failed the `Origin`/`Referer` check. |
| `404` | The named resource does not exist. |
| `409` | The write conflicts with an existing resource, such as a name already in use. |
| `422` | Request validation, including a body `name` that differs from the path `name`. |
| `429` | An auth-failure lockout, with `Retry-After`. |
| `503` | A dependency the operation needs is unavailable. |

A non-administrator who is signed in receives `401`, not `403`. This is worth
designing for explicitly: a browser client cannot distinguish "session
expired" from "not an administrator" by status alone, so treat `401` on
`/api/v1` as *either*, and use [`GET /api/v1/me`](/integrate/management-api)
— which answers for any signed-in user — to tell them apart.

## JSON-RPC codes on the MCP edge

| Code | Name | Cause | HTTP |
|---|---|---|---|
| `-32700` | parse error | The body is not JSON, or not a JSON-RPC object | `400` |
| `-32600` | invalid request | A stateless client sent a JSON-RPC *response* | `400` |
| `-32602` | invalid params | A missing or malformed `params._meta` envelope, an unknown log level, or bad method parameters | `400` |
| `-32601` | method not found | The method is not registered | `404` |
| `-32020` | header mismatch | A mirrored header disagrees with the body — see [Request envelope](/integrate/http-surface#request-envelope) | `400` |
| `-32022` | unsupported protocol version | `data` carries `supported` and `requested` | `400` |
| `-32000` | upstream failure | The upstream call failed, was denied by the metering hook, or needs an upstream connection the caller has not made | `200` |
| `-32800` | cancelled | The call was cancelled, by the client or by the total-timeout ceiling | `200` |

`-32000` and `-32800` arrive with HTTP `200` because they are the *result* of a
successfully routed call, and on a streamed `tools/call` they are the last SSE
event rather than the response body.

### `-32000` carries no discriminator

The message is free text: your own `reason` verbatim from a metering denial, or
a connect hint naming the URL when a `per_user` upstream is not connected.
There is no `data` field and no machine-readable code, so a client that must
distinguish these cases matches on the message. Two facts make that more
robust than it sounds:

- A metering denial is audited as `status: denied` with `denied_reason` set to
  the same string.
- A missing upstream connection is audited as `status: error` with
  `error_message: upstream_not_connected`.

So the [audit log](/manage/audit) disambiguates after the fact even where the
wire response does not.

## Retrying

| Response | Retry? |
|---|---|
| `429` | Yes, after `Retry-After`. |
| `503` | Yes, with backoff. |
| `-32000` upstream failure | Once, with backoff. The gateway already retried an expired upstream token internally. |
| `-32800` cancelled | No. Cancellation was deliberate or the ceiling was reached. |
| `-32020`, `-32022`, `-32602`, `422` | No. Fix the request. |
| `401` | No. Get a new credential first. |

## Next steps

- [HTTP surface](/integrate/http-surface) — every route and the request envelope.
- [Management API](/integrate/management-api) — conventions and routes.
- [Audit](/manage/audit) — what each failure records.
