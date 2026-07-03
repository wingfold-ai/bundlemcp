"""Public MCP endpoints: POST/GET/DELETE /{endpoint_name}/mcp (specs 14/30/31).

The Streamable-HTTP edge is implemented directly here (not via FastMCP's
server session manager) so that session state lives in Redis and any replica
serves any request (SES-2, ADR-0011). FastMCP is used for the upstream side.
"""

import time
import uuid
from dataclasses import dataclass
from typing import Any

import structlog
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from bundlemcp.api.deps import resolve_api_key
from bundlemcp.gateway.composition import BundleView, PresentedTool, load_bundle_view
from bundlemcp.gateway.metering import MeterContext, MeterDecision, new_idempotency_key
from bundlemcp.gateway.metrics import RATE_LIMIT_REJECTIONS, Counters
from bundlemcp.gateway.proxy import client_ip
from bundlemcp.models import (
    AuditRecord,
    AuditStatus,
    EndpointAuthMode,
    IdentityMode,
    ServerAuthMode,
)
from bundlemcp.oauth.upstream_client import NeedsConnect
from bundlemcp.store.sessions import SessionRecord, SessionStore, UpstreamBinding

log = structlog.get_logger(__name__)

router = APIRouter()

PROTOCOL_VERSION = "2025-11-25"
SESSION_HEADER = "mcp-session-id"

# FWD-2: never forwardable, enforced at runtime on top of write-time checks
DENIED_FORWARD_HEADERS = {"host", "content-length", "cookie", "x-api-key", "mcp-session-id"}
IDENTITY_HEADER = "X-MCP-User"


def _rpc_result(id_: Any, result: dict) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": id_, "result": result})


def _rpc_error(id_: Any, code: int, message: str, status: int = 200) -> JSONResponse:
    return JSONResponse(
        {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}},
        status_code=status,
    )


def _unauthorized(request: Request, endpoint_name: str) -> Response:
    """EP-3: 401 with the challenge + per-endpoint protected-resource metadata (RFC 9728)."""
    base = str(request.app.state.settings.public_url).rstrip("/")  # DEP-1, not Host header
    metadata = f"{base}/.well-known/oauth-protected-resource/{endpoint_name}/mcp"
    return JSONResponse(
        {"error": "unauthorized"},
        status_code=401,
        headers={"WWW-Authenticate": f'Bearer resource_metadata="{metadata}"'},
    )


async def _resolve_oauth_bearer(
    request: Request, db: AsyncSession, view: BundleView
) -> tuple[str, str | None] | None:
    """OAS-7 direct-DB bearer validation + EP-3a audience check.

    Returns (user_id, email) or None.
    """
    from bundlemcp.models import OAuthAccessToken, User, utcnow
    from bundlemcp.security import ACCESS_TOKEN_PREFIX, hash_token

    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer ") or not auth[7:].startswith(ACCESS_TOKEN_PREFIX):
        return None
    from datetime import UTC

    from sqlmodel import select

    row = (
        await db.execute(
            select(OAuthAccessToken).where(
                OAuthAccessToken.access_token_hash == hash_token(auth[7:])
            )
        )
    ).scalar_one_or_none()
    if row is None or row.revoked:
        return None
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if expires < utcnow():
        return None
    if row.endpoint_id != view.endpoint.id:
        return None  # EP-3a: audience mismatch -> 401 invalid_token
    user = (await db.execute(select(User).where(User.id == row.user_id))).scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    return (str(user.id), user.email)


async def _authenticate(
    request: Request, db: AsyncSession, view: BundleView
) -> tuple[str, str | None, str | None, str | None] | None:
    """EP-3/EP-3b/EP-6: returns (auth_method, user_id, user_email, api_key_id) or None.

    Precedence oauth > api_key (EP-3b).
    """
    modes = set(view.endpoint.auth_modes)
    if EndpointAuthMode.OAUTH in modes:
        oauth = await _resolve_oauth_bearer(request, db, view)
        if oauth is not None:
            user_id, email = oauth
            return ("oauth", user_id, email, None)
    if EndpointAuthMode.API_KEY in modes:
        key = await resolve_api_key(request, db)
        if key is not None:
            if key.kind == "endpoint" and key.endpoint_ids:
                if str(view.endpoint.id) not in key.endpoint_ids:
                    return None  # scoped key, wrong endpoint (KEY-2)
            return ("api_key", None, None, str(key.id))
    if EndpointAuthMode.NONE in modes:
        return ("none", None, None, None)
    return None


def _rate_identity(user_id: str | None, api_key_id: str | None, ip: str) -> str:
    """EP-6/RATE-1 per-client bucket key: OAuth user, else API key, else client IP."""
    if user_id:
        return f"user:{user_id}"
    if api_key_id:
        return f"apikey:{api_key_id}"
    return f"ip:{ip}"


async def _enforce_rate_limit(
    runtime: "GatewayRuntime",
    request: Request,
    view: BundleView,
    user_id: str | None,
    api_key_id: str | None,
    rpc_id: Any,
    *,
    is_tool_call: bool,
) -> Response | None:
    """RATE-1/3/4/6/7: endpoint + per-client fixed-window limits.

    Returns a 429 (+ Retry-After) when a configured limit is exceeded, else None.
    initialize/tools/list are exempt unless the endpoint opted in (RATE-4).
    A rejection is a metric (RATE-3), never an audit record.
    """
    cfg = view.endpoint.rate_limit
    if not cfg or runtime.rate_limiter is None:
        return None
    if not is_tool_call and not cfg.get("include_initialize_list", False):
        return None
    fail_closed = bool(cfg.get("fail_closed", False))
    checks: list[tuple[str, dict]] = []
    endpoint_rule = cfg.get("endpoint")
    if endpoint_rule:
        checks.append((f"ep:{view.endpoint.name}:all", endpoint_rule))
    per_client_rule = cfg.get("per_client")
    if per_client_rule:
        ip = client_ip(request, runtime.settings) if runtime.settings else "unknown"
        identity = _rate_identity(user_id, api_key_id, ip)
        checks.append((f"ep:{view.endpoint.name}:{identity}", per_client_rule))
    for scope, rule in checks:
        result = await runtime.rate_limiter.check(
            scope,
            int(rule["limit"]),
            int(rule["window_seconds"]),
            fail_closed=fail_closed,
        )
        if not result.allowed:
            runtime.counters.inc(RATE_LIMIT_REJECTIONS)
            resp = _rpc_error(rpc_id, -32000, "rate limit exceeded", status=429)
            resp.headers["Retry-After"] = str(result.retry_after)
            return resp
    return None


async def note_auth_failure(request: Request) -> Response | None:
    """RATE-5: count an auth failure for the caller IP; 429 once the IP is locked out.

    Gateway-wide, IP-keyed, shared by the MCP edge and the OAuth token endpoint.
    Returns a 429 (+ Retry-After) when the IP is over the threshold, else None
    (the caller then returns its own 401/invalid_client). Fails open on Redis.
    """
    limiter = getattr(request.app.state, "auth_failure_limiter", None)
    if limiter is None:
        return None
    ip = client_ip(request, request.app.state.settings)
    result = await limiter.record_failure(ip)
    if result.allowed:
        return None
    resp = JSONResponse({"error": "too_many_auth_failures"}, status_code=429)
    resp.headers["Retry-After"] = str(result.retry_after)
    return resp


def _forward_headers(
    request: Request, pt: PresentedTool, auth_method: str, sub: str | None
) -> dict[str, str]:
    """FWD-1/FWD-2/FWD-3."""
    extra: dict[str, str] = {}
    for client_header, upstream_header in pt.server.forward_headers.items():
        lower = client_header.lower()
        if lower in DENIED_FORWARD_HEADERS or lower.startswith(("sec-", "proxy-")):
            continue
        value = request.headers.get(client_header)
        if value is not None:
            extra[upstream_header] = value
    # client-supplied identity header is always stripped; gateway injects its own
    extra.pop(IDENTITY_HEADER, None)
    if pt.server.send_identity_header and sub is not None:
        extra[IDENTITY_HEADER] = sub
    return extra


class GatewayRuntime:
    """Per-app gateway wiring (attached to app.state.gateway)."""

    def __init__(
        self,
        *,
        session_store,
        metering,
        audit,
        client_factory,
        runtime_config=None,
        registry=None,
        signals=None,
        upstream_tokens=None,
        public_url="",
        rate_limiter=None,
        auth_failure_limiter=None,
        counters=None,
        settings=None,
    ) -> None:
        self.sessions: SessionStore = session_store
        self.metering = metering
        self.audit = audit
        self.client_factory = client_factory
        self.runtime_config = runtime_config  # spec 02 Config accessors (PROT-2 values)
        self.registry = registry  # replica-pinned streams/calls/replies (SES-13)
        self.signals = signals  # cross-replica routing (SES-13)
        self.upstream_tokens = upstream_tokens  # UpstreamTokenStore | None (spec 23)
        self.public_url = str(public_url).rstrip("/")
        self.rate_limiter = rate_limiter  # RateLimiter | None (spec 16)
        self.auth_failure_limiter = auth_failure_limiter  # AuthFailureLimiter | None (RATE-5)
        self.counters = counters or Counters()  # RATE-3 metrics seam (spec 51)
        self.settings = settings  # for trusted_proxies / auth-failure limits


async def _handle_initialize(
    runtime: GatewayRuntime, view: BundleView, body: dict, auth: tuple
) -> Response:
    auth_method, user_id, user_email, api_key_id = auth
    params = body.get("params") or {}
    session_id = SessionStore.new_session_id()
    record = SessionRecord(
        session_id=session_id,
        endpoint_name=view.endpoint.name,
        bundle_name=view.bundle.name,
        auth_method=auth_method,
        user_id=user_id,
        user_email=user_email,
        api_key_id=api_key_id,
        protocol_version=params.get("protocolVersion", PROTOCOL_VERSION),
        client_capabilities=params.get("capabilities") or {},
    )
    await runtime.sessions.create(record)  # SES-1
    response = _rpc_result(
        body.get("id"),
        {
            "protocolVersion": record.protocol_version,
            "capabilities": {"tools": {"listChanged": True}},  # PROT-11 (BND-7 via GET stream)
            "serverInfo": {"name": f"bundlemcp/{view.bundle.name}", "version": "0.1.0"},
            **({"instructions": view.bundle.description} if view.bundle.description else {}),
        },
    )
    response.headers[SESSION_HEADER] = session_id
    return response


def _tools_payload(view: BundleView) -> list[dict[str, Any]]:
    tools = []
    for pt in view.tools:
        entry: dict[str, Any] = {"name": pt.presented_name, "inputSchema": pt.input_schema}
        if pt.title:
            entry["title"] = pt.title
        if pt.description:
            entry["description"] = pt.description
        if pt.annotations:
            entry["annotations"] = pt.annotations
        tools.append(entry)
    return tools


@dataclass
class _CallOutcome:
    status: str  # "success" | "error"
    result: Any = None  # mcp CallToolResult on success
    error_message: str | None = None
    code: int | None = None


async def _timeout_config(runtime: GatewayRuntime) -> tuple[float, bool, float]:
    """PROT-2 values from runtime config (defaults if unavailable)."""
    rc = runtime.runtime_config
    if rc is None:
        return (60.0, True, 1800.0)
    return (
        float(await rc.get("call_timeout")),
        bool(await rc.get("reset_timeout_on_progress")),
        float(await rc.get("max_total_timeout")),
    )


def _build_relay_handlers(
    runtime: GatewayRuntime, session_id: str, wait_timeout: float
) -> dict:
    """PROT-4/5: elicitation/sampling handlers that forward to the downstream client.

    Only attached when the client advertised the capability (caller gates this).
    Each request is delivered on the client's GET stream and its reply awaited
    via a correlation future (SES-13), bounded by the call's timeout (PROT-6).
    """
    import asyncio

    async def _roundtrip(method: str, params: dict) -> dict:
        correlation_id = uuid.uuid4().hex
        future = runtime.registry.register_reply(correlation_id)
        request = {"jsonrpc": "2.0", "id": correlation_id, "method": method, "params": params}
        await runtime.signals.deliver(session_id, request)
        try:
            reply = await asyncio.wait_for(future, timeout=wait_timeout)
        finally:
            runtime.registry.unregister_reply(correlation_id)
        if "error" in reply:
            raise RuntimeError(reply["error"].get("message", "client rejected request"))
        return reply.get("result", {})

    async def elicitation_handler(message, response_type, params, context):
        from fastmcp.client.elicitation import ElicitResult

        payload = params.model_dump(by_alias=True, mode="json", exclude_none=True)
        result = await _roundtrip("elicitation/create", payload)
        return ElicitResult(action=result.get("action", "decline"), content=result.get("content"))

    async def sampling_handler(messages, params, context):
        from mcp.types import CreateMessageResult

        payload = params.model_dump(by_alias=True, mode="json", exclude_none=True)
        result = await _roundtrip("sampling/createMessage", payload)
        return CreateMessageResult.model_validate(result)

    return {"elicitation_handler": elicitation_handler, "sampling_handler": sampling_handler}


async def _drive_upstream(
    runtime: GatewayRuntime,
    pt: PresentedTool,
    arguments: dict,
    extra_headers: dict[str, str],
    record: SessionRecord,
    sub: str | None,
    handle,
    cfg: tuple[float, bool, float],
    *,
    on_progress,
) -> _CallOutcome:
    """Run the upstream call with progress-aware timeout (PROT-2) and cancel (PROT-3)."""
    import asyncio

    call_timeout, reset_on_progress, max_total = cfg
    loop = asyncio.get_running_loop()
    last_activity = loop.time()

    async def progress_handler(progress: float, total: float | None, message: str | None) -> None:
        nonlocal last_activity
        last_activity = loop.time()  # PROT-2: reset the idle window
        if on_progress is not None:
            await on_progress(progress, total, message)

    # PROT-5: capability intersection — attach relay handlers only for what the
    # downstream client advertised, and only if we can route replies.
    handlers: dict = {}
    caps = record.client_capabilities or {}
    if runtime.registry is not None and runtime.signals is not None:
        all_handlers = _build_relay_handlers(runtime, record.session_id, max_total)
        if "elicitation" in caps:
            handlers["elicitation_handler"] = all_handlers["elicitation_handler"]
        if "sampling" in caps:
            handlers["sampling_handler"] = all_handlers["sampling_handler"]

    async def run():
        client = runtime.client_factory(pt.server, extra_headers, **handlers)
        async with client:
            await runtime.sessions.set_binding(
                record.session_id,
                UpstreamBinding(server_name=pt.server.name, identity_key=sub),
            )
            return await client.call_tool_mcp(
                pt.tool.name, arguments, progress_handler=progress_handler
            )

    call_task = asyncio.create_task(run())
    timeout_reason: list[str | None] = [None]
    cancelled = [False]

    async def watchdog():
        while not call_task.done():
            await asyncio.sleep(0.05)
            now = loop.time()
            if now - record_start > max_total:
                timeout_reason[0] = "max_total_timeout"
                call_task.cancel()
                return
            idle_since = last_activity if reset_on_progress else record_start
            if now - idle_since > call_timeout:
                timeout_reason[0] = "call_timeout"
                call_task.cancel()
                return

    async def canceller():
        if handle is None:
            return
        await handle.cancel_event.wait()  # PROT-3 (may be set cross-replica)
        cancelled[0] = True
        call_task.cancel()

    record_start = loop.time()
    wd = asyncio.create_task(watchdog())
    cn = asyncio.create_task(canceller())
    try:
        result = await call_task
        status = "error" if result.isError else "success"  # MID-3 isError mapping
        return _CallOutcome(status=status, result=result)
    except asyncio.CancelledError:
        if cancelled[0]:
            return _CallOutcome(status="error", error_message="cancelled", code=-32800)
        if timeout_reason[0] is not None:
            return _CallOutcome(status="error", error_message=timeout_reason[0], code=-32000)
        raise
    except Exception as exc:
        log.warning("upstream.call_failed", server=pt.server.name, tool=pt.tool.name)
        return _CallOutcome(status="error", error_message=str(exc)[:500], code=-32000)
    finally:
        wd.cancel()
        cn.cancel()


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
    """PROT-1: stream notifications/progress, then the final JSON-RPC result."""
    import asyncio
    import json as jsonlib

    from fastapi.responses import StreamingResponse

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
            outcome = await _drive_upstream(
                runtime, pt, arguments, extra_headers, record, sub, handle, cfg,
                on_progress=on_progress,
            )
            await queue.put(("final", outcome))

        task = asyncio.create_task(runner())
        try:
            while True:
                kind, data = await queue.get()
                if kind == "progress":
                    yield f"data: {jsonlib.dumps(data)}\n\n"
                    continue
                outcome: _CallOutcome = data
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
                yield f"data: {jsonlib.dumps(msg)}\n\n"
                break
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


async def _handle_call(
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

    sub = record.user_id or (f"api_key:{record.api_key_id}" if record.api_key_id else None)

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
            AuditRecord(status=AuditStatus.DENIED, denied_reason="unknown_or_disabled_tool",
                        **audit_kwargs)
        )
        return _rpc_error(rpc_id, -32602, f"Unknown tool: {presented_name}")

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
            return _rpc_error(rpc_id, -32000, "upstream OAuth not configured on this gateway")
        per_user = pt.server.identity_mode == IdentityMode.PER_USER
        if per_user:
            if record.user_id is None:  # UPO-6 guard (should be unreachable)
                return _rpc_error(
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
            return _rpc_error(rpc_id, -32000, f"upstream not connected — connect at {connect_url}")
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
        fail_open = getattr(runtime.metering, "fail_open", False)
        decision = MeterDecision(allowed=fail_open, reason="metering_unavailable")
    if not decision.allowed:
        runtime.audit.record(
            AuditRecord(
                status=AuditStatus.DENIED,
                denied_reason=decision.reason or "denied",
                **audit_kwargs,
            )
        )
        return _rpc_error(rpc_id, -32000, decision.reason or "call denied")

    extra_headers = _forward_headers(request, pt, record.auth_method, sub)
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
    if runtime.registry is not None and rpc_id is not None:
        handle = runtime.registry.register_call(record.session_id, str(rpc_id))

    # PROT-1: when the client sent a progressToken, stream progress as SSE and
    # deliver the result as the final event. Otherwise the buffered JSON path.
    if progress_token is not None:
        return _sse_call_response(
            runtime, pt, arguments, extra_headers, record, sub, handle, cfg,
            progress_token, rpc_id, finalize,
        )

    started = time.monotonic()
    outcome = await _drive_upstream(
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
            outcome = await _drive_upstream(
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
        return _rpc_result(rpc_id, payload)
    return _rpc_error(rpc_id, outcome.code or -32000, outcome.error_message or "call failed")


@router.post("/{endpoint_name}/mcp", include_in_schema=False)
async def mcp_post(endpoint_name: str, request: Request) -> Response:
    runtime: GatewayRuntime = request.app.state.gateway
    async with request.app.state.session_factory() as db:
        view = await load_bundle_view(db, endpoint_name)
        if view is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        auth = await _authenticate(request, db, view)
    if auth is None:
        locked = await note_auth_failure(request)  # RATE-5
        return locked if locked is not None else _unauthorized(request, endpoint_name)

    try:
        body = await request.json()
    except ValueError:
        return _rpc_error(None, -32700, "parse error", status=400)
    method = body.get("method", "")

    if method == "initialize":
        limited = await _enforce_rate_limit(
            runtime, request, view, auth[1], auth[3], body.get("id"), is_tool_call=False
        )
        if limited is not None:
            return limited
        return await _handle_initialize(runtime, view, body, auth)

    # SES-2/SES-3: everything else requires a live session record
    session_id = request.headers.get(SESSION_HEADER, "")
    record = await runtime.sessions.load(session_id) if session_id else None
    if record is None or record.endpoint_name != endpoint_name:
        return JSONResponse({"error": "session not found"}, status_code=404)
    await runtime.sessions.touch(session_id)  # SES-1 (+ PROT-8 for ping)

    # PROT-4: a JSON-RPC response (no method, has result/error) is the client's
    # reply to a server->client request — route it to the awaiting call.
    if not method and ("result" in body or "error" in body):
        if runtime.signals is not None and body.get("id") is not None:
            await runtime.signals.reply(str(body["id"]), body)
        return Response(status_code=202)

    if method == "notifications/cancelled":
        # PROT-3: route the cancel to the replica holding the in-flight call
        cancel_id = (body.get("params") or {}).get("requestId")
        if cancel_id is not None and runtime.signals is not None:
            await runtime.signals.cancel(session_id, str(cancel_id))
        return Response(status_code=202)
    if method.startswith("notifications/"):
        return Response(status_code=202)
    if method == "ping":
        return _rpc_result(body.get("id"), {})
    if method == "tools/list":
        limited = await _enforce_rate_limit(
            runtime, request, view, record.user_id, record.api_key_id, body.get("id"),
            is_tool_call=False,
        )
        if limited is not None:
            return limited
        return _rpc_result(body.get("id"), {"tools": _tools_payload(view)})
    if method == "tools/call":
        limited = await _enforce_rate_limit(
            runtime, request, view, record.user_id, record.api_key_id, body.get("id"),
            is_tool_call=True,
        )
        if limited is not None:
            return limited
        return await _handle_call(runtime, request, view, record, body)
    return _rpc_error(body.get("id"), -32601, f"method not supported: {method}")


@router.delete("/{endpoint_name}/mcp", include_in_schema=False)
async def mcp_delete(endpoint_name: str, request: Request) -> Response:
    """SES-4: explicit session termination."""
    runtime: GatewayRuntime = request.app.state.gateway
    session_id = request.headers.get(SESSION_HEADER, "")
    if session_id:
        await runtime.sessions.delete(session_id)
    return Response(status_code=204)


@router.get("/{endpoint_name}/mcp", include_in_schema=False)
async def mcp_get(endpoint_name: str, request: Request) -> Response:
    """EP-1a: the server->client event stream (SSE).

    Carries list_changed notifications (BND-7) and server->client requests
    (PROT-4). The open stream is replica-pinned; messages from other replicas
    arrive via the SignalBus (SES-13).
    """
    import asyncio
    import json as jsonlib

    from fastapi.responses import StreamingResponse

    runtime: GatewayRuntime = request.app.state.gateway
    async with request.app.state.session_factory() as db:
        view = await load_bundle_view(db, endpoint_name)
        if view is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        auth = await _authenticate(request, db, view)
    if auth is None:
        locked = await note_auth_failure(request)  # RATE-5
        return locked if locked is not None else _unauthorized(request, endpoint_name)

    session_id = request.headers.get(SESSION_HEADER, "")
    record = await runtime.sessions.load(session_id) if session_id else None
    if record is None or record.endpoint_name != endpoint_name:
        return JSONResponse({"error": "session not found"}, status_code=404)

    queue = runtime.registry.register_stream(session_id)

    async def event_source():
        try:
            yield ": connected\n\n"
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"data: {jsonlib.dumps(payload)}\n\n"
                except TimeoutError:
                    yield ": keepalive\n\n"
                    await runtime.sessions.touch(session_id)  # stream open = active
        finally:
            runtime.registry.unregister_stream(session_id, queue)

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
