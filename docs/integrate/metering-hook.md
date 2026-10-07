# Metering hook

Every `tools/call` passes through a middleware chain: tool filter, overrides, profile transform, **metering hook**,
audit. The hook is the supported place for an application layer to plug in billing, quotas or entitlement checks without
forking the gateway. It is a small, versioned Python protocol.

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

**Pre-call decides.** `pre_call` runs after the tool filter, overrides and profile transform, so a call to a disabled
tool never reaches it. Returning `allowed=False` produces a structured MCP error carrying `reason` to the client, an
audit record with `status=denied`, and no upstream call.

**Post-call reports the outcome.** Exactly one `post_call` is delivered for every invocation whose `pre_call` allowed
it, with the final `status` and the upstream duration. An MCP result with `isError: true` is `error`, as is a cancelled
call. A failed call after a successful debit is your refund trigger.

**Retries do not double-charge.** The gateway retries a call internally in a few cases, such as once after refreshing an
upstream OAuth token. `pre_call` fires once per client invocation, and the retry reuses the same `idempotency_key`.
Charge exactly once per key.

**Hook failures.** If the hook raises, the call is denied by default. `BUNDLEMCP_METERING_HOOK_FAIL_OPEN=true` lets it
proceed with a log line; that is a business decision, not a safety one.

## Installing a hook

Write a class that satisfies the protocol and expose an instance:

```python
# acme_billing/hook.py
import httpx
from bundlemcp.application.metering import MeterContext, MeterDecision

class LedgerHook:
    def __init__(self) -> None:
        self._http = httpx.AsyncClient(base_url="http://billing:8000")

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

The gateway checks at startup that the object has both methods and refuses to boot otherwise, so a typo surfaces
immediately rather than on the first call.

## Crash reconciliation

If the gateway dies between `pre_call` and `post_call`, no `post_call` fires and nothing refunds. The
[audit log](/manage/audit) is the reconciliation source: for every invocation that passed `pre_call`, an audit record
with a terminal status eventually exists. A debit in your ledger with no audit record for its idempotency window is a
lost invocation to refund out of band. Keep `audit_retention_days` longer than your reconciliation window.

## Versioning

`METERING_PROTOCOL_VERSION` is `1`. A change to the context, the decision or the call pattern bumps it and is a breaking
change in the gateway's release notes. The hook is not consulted for `tools/list`; entitlement-based tool hiding is not
part of version 1.
