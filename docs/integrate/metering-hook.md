---
description: "The bundlemcp metering hook: a versioned Python protocol, in process or over HTTP, to add billing,
  quotas or entitlement checks to MCP tool calls."
---

# Metering hook

The hook is the supported place for an application layer to plug in billing,
quotas or entitlement checks without forking the gateway. It is a small,
versioned Python protocol. It can run in the gateway's process or out of
process, as a separate service the gateway calls [over HTTP](#over-http), for
deployments that run the published image unchanged.

Every `tools/list` and `tools/call` passes one chain of stages: tool filter, profile, overrides, metering, audit. The
first three decide the tools an endpoint serves; a list shows them and a call is resolved against them. The order
matters to you because it decides which calls you are asked about at all:

1. **Tool filter.** A tool disabled in the bundle, or gone from its upstream's latest tool list, is rejected here. No
   `pre_call`.
2. **Profile, then overrides**, so an explicit override wins over the profile's rewrite.
3. **Upstream credential resolution.** A `per_user` server the caller has not
   connected, or an unconfigured upstream OAuth client, fails here with an audit
   record of `status: error`. **No `pre_call`, so nothing is debited** — you are
   never charged for a call that could not have gone out.
4. **`pre_call`**, once per client invocation.
5. **The upstream call**, with at most one internal retry after a token refresh.
6. **`post_call`**, once per invocation, then the audit record. The audit stage also records a call an earlier stage
   refused.

## The contract

```python
from typing import Protocol, runtime_checkable

from bundlemcp.application.metering import MeterContext, MeterDecision, MeterOutcome

METERING_PROTOCOL_VERSION = 2

@runtime_checkable
class MeteringHook(Protocol):
    async def pre_call(self, ctx: MeterContext) -> MeterDecision: ...

    async def post_call(
        self, ctx: MeterContext, outcome: MeterOutcome, duration_ms: int
    ) -> None: ...
```

`MeterContext` is a frozen Pydantic model:

| Field | Meaning |
|---|---|
| `sub` | Caller identity: a user id, `api_key:<id>`, or `None` on an open endpoint. |
| `email` | The caller's email when the identity provider supplied one, else `None`. |
| `oidc_issuer` | Issuer of the identity provider that authenticated the user; `None` for an API key or an open endpoint. |
| `oidc_sub` | The user's subject at that identity provider, e.g. the Keycloak `sub`; `None` when `oidc_issuer` is. |
| `auth_method` | How the caller authenticated: `oauth`, `api_key` or `none`. |
| `endpoint` | Endpoint name the call arrived on. |
| `profile` | The endpoint's profile, e.g. `default` or `write_as_read`. |
| `bundle` | Bundle the endpoint exposes. |
| `session_id` | MCP session of a handshake-era client; `None` for a modern-era request, which has no session. |
| `server` | Upstream server the call routes to. |
| `tool` | Upstream tool name, without the bundle prefix or override. |
| `idempotency_key` | Stable key for one client invocation. |
| `headers` | The client's request headers, names lower-cased, read-only. `authorization`, `proxy-authorization`, `cookie` and `x-api-key` are removed. |
| `scratch` | A mapping your `pre_call` fills and your `post_call` receives as you left it, e.g. a reservation id; at most 4 KiB as JSON. |

Only those four headers are removed. If a client sends a credential in a header of your own, such as
`x-acme-token`, it reaches the hook too; add it to the deny-list your servers' `forward_headers` already respect, and
do not log `headers` wholesale.

An in-process hook writes `ctx.scratch["reservation"] = …` in `pre_call`; an HTTP hook returns a `scratch` object in
its decision. A `scratch` over 4 KiB is dropped and logged as `metering.scratch_too_large`.

`sub` is the gateway's own user id, stable only within this gateway's database. If your ledger keys users on the
identity provider's subject, key on `(oidc_issuer, oidc_sub)` instead: it is the same for every login of a user,
survives a rebuild or restore of the gateway, and is known for users who have not yet signed in through the gateway.
Never key on `email`, which can change and be reused.

`MeterDecision` has `allowed: bool`, an optional machine-readable `reason` such as `insufficient_credits`, and an
optional `user_message`: text for the person behind the client, such as "Your credits are used up. Top up at
https://example.com/account", at most 2000 characters, and an optional `scratch` mapping merged into the context's.

`MeterOutcome` is a string enum:

| Outcome | When |
|---|---|
| `result` | The upstream returned a tool result. |
| `tool_error` | The upstream returned a tool result with `isError: true`. The tool ran and reported a failure. |
| `no_result` | No tool result: the upstream was unreachable or timed out, answered a JSON-RPC error, the gateway refused the call after `pre_call` allowed it, `pre_call` itself gave no answer, or the call paused for client input and the client never came back. |
| `cancelled` | The client cancelled the call or closed its stream before a result arrived. |

## Semantics

**Pre-call decides.** Returning `allowed=False` writes an audit record with
`status=denied` and makes no upstream call. With a `user_message`, the client
receives a tool result with `isError: true` whose only content is your text,
verbatim, so the model tells the person. Without one, it receives an MCP error
carrying your `reason`.

**Post-call reports the outcome.** For an invocation that runs to completion,
one `post_call` is delivered with the final `outcome` and the upstream duration.
The gateway does not decide what an outcome costs: whether `tool_error` (the
tool ran) is charged like `result` or refunded like `no_result` is your call.

`duration_ms` is the upstream call only — not your hook, not gateway overhead —
so it is safe to bill on.

**Calls that pause for input.** A tool that asks the client a question produces
an audit record with `status: input_required` and **no `post_call` yet**. The
invocation continues when the client retries, under the same `idempotency_key`
and with the same context, `scratch` included, and **`pre_call` does not fire
again**: you decided on the first leg, and cannot refuse a later one. The one
`post_call` comes when the invocation ends. If the client never retries — the
user closes the tab, the agent gives up — the gateway delivers `post_call`
`no_result` with `duration_ms` 0 once the call's `requestState` has expired,
within about 30 seconds after.

The gateway keeps the paused invocation in Valkey. If that record is lost, for
example with a Valkey restart while the call waits, the retry runs `pre_call`
again under the same key and logs `metering.invocation_record_missing`. So:
**keep `pre_call` idempotent on `idempotency_key`** and charge at most once per key.

**The contract carries no amount, unit or currency.** Pricing is entirely
yours. The gateway asks one question — may this call proceed? — and reports one
fact: it ended this way, after this many milliseconds. `MeterContext` also gives
the *upstream* tool name; if you need the name the client saw, read
`presented_tool_name` from the audit record.

### Hook failures

| Situation | What the gateway does |
|---|---|
| `pre_call` raises | Denies the call (or allows it with `BUNDLEMCP_METERING_HOOK_FAIL_OPEN=true`), with `reason` `metering_unavailable`; logged as `metering.pre_call_failed`. That is a business decision, not a safety one. A denied call is then reported to `post_call` as `no_result` with `duration_ms` 0 under the same `idempotency_key`, in case your hook debited before it failed. |
| `pre_call` hangs | **Nothing — there is no timeout** for an in-process hook. The tool call waits as long as your hook does. The HTTP hook times out after `BUNDLEMCP_METERING_HTTP_TIMEOUT`. |
| `post_call` raises or hangs | Logged as `metering.post_call_failed`. The call's own result is unaffected and the audit record is still written, so your refund simply never happens. |
| `pre_call` returns `allowed=False` | With a `user_message`: a tool result with `isError: true` carrying it. Without: JSON-RPC error `-32000` whose `message` is your `reason` verbatim. Either way audit `status: denied`, `denied_reason` = your `reason`, and no upstream call. |

**Set your own timeout.** The gateway's call timeouts govern the *upstream*
call, not your hook, and it will not impose one for you. A hook that talks to a
network service and does not time out is a way to hang every tool call on the
gateway.

Note also that a denial without a `user_message` reaches the client as a
free-text message, not a structured code — `-32000` with your `reason` as the
message and no `data` field. A client cannot branch on `insufficient_credits` except by string
comparison; the audit log is the reliable discriminator. See
[Error responses](/integrate/errors).

## Installing a hook

Write a class that satisfies the protocol and expose an instance:

```python
# acme_billing/hook.py
import httpx
from bundlemcp.application.metering import MeterContext, MeterDecision, MeterOutcome

class LedgerHook:
    def __init__(self) -> None:
        # The gateway puts no timeout around the hook; set one here.
        self._http = httpx.AsyncClient(base_url="http://billing:8000", timeout=2.0)

    async def pre_call(self, ctx: MeterContext) -> MeterDecision:
        r = await self._http.post("/check-and-debit", json={
            "sub": ctx.sub, "email": ctx.email, "oidc_sub": ctx.oidc_sub,
            "bundle_slug": ctx.bundle, "server_name": ctx.server, "tool_name": ctx.tool,
            "idempotency_key": ctx.idempotency_key,
        })
        if r.status_code == 402:
            return MeterDecision(
                allowed=False,
                reason="insufficient_credits",
                user_message="Your credits are used up. Top up at https://acme.example/account",
            )
        r.raise_for_status()
        return MeterDecision(allowed=True)

    async def post_call(self, ctx: MeterContext, outcome: MeterOutcome, duration_ms: int) -> None:
        if outcome in (MeterOutcome.NO_RESULT, MeterOutcome.CANCELLED):
            await self._http.post("/refund", json={"idempotency_key": ctx.idempotency_key})

hook = LedgerHook()
```

Make the module importable in the gateway's environment, for example by installing your package into the gateway image,
and point the gateway at the attribute:

```
BUNDLEMCP_METERING_HOOK=acme_billing.hook:hook
```

The attribute may be the instance itself or a zero-argument callable returning
one, so `acme_billing.hook:LedgerHook` works as well as `…:hook`. A factory is
the usual way to inject configuration.

The gateway checks at startup that the object has both methods and refuses
to boot otherwise, so a typo surfaces immediately rather than on the first
call.

## Over HTTP

When the hook runs as its own service, there is no need to install Python into
the gateway image. Point the gateway at the service instead:

```
BUNDLEMCP_METERING_HTTP_URL=http://metering:8000/hook
BUNDLEMCP_METERING_HTTP_TOKEN=<secret>
BUNDLEMCP_METERING_HTTP_TIMEOUT=2
```

`BUNDLEMCP_METERING_HTTP_URL` and `BUNDLEMCP_METERING_HOOK` are exclusive; the
gateway refuses to start with both. Every event is a `POST` of JSON to that one
URL, with `Authorization: Bearer <token>` when a token is set.

**Pre-call.** The body is the context above under `context`:

```json
{
  "protocol_version": 2,
  "event": "pre_call",
  "context": {
    "sub": "api_key:3f…", "email": null, "oidc_issuer": null, "oidc_sub": null,
    "auth_method": "api_key", "endpoint": "main", "profile": "default", "bundle": "main",
    "session_id": null, "server": "echo", "tool": "say", "idempotency_key": "9c1e…",
    "headers": {"user-agent": "claude-code/2.1"}, "scratch": {}
  }
}
```

Answer `2xx` with a decision. `reason`, `user_message` and `scratch` are optional:

```json
{"allowed": false, "reason": "insufficient_credits", "user_message": "Your credits are used up."}
```

```json
{"allowed": true, "scratch": {"reservation": "r-81f2"}}
```

A pre-call that is not answered within the timeout, cannot be sent, gets a
non-2xx status, or gets a body that is not a decision (`"allowed": "yes"` is
not one) counts as unanswered: the call is denied unless
`BUNDLEMCP_METERING_HOOK_FAIL_OPEN=true`, and a `no_result` post-call follows
for the same key.

**Post-call.** The same `context`, with the `scratch` your decision returned, plus `outcome` and `duration_ms`:

```json
{"protocol_version": 2, "event": "post_call", "context": {…}, "outcome": "no_result", "duration_ms": 0}
```

Any `2xx` acknowledges it. Post-calls are sent in the background, so a tool
result never waits for your service. A transport error, a timeout, a `429` or a
`5xx` is retried, five tries within about a minute, after which the gateway
logs `metering.post_call_failed` with the `idempotency_key`. Any other status is
taken as your answer and not retried. Because a post-call can arrive more than
once, make it idempotent on `idempotency_key` too.

## Crash reconciliation

If the gateway dies between `pre_call` and `post_call`, no `post_call` fires and nothing refunds. The
[audit log](/manage/audit) is the reconciliation source, and every audit record of a metered invocation carries the
`idempotency_key` your hook received, on every leg of it. Reconcile by that key:

```bash
curl -s -H "Authorization: Bearer $SERVICE_KEY" \
  "$GATEWAY/api/v1/audit-records?idempotency_key=$KEY"
```

- **A terminal record** (`success`, `error` or `denied`) means the invocation ended; settle the debit by its outcome.
- **No record at all** after your reconciliation window means the record was lost. Every loss the gateway knows of is
  logged with the key (`audit.queue_overflow`, `audit.write_failed`, `audit.lost_on_shutdown`); only a process killed
  outright loses one silently, and the key in your `pre_call` is still how you find it.
- **Only an `input_required` record** means the client never came back; the gateway delivers `post_call` with
  `no_result` once the request state expires.

A call denied before metering, such as an unknown tool, has no key and was never debited. Keep the audit retention
(`audit_retention_days`, 90 days by default) longer than your reconciliation window.

## Versioning

`METERING_PROTOCOL_VERSION` is `2`. A change that breaks a hook written against
the documented contract bumps it and is a breaking change in the gateway's
release notes; new optional fields do not. The
[`CHANGELOG.md`](https://github.com/wingfold-ai/bundlemcp/blob/main/CHANGELOG.md)
entry of a release that changes it says so, as a breaking change; an entry that
does not mention the protocol leaves it unchanged. The GitHub release notes always
end with the version and say whether it changed since the previous release, so
watching the repository's releases is enough to hear about a change. The HTTP bodies carry the version as
`protocol_version`. The hook is not consulted for `tools/list`;
entitlement-based tool hiding is not part of version 2.

Within version 2 the context gained `auth_method`, `profile`, `session_id`,
`headers` and `scratch`, and the decision `scratch`. A call that pauses for
client input now fires `pre_call` once rather than on every leg, and an
abandoned one now receives `post_call` `no_result`. A hook that was idempotent
on `idempotency_key`, as this page always asked, sees one call fewer and one
more report, both under keys it already knows.

Version 2 replaced the `status` argument of `post_call` (`success` or `error`)
with `outcome`. To port a version 1 hook, treat `result` as `success` and every
other outcome as `error`, then decide whether `tool_error` should really be
refunded.

## Next steps

- [Audit log](/manage/audit) — the reconciliation source and its fields.
- [Error responses](/integrate/errors) — what a denied caller actually receives.
- [Management API](/integrate/management-api#stability) — what `/api/v1` and
  `METERING_PROTOCOL_VERSION` each promise.
