# Metering hook

The hook is the supported place for an application layer to plug in billing,
quotas or entitlement checks without forking the gateway. It is a small,
versioned Python protocol.

Every `tools/call` runs this chain, and the order matters to you because it
decides which calls you are asked about at all:

1. **Tool filter.** A tool disabled in the bundle is rejected here. No `pre_call`.
2. **Overrides and profile transform.**
3. **Upstream credential resolution.** A `per_user` server the caller has not
   connected, or an unconfigured upstream OAuth client, fails here with an audit
   record of `status: error`. **No `pre_call`, so nothing is debited** — you are
   never charged for a call that could not have gone out.
4. **`pre_call`.**
5. **The upstream call**, with at most one internal retry after a token refresh.
6. **`post_call`**, then the audit record.

## The contract

```python
from typing import Literal, Protocol, runtime_checkable

from bundlemcp.application.metering import MeterContext, MeterDecision

METERING_PROTOCOL_VERSION = 1

@runtime_checkable
class MeteringHook(Protocol):
    async def pre_call(self, ctx: MeterContext) -> MeterDecision: ...

    async def post_call(
        self, ctx: MeterContext, status: Literal["success", "error"], duration_ms: int
    ) -> None: ...
```

`MeterContext` is a frozen Pydantic model:

| Field | Meaning |
|---|---|
| `sub` | Caller identity: a user id, `api_key:<id>`, or `None` on an open endpoint. |
| `email` | The caller's email when the identity provider supplied one, else `None`. |
| `endpoint` | Endpoint name the call arrived on. |
| `bundle` | Bundle the endpoint exposes. |
| `server` | Upstream server the call routes to. |
| `tool` | Upstream tool name, without the bundle prefix or override. |
| `idempotency_key` | Stable key for one client invocation. |

`MeterDecision` has `allowed: bool` and an optional machine-readable `reason` such as `insufficient_credits`.

## Semantics

**Pre-call decides.** Returning `allowed=False` produces an MCP error carrying
your `reason` to the client, an audit record with `status=denied`, and no
upstream call.

**Post-call reports the outcome.** For an invocation that runs to completion,
one `post_call` is delivered with the final `status` and the upstream duration.
An MCP result with `isError: true` is `error`, as is a cancelled call. A failed
call after a successful debit is your refund trigger.

`duration_ms` is the upstream call only — not your hook, not gateway overhead —
so it is safe to bill on.

**Calls that pause for input.** A tool that asks the client a question produces
an audit record with `status: input_required` and **no `post_call`**. The
invocation resumes when the client retries, reusing the same
`idempotency_key`, and `pre_call` fires again on that resume. If the client
never retries — the user closes the tab, the agent gives up — no `post_call`
ever arrives. Treat a debit whose only audit record is `input_required`, older
than your window, as abandoned.

**`pre_call` can fire more than once for one key.** An internal retry (after
refreshing an upstream OAuth token) does *not* re-fire it. An `input_required`
resume does, with the key preserved. So: **make `pre_call` idempotent on
`idempotency_key` and charge exactly once per key.**

**The contract carries no amount, unit or currency.** Pricing is entirely
yours. The gateway asks one question — may this call proceed? — and reports one
fact: it ended this way, after this many milliseconds. `MeterContext` also gives
the *upstream* tool name; if you need the name the client saw, read
`presented_tool_name` from the audit record.

### Hook failures

| Situation | What the gateway does |
|---|---|
| `pre_call` raises | Denies the call (or allows it with `BUNDLEMCP_METERING_HOOK_FAIL_OPEN=true`), with `reason` `metering_unavailable`; logged as `metering.pre_call_failed`. That is a business decision, not a safety one. |
| `pre_call` hangs | **Nothing — there is no timeout.** The tool call waits as long as your hook does. |
| `post_call` raises or hangs | Logged as `metering.post_call_failed`. The call's own result is unaffected and the audit record is still written, so your refund simply never happens. |
| `pre_call` returns `allowed=False` | JSON-RPC error `-32000` whose `message` is your `reason` verbatim; audit `status: denied`, `denied_reason` = your `reason`; no upstream call. |

**Set your own timeout.** The gateway's call timeouts govern the *upstream*
call, not your hook, and it will not impose one for you. A hook that talks to a
network service and does not time out is a way to hang every tool call on the
gateway.

Note also that the denial the client sees is a free-text message, not a
structured code — `-32000` with your `reason` as the message and no `data`
field. A client cannot branch on `insufficient_credits` except by string
comparison; the audit log is the reliable discriminator. See
[Error responses](/integrate/errors).

## Installing a hook

Write a class that satisfies the protocol and expose an instance:

```python
# acme_billing/hook.py
import httpx
from bundlemcp.application.metering import MeterContext, MeterDecision

class LedgerHook:
    def __init__(self) -> None:
        # The gateway puts no timeout around the hook; set one here.
        self._http = httpx.AsyncClient(base_url="http://billing:8000", timeout=2.0)

    async def pre_call(self, ctx: MeterContext) -> MeterDecision:
        r = await self._http.post("/check-and-debit", json={
            "sub": ctx.sub, "email": ctx.email,
            "bundle_slug": ctx.bundle, "server_name": ctx.server, "tool_name": ctx.tool,
            "idempotency_key": ctx.idempotency_key,
        })
        if r.status_code == 402:
            return MeterDecision(allowed=False, reason="insufficient_credits")
        r.raise_for_status()
        return MeterDecision(allowed=True)

    async def post_call(self, ctx: MeterContext, status, duration_ms: int) -> None:
        if status == "error":
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

## Crash reconciliation

If the gateway dies between `pre_call` and `post_call`, no `post_call` fires
and nothing refunds. The [audit log](/manage/audit) is the reconciliation
source: for an invocation that passed `pre_call` and ran to completion, an audit
record with a terminal status exists.

::: warning There is no shared key between your ledger and an audit record
The audit record does **not** carry `idempotency_key` or any correlation id, so
you cannot look a debit up directly. Reconcile on `(sub, tool_name, created_at)`
within your window, and accept that two identical calls in the same instant are
ambiguous — which is exactly what a retry produces.
:::

Two cases produce a debit with no terminal audit record, and both need a
time-based sweep rather than a lookup: a crash between the two calls, and an
`input_required` call the client never resumed. Keep your audit retention
longer than your reconciliation window — noting that
[nothing purges the audit log for you](/manage/audit#retention).

## Versioning

`METERING_PROTOCOL_VERSION` is `1`. A change to the context, the decision or
the call pattern bumps it and is a breaking change in the gateway's release
notes. The hook is not consulted for `tools/list`; entitlement-based tool
hiding is not part of version 1.

## Next steps

- [Audit log](/manage/audit) — the reconciliation source and its fields.
- [Error responses](/integrate/errors) — what a denied caller actually receives.
- [Management API](/integrate/management-api#stability) — what `/api/v1` and
  `METERING_PROTOCOL_VERSION` each promise.
