"""The tools/call pipeline: authorise, meter, drive the upstream, account."""

import asyncio
import json
import time
import uuid

import structlog
from fastapi import Request, Response
from fastapi.responses import StreamingResponse

from bundlemcp.gateway.composition import BundleView
from bundlemcp.gateway.mcp_endpoint.call_outcome import CallOutcome
from bundlemcp.gateway.mcp_endpoint.caller_identity import caller_sub
from bundlemcp.gateway.mcp_endpoint.forwarded_headers import forwarded_headers
from bundlemcp.gateway.mcp_endpoint.gateway_runtime import GatewayRuntime
from bundlemcp.gateway.mcp_endpoint.jsonrpc import rpc_error, rpc_result
from bundlemcp.gateway.mcp_endpoint.upstream_driver import drive_upstream
from bundlemcp.gateway.metering import MeterContext, MeterDecision, new_idempotency_key
from bundlemcp.models import AuditRecord, AuditStatus, IdentityMode, ServerAuthMode
from bundlemcp.oauth.upstream_client import NeedsConnect
from bundlemcp.store.sessions import SessionRecord

log = structlog.get_logger(__name__)


async def _timeout_config(runtime: GatewayRuntime) -> tuple[float, bool, float]:
    """Timeout values from runtime config; unset keys fall back to the registry."""
    rc = runtime.runtime_config
    return (
        float(await rc.get("call_timeout")),
        bool(await rc.get("reset_timeout_on_progress")),
        float(await rc.get("max_total_timeout")),
    )


def _sse_call_response(
    runtime,
    pt,
    arguments,
    extra_headers,
    record,
    sub,
    handle,
    cfg,
    progress_token,
    rpc_id,
    finalize,
) -> Response:
    """Stream notifications/progress, then the final JSON-RPC result."""

    async def gen():
        queue: asyncio.Queue = asyncio.Queue()

        async def on_progress(progress, total, message):
            note = {
                "jsonrpc": "2.0",
                "method": "notifications/progress",
                "params": {
                    "progressToken": progress_token,
                    "progress": progress,
                    **({"total": total} if total is not None else {}),
                    **({"message": message} if message else {}),
                },
            }
            await queue.put(("progress", note))

        started = time.monotonic()

        async def runner():
            outcome = await drive_upstream(
                runtime,
                pt,
                arguments,
                extra_headers,
                record,
                sub,
                handle,
                cfg,
                on_progress=on_progress,
            )
            await queue.put(("final", outcome))

        task = asyncio.create_task(runner())
        try:
            while True:
                kind, data = await queue.get()
                if kind == "progress":
                    yield f"data: {json.dumps(data)}\n\n"
                    continue
                outcome: CallOutcome = data
                if handle is not None:
                    runtime.registry.unregister_call(handle)
                duration_ms = int((time.monotonic() - started) * 1000)
                await finalize(outcome.status, duration_ms, outcome.error_message)
                if outcome.result is not None:
                    payload = outcome.result.model_dump(
                        by_alias=True, mode="json", exclude_none=True
                    )
                    msg = {"jsonrpc": "2.0", "id": rpc_id, "result": payload}
                else:
                    msg = {
                        "jsonrpc": "2.0",
                        "id": rpc_id,
                        "error": {
                            "code": outcome.code or -32000,
                            "message": outcome.error_message or "call failed",
                        },
                    }
                yield f"data: {json.dumps(msg)}\n\n"
                break
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


async def handle_call(
    runtime: GatewayRuntime,
    request: Request,
    view: BundleView,
    record: SessionRecord,
    body: dict,
) -> Response:
    params = body.get("params") or {}
    presented_name = params.get("name", "")
    arguments = params.get("arguments") or {}
    rpc_id = body.get("id")

    sub = caller_sub(record)

    pt = view.resolve(presented_name)
    audit_kwargs = dict(
        endpoint_id=view.endpoint.id,
        endpoint_name=view.endpoint.name,
        bundle_name=view.bundle.name,
        presented_tool_name=presented_name,
        user_id=uuid.UUID(record.user_id) if record.user_id else None,
        api_key_id=uuid.UUID(record.api_key_id) if record.api_key_id else None,
        auth_method=record.auth_method,
        session_id=record.session_id,
    )
    if pt is None:
        # TM-2: disabled/unknown tools are rejected on call, not just hidden
        runtime.audit.record(
            AuditRecord(
                status=AuditStatus.DENIED, denied_reason="unknown_or_disabled_tool", **audit_kwargs
            )
        )
        return rpc_error(rpc_id, -32602, f"Unknown tool: {presented_name}")

    audit_kwargs["server_name"] = pt.server.name
    audit_kwargs["tool_name"] = pt.tool.name

    # spec 23: resolve the upstream OAuth bearer BEFORE metering, so an
    # unconnected upstream is never debited.
    is_upstream_oauth = pt.server.auth_mode == ServerAuthMode.UPSTREAM_OAUTH
    upstream_token_user: uuid.UUID | None = None
    upstream_headers: dict[str, str] = {}
    if is_upstream_oauth:
        if runtime.upstream_tokens is None:
            runtime.audit.record(
                AuditRecord(
                    status=AuditStatus.ERROR,
                    error_message="upstream OAuth not configured",
                    **audit_kwargs,
                )
            )
            return rpc_error(rpc_id, -32000, "upstream OAuth not configured on this gateway")
        per_user = pt.server.identity_mode == IdentityMode.PER_USER
        if per_user:
            if record.user_id is None:  # UPO-6 guard (should be unreachable)
                return rpc_error(
                    rpc_id, -32000, "per_user upstream requires an authenticated user"
                )
            upstream_token_user = uuid.UUID(record.user_id)
        try:
            access = await runtime.upstream_tokens.ensure_access_token(
                pt.server, upstream_token_user
            )
        except NeedsConnect:
            suffix = "?as=me" if per_user else ""
            connect_url = f"{runtime.public_url}/oauth/upstream/{pt.server.name}/connect{suffix}"
            runtime.audit.record(
                AuditRecord(
                    status=AuditStatus.ERROR, error_message="upstream_not_connected", **audit_kwargs
                )
            )
            return rpc_error(rpc_id, -32000, f"upstream not connected — connect at {connect_url}")
        upstream_headers = {"Authorization": f"Bearer {access}"}

    ctx = MeterContext(
        sub=sub,
        email=record.user_email,
        endpoint=view.endpoint.name,
        bundle=view.bundle.name,
        server=pt.server.name,
        tool=pt.tool.name,
        idempotency_key=new_idempotency_key(),  # MID-3: once per client invocation
    )
    try:
        decision: MeterDecision = await runtime.metering.pre_call(ctx)
    except Exception:
        log.error("metering.pre_call_failed", exc_info=True)
        # MID-3: fail-open is the gateway's policy, not the hook's property.
        fail_open = runtime.settings.metering_hook_fail_open
        decision = MeterDecision(allowed=fail_open, reason="metering_unavailable")
    if not decision.allowed:
        runtime.audit.record(
            AuditRecord(
                status=AuditStatus.DENIED,
                denied_reason=decision.reason or "denied",
                **audit_kwargs,
            )
        )
        return rpc_error(rpc_id, -32000, decision.reason or "call denied")

    extra_headers = forwarded_headers(request.headers, pt.server, sub)
    extra_headers.update(upstream_headers)  # spec 23: upstream OAuth bearer wins
    progress_token = (params.get("_meta") or {}).get("progressToken")
    cfg = await _timeout_config(runtime)

    async def finalize(status: str, duration_ms: int, error_message: str | None) -> None:
        try:
            await runtime.metering.post_call(ctx, status, duration_ms)  # refund trigger
        except Exception:
            log.error("metering.post_call_failed", exc_info=True)
        runtime.audit.record(
            AuditRecord(
                status=AuditStatus.SUCCESS if status == "success" else AuditStatus.ERROR,
                duration_ms=duration_ms,
                error_message=error_message,
                **audit_kwargs,
            )
        )

    handle = None
    if rpc_id is not None:
        handle = runtime.registry.register_call(record.session_id, str(rpc_id))

    # PROT-1: when the client sent a progressToken, stream progress as SSE and
    # deliver the result as the final event. Otherwise the buffered JSON path.
    if progress_token is not None:
        return _sse_call_response(
            runtime,
            pt,
            arguments,
            extra_headers,
            record,
            sub,
            handle,
            cfg,
            progress_token,
            rpc_id,
            finalize,
        )

    started = time.monotonic()
    outcome = await drive_upstream(
        runtime, pt, arguments, extra_headers, record, sub, handle, cfg, on_progress=None
    )
    # UPO-4 reactive: on an upstream error for an oauth server, force-refresh the
    # token and retry once (covers a 401 despite a non-expired token). The same
    # metering ctx is reused — internal retry does NOT re-fire pre_call (MID-3).
    if outcome.result is None and is_upstream_oauth and runtime.upstream_tokens is not None:
        try:
            access = await runtime.upstream_tokens.ensure_access_token(
                pt.server, upstream_token_user, force=True
            )
            extra_headers = {**extra_headers, "Authorization": f"Bearer {access}"}
            outcome = await drive_upstream(
                runtime, pt, arguments, extra_headers, record, sub, handle, cfg, on_progress=None
            )
        except NeedsConnect:
            pass  # keep the original error outcome
    if handle is not None:
        runtime.registry.unregister_call(handle)
    duration_ms = int((time.monotonic() - started) * 1000)
    await finalize(outcome.status, duration_ms, outcome.error_message)
    if outcome.result is not None:
        payload = outcome.result.model_dump(by_alias=True, mode="json", exclude_none=True)
        return rpc_result(rpc_id, payload)
    return rpc_error(rpc_id, outcome.code or -32000, outcome.error_message or "call failed")
