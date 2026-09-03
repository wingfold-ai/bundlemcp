"""Public MCP endpoints: POST/GET/DELETE /{endpoint_name}/mcp.

The Streamable-HTTP edge is implemented directly here (not via FastMCP's
server session manager) so that session state lives in Redis and any replica
serves any request. FastMCP is used for the upstream side.
"""

import asyncio
import json
import time
import uuid
from datetime import UTC
from typing import Any

import structlog
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from fastmcp.client.elicitation import ElicitResult
from mcp.types import (
    CreateMessageResult,
    PromptReference,
    ResourceTemplateReference,
    Root,
)
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from bundlemcp.crypto import ACCESS_TOKEN_PREFIX, hash_token
from bundlemcp.gateway.composition import PREFIX_SEP, BundleView, PresentedTool, load_bundle_view
from bundlemcp.gateway.mcp_endpoint._call_outcome import _CallOutcome
from bundlemcp.gateway.mcp_endpoint.gateway_runtime import GatewayRuntime
from bundlemcp.gateway.metering import MeterContext, MeterDecision, new_idempotency_key
from bundlemcp.gateway.metrics import RATE_LIMIT_REJECTIONS
from bundlemcp.gateway.protocol_version import SUPPORTED_PROTOCOL_VERSIONS, negotiate_version
from bundlemcp.gateway.proxy import client_ip
from bundlemcp.models import (
    AuditRecord,
    AuditStatus,
    EndpointAuthMode,
    IdentityMode,
    OAuthAccessToken,
    ServerAuthMode,
    User,
    utcnow,
)
from bundlemcp.oauth.upstream_client import NeedsConnect
from bundlemcp.schemas import RateLimitConfig, RateRule
from bundlemcp.services import AuthService
from bundlemcp.store.sessions import SessionRecord, SessionStore, UpstreamBinding

log = structlog.get_logger(__name__)

router = APIRouter()

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
    """401 with the challenge + per-endpoint protected-resource metadata (RFC 9728)."""
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
    """Direct-DB bearer validation + audience check.

    Returns (user_id, email) or None.
    """
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer ") or not auth[7:].startswith(ACCESS_TOKEN_PREFIX):
        return None
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
    """Returns (auth_method, user_id, user_email, api_key_id) or None.

    Precedence oauth > api_key.
    """
    modes = set(view.endpoint.auth_modes)
    if EndpointAuthMode.OAUTH in modes:
        oauth = await _resolve_oauth_bearer(request, db, view)
        if oauth is not None:
            user_id, email = oauth
            return ("oauth", user_id, email, None)
    if EndpointAuthMode.API_KEY in modes:
        key = await AuthService(db).authenticate_api_key(
            authorization=request.headers.get("authorization"),
            x_api_key=request.headers.get("x-api-key"),
        )
        if key is not None:
            if key.kind == "endpoint" and key.endpoint_ids:
                if str(view.endpoint.id) not in key.endpoint_ids:
                    return None  # scoped key, wrong endpoint (KEY-2)
            return ("api_key", None, None, str(key.id))
    if EndpointAuthMode.NONE in modes:
        return ("none", None, None, None)
    return None


def _rate_identity(user_id: str | None, api_key_id: str | None, ip: str) -> str:
    """Per-client rate-limit bucket key: OAuth user, else API key, else client IP."""
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
    """Endpoint-wide + per-client fixed-window limits.

    Returns a 429 (+ Retry-After) when a configured limit is exceeded, else None.
    initialize/tools/list are exempt unless the endpoint opted in.
    A rejection is a metric, never an audit record.
    """
    if not view.endpoint.rate_limit:
        return None
    try:
        cfg = RateLimitConfig.model_validate(view.endpoint.rate_limit)
    except ValidationError:
        # A stored config whose shape has drifted must not take the endpoint
        # down; serve unlimited and say so loudly.
        log.warning("ratelimit.config_malformed", endpoint=view.endpoint.name)
        return None
    if not is_tool_call and not cfg.include_initialize_list:  # RATE-4
        return None

    checks: list[tuple[str, RateRule]] = []
    if cfg.endpoint is not None:
        checks.append((f"ep:{view.endpoint.name}:all", cfg.endpoint))
    if cfg.per_client is not None:  # EP-6
        ip = client_ip(request, runtime.settings)
        identity = _rate_identity(user_id, api_key_id, ip)
        checks.append((f"ep:{view.endpoint.name}:{identity}", cfg.per_client))

    for scope, rule in checks:
        result = await runtime.rate_limiter.check(
            scope, rule.limit, rule.window_seconds, fail_closed=cfg.fail_closed
        )
        if not result.allowed:
            runtime.counters.inc(RATE_LIMIT_REJECTIONS)
            resp = _rpc_error(rpc_id, -32000, "rate limit exceeded", status=429)
            resp.headers["Retry-After"] = str(result.retry_after)
            return resp
    return None


async def note_auth_failure(request: Request) -> Response | None:
    """Count an auth failure for the caller IP; 429 once the IP is locked out.

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


def _forward_headers(request: Request, server, sub: str | None) -> dict[str, str]:
    """Build the extra headers forwarded upstream.

    Applies the server's configured header mappings, skipping denied headers,
    then injects the gateway's own identity header (any client-supplied
    identity header is always stripped).
    """
    extra: dict[str, str] = {}
    for client_header, upstream_header in server.forward_headers.items():
        lower = client_header.lower()
        if lower in DENIED_FORWARD_HEADERS or lower.startswith(("sec-", "proxy-")):
            continue
        value = request.headers.get(client_header)
        if value is not None:
            extra[upstream_header] = value
    # client-supplied identity header is always stripped; gateway injects its own
    extra.pop(IDENTITY_HEADER, None)
    if server.send_identity_header and sub is not None:
        extra[IDENTITY_HEADER] = sub
    return extra


def _aggregate_capabilities(view: BundleView) -> dict[str, Any]:
    """PROT-11: advertise a capability iff ≥1 enabled member advertises it.

    Source is each member's discovery-time capabilities snapshot (DISC-6), so
    initialize never fans out to members. The gateway always supports tools.
    """
    caps: dict[str, Any] = {"tools": {"listChanged": True}}
    has_prompts = has_resources = has_completions = has_logging = False
    resources_subscribe = False
    for server in view.servers.values():
        member = server.capabilities or {}
        if "prompts" in member:
            has_prompts = True
        if "resources" in member:
            has_resources = True
            if (member.get("resources") or {}).get("subscribe"):
                resources_subscribe = True
        if "completions" in member:
            has_completions = True
        if "logging" in member:
            has_logging = True
    if has_prompts:
        caps["prompts"] = {"listChanged": True}
    if has_resources:
        resources: dict[str, Any] = {"listChanged": True}
        if resources_subscribe:
            resources["subscribe"] = True
        caps["resources"] = resources
    if has_completions:
        caps["completions"] = {}
    if has_logging:
        caps["logging"] = {}
    return caps


async def _handle_initialize(
    runtime: GatewayRuntime, view: BundleView, body: dict, auth: tuple
) -> Response:
    auth_method, user_id, user_email, api_key_id = auth
    params = body.get("params") or {}
    negotiated = negotiate_version(params.get("protocolVersion"))  # PROT-12
    if negotiated is None:
        return _rpc_error(
            body.get("id"),
            -32602,
            f"unsupported protocolVersion {params.get('protocolVersion')!r}; "
            f"supported: {', '.join(SUPPORTED_PROTOCOL_VERSIONS)}",
        )
    session_id = SessionStore.new_session_id()
    record = SessionRecord(
        session_id=session_id,
        endpoint_name=view.endpoint.name,
        bundle_name=view.bundle.name,
        auth_method=auth_method,
        user_id=user_id,
        user_email=user_email,
        api_key_id=api_key_id,
        protocol_version=negotiated,
        client_capabilities=params.get("capabilities") or {},
    )
    await runtime.sessions.create(record)  # SES-1
    response = _rpc_result(
        body.get("id"),
        {
            "protocolVersion": negotiated,
            "capabilities": _aggregate_capabilities(view),  # PROT-11
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


async def _timeout_config(runtime: GatewayRuntime) -> tuple[float, bool, float]:
    """Timeout values from runtime config; unset keys fall back to the registry."""
    rc = runtime.runtime_config
    return (
        float(await rc.get("call_timeout")),
        bool(await rc.get("reset_timeout_on_progress")),
        float(await rc.get("max_total_timeout")),
    )


def _build_relay_handlers(runtime: GatewayRuntime, session_id: str, wait_timeout: float) -> dict:
    """Elicitation/sampling handlers that forward to the downstream client.

    Only attached when the client advertised the capability (caller gates this).
    Each request is delivered on the client's GET stream and its reply awaited
    via a correlation future, bounded by the call's timeout.
    """

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
        payload = params.model_dump(by_alias=True, mode="json", exclude_none=True)
        result = await _roundtrip("elicitation/create", payload)
        return ElicitResult(action=result.get("action", "decline"), content=result.get("content"))

    async def sampling_handler(messages, params, context):
        payload = params.model_dump(by_alias=True, mode="json", exclude_none=True)
        result = await _roundtrip("sampling/createMessage", payload)
        return CreateMessageResult.model_validate(result)

    async def roots_handler(context):
        # PROT-4: relay the upstream's roots/list to the downstream client.
        result = await _roundtrip("roots/list", {})
        return [Root.model_validate(r) for r in result.get("roots", [])]

    async def log_handler(message):
        # PROT-7: forward an upstream log to the client's stream (notification).
        await runtime.signals.deliver(
            session_id,
            {
                "jsonrpc": "2.0",
                "method": "notifications/message",
                "params": message.model_dump(by_alias=True, mode="json", exclude_none=True),
            },
        )

    return {
        "elicitation_handler": elicitation_handler,
        "sampling_handler": sampling_handler,
        "roots_handler": roots_handler,
        "log_handler": log_handler,
    }


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
    """Run the upstream call with progress-aware timeout and cancellation support."""
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
    all_handlers = _build_relay_handlers(runtime, record.session_id, max_total)
    if "elicitation" in caps:
        handlers["elicitation_handler"] = all_handlers["elicitation_handler"]
    if "sampling" in caps:
        handlers["sampling_handler"] = all_handlers["sampling_handler"]
    if "roots" in caps:  # PROT-4: Client kwarg is `roots`
        handlers["roots"] = all_handlers["roots_handler"]
    if "logging" in caps:  # PROT-7
        handlers["log_handler"] = all_handlers["log_handler"]

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
            outcome = await _drive_upstream(
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

    sub = _sub_for(record)

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
        return _rpc_error(rpc_id, -32000, decision.reason or "call denied")

    extra_headers = _forward_headers(request, pt.server, sub)
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


# --- read-only passthrough: prompts / resources / completions (BND-8, PROT-9) ---
#
# Live, uncurated: each request fans out to the enabled member servers. Prompt
# names are prefixed `server__prompt`; resource URIs pass through unchanged and
# are routed on read by fan-out (first owner wins). No metering, no tool-call
# audit — these are reads.


def _sub_for(record: SessionRecord) -> str | None:
    return record.user_id or (f"api_key:{record.api_key_id}" if record.api_key_id else None)


async def _readonly_headers(
    runtime: GatewayRuntime, request: Request, server, record: SessionRecord
) -> dict[str, str]:
    """Forward headers + upstream-OAuth bearer for a read-only member call.

    Raises NeedsConnect if an upstream_oauth member has no usable token.
    """
    headers = _forward_headers(request, server, _sub_for(record))
    if server.auth_mode == ServerAuthMode.UPSTREAM_OAUTH:
        if runtime.upstream_tokens is None:
            raise NeedsConnect("upstream_oauth_not_configured")
        token_user: uuid.UUID | None = None
        if server.identity_mode == IdentityMode.PER_USER:
            if record.user_id is None:
                raise NeedsConnect("per_user_requires_user")
            token_user = uuid.UUID(record.user_id)
        access = await runtime.upstream_tokens.ensure_access_token(server, token_user)
        headers["Authorization"] = f"Bearer {access}"
    return headers


def _connect_hint(runtime: GatewayRuntime, server) -> str:
    suffix = "?as=me" if server.identity_mode == IdentityMode.PER_USER else ""
    url = f"{runtime.public_url}/oauth/upstream/{server.name}/connect{suffix}"
    return f"upstream not connected — connect at {url}"


async def _fanout_readonly(runtime, request, record, servers, call):
    """Run `call(client)` against each member concurrently; skip + WARN failures.

    Returns a list of (server, result | None) — a None means that member was
    unreachable/unconnected and was omitted (DISC-4: degrade observably).
    """

    async def _one(server):
        try:
            headers = await _readonly_headers(runtime, request, server, record)
        except NeedsConnect:
            log.warning("passthrough.member_unconnected", server=server.name)
            return server, None
        try:
            client = runtime.client_factory(server, headers)
            async with client:
                return server, await call(client)
        except Exception:
            log.warning("passthrough.member_failed", server=server.name, exc_info=True)
            return server, None

    return list(await asyncio.gather(*[_one(s) for s in servers]))


def _dump(obj) -> dict[str, Any]:
    return obj.model_dump(by_alias=True, mode="json", exclude_none=True)


async def _handle_prompts_list(runtime, request, view, record, rpc_id) -> Response:
    """PROT-11/BND-8: merge members' prompts with `server__name` prefixing."""

    async def call(client):
        return await client.list_prompts()

    prompts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for server, member_prompts in await _fanout_readonly(
        runtime, request, record, view.servers.values(), call
    ):
        if member_prompts is None:
            continue
        for prompt in member_prompts:
            entry = _dump(prompt)
            entry["name"] = f"{server.name}{PREFIX_SEP}{prompt.name}"
            if entry["name"] in seen:
                continue
            seen.add(entry["name"])
            prompts.append(entry)
    return _rpc_result(rpc_id, {"prompts": prompts})


async def _handle_prompts_get(runtime, request, view, record, body, rpc_id) -> Response:
    params = body.get("params") or {}
    presented = params.get("name", "")
    server_name, _, prompt_name = presented.partition(PREFIX_SEP)  # BND-2 first-`__`
    server = view.servers.get(server_name)
    if server is None or not prompt_name:
        return _rpc_error(rpc_id, -32602, f"unknown prompt: {presented}")
    try:
        headers = await _readonly_headers(runtime, request, server, record)
    except NeedsConnect:
        return _rpc_error(rpc_id, -32000, _connect_hint(runtime, server))
    try:
        client = runtime.client_factory(server, headers)
        async with client:
            result = await client.get_prompt_mcp(prompt_name, params.get("arguments") or None)
    except Exception as exc:
        log.warning("prompts.get_failed", server=server_name)
        return _rpc_error(rpc_id, -32000, str(exc)[:200])
    return _rpc_result(rpc_id, _dump(result))


async def _handle_completion(runtime, request, view, record, body, rpc_id) -> Response:
    """PROT-9: route completion to the owning member (prompt ref de-prefixed;
    resource-template ref resolved by URI fan-out)."""
    params = body.get("params") or {}
    ref = params.get("ref") or {}
    argument = params.get("argument") or {}
    context = (params.get("context") or {}).get("arguments")

    if ref.get("type") == "ref/prompt":
        presented = ref.get("name", "")
        server_name, _, prompt_name = presented.partition(PREFIX_SEP)
        server = view.servers.get(server_name)
        if server is None or not prompt_name:
            return _rpc_error(rpc_id, -32602, f"unknown prompt ref: {presented}")
        member_ref = PromptReference(type="ref/prompt", name=prompt_name)
        candidates = [server]
    elif ref.get("type") == "ref/resource":
        member_ref = ResourceTemplateReference(type="ref/resource", uri=ref.get("uri", ""))
        candidates = list(view.servers.values())  # URI is not prefixed → fan-out
    else:
        return _rpc_error(rpc_id, -32602, f"unsupported completion ref: {ref.get('type')}")

    for server in candidates:
        try:
            headers = await _readonly_headers(runtime, request, server, record)
            client = runtime.client_factory(server, headers)
            async with client:
                result = await client.complete_mcp(member_ref, argument, context)
            return _rpc_result(rpc_id, _dump(result))
        except Exception:
            log.warning("completion.member_failed", server=server.name)
            continue
    return _rpc_result(rpc_id, {"completion": {"values": [], "hasMore": False}})


async def _merge_by_key(runtime, request, view, record, call, key: str) -> list[dict[str, Any]]:
    """Fan-out a resource-list method, merging entries de-duplicated by `key`."""
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for server, member in await _fanout_readonly(
        runtime, request, record, view.servers.values(), call
    ):
        if member is None:
            continue
        for obj in member:
            entry = _dump(obj)
            identity = entry.get(key)
            if identity in seen:
                log.warning("resources.collision", key=identity, server=server.name)
                continue
            seen.add(identity)
            items.append(entry)
    return items


async def _handle_resources_list(runtime, request, view, record, rpc_id) -> Response:
    """BND-8: merge members' resources; URIs pass through unchanged (dedupe by URI)."""

    async def call(client):
        return await client.list_resources()

    items = await _merge_by_key(runtime, request, view, record, call, "uri")
    return _rpc_result(rpc_id, {"resources": items})


async def _handle_resource_templates_list(runtime, request, view, record, rpc_id) -> Response:
    async def call(client):
        return await client.list_resource_templates()

    items = await _merge_by_key(runtime, request, view, record, call, "uriTemplate")
    return _rpc_result(rpc_id, {"resourceTemplates": items})


async def _handle_resources_read(runtime, request, view, record, body, rpc_id) -> Response:
    """BND-8: resolve the owner by fan-out — first enabled member that owns the URI."""
    uri = (body.get("params") or {}).get("uri", "")
    for server in view.servers.values():
        try:
            headers = await _readonly_headers(runtime, request, server, record)
            client = runtime.client_factory(server, headers)
            async with client:
                result = await client.read_resource_mcp(uri)
            return _rpc_result(rpc_id, _dump(result))
        except Exception:
            continue
    return _rpc_error(rpc_id, -32002, f"resource not found: {uri}")


async def _handle_resources_subscribe(rpc_id) -> Response:
    """Accept the subscription (request/response half).

    notifications/resources/updated push is pooling-dependent (ADR-0021) and is
    not delivered between calls under per-call upstream connections.
    """
    log.warning("resources.subscribe_push_pooling_dependent")
    return _rpc_result(rpc_id, {})


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
        if body.get("id") is not None:
            await runtime.signals.reply(str(body["id"]), body)
        return Response(status_code=202)

    if method == "notifications/cancelled":
        # PROT-3: route the cancel to the replica holding the in-flight call
        cancel_id = (body.get("params") or {}).get("requestId")
        if cancel_id is not None:
            await runtime.signals.cancel(session_id, str(cancel_id))
        return Response(status_code=202)
    if method.startswith("notifications/"):
        return Response(status_code=202)
    if method == "ping":
        return _rpc_result(body.get("id"), {})
    if method == "tools/list":
        limited = await _enforce_rate_limit(
            runtime,
            request,
            view,
            record.user_id,
            record.api_key_id,
            body.get("id"),
            is_tool_call=False,
        )
        if limited is not None:
            return limited
        return _rpc_result(body.get("id"), {"tools": _tools_payload(view)})
    if method == "tools/call":
        limited = await _enforce_rate_limit(
            runtime,
            request,
            view,
            record.user_id,
            record.api_key_id,
            body.get("id"),
            is_tool_call=True,
        )
        if limited is not None:
            return limited
        return await _handle_call(runtime, request, view, record, body)
    if method == "prompts/list":
        return await _handle_prompts_list(runtime, request, view, record, body.get("id"))
    if method == "prompts/get":
        return await _handle_prompts_get(runtime, request, view, record, body, body.get("id"))
    if method == "completion/complete":
        return await _handle_completion(runtime, request, view, record, body, body.get("id"))
    if method == "resources/list":
        return await _handle_resources_list(runtime, request, view, record, body.get("id"))
    if method == "resources/templates/list":
        return await _handle_resource_templates_list(runtime, request, view, record, body.get("id"))
    if method == "resources/read":
        return await _handle_resources_read(runtime, request, view, record, body, body.get("id"))
    if method in ("resources/subscribe", "resources/unsubscribe"):
        return await _handle_resources_subscribe(body.get("id"))
    if method == "logging/setLevel":
        # PROT-7: accepted; the level applies on each member's next connection
        # (per-call model — no standing upstream connection to set it on now).
        return _rpc_result(body.get("id"), {})
    return _rpc_error(body.get("id"), -32601, f"method not supported: {method}")


@router.delete("/{endpoint_name}/mcp", include_in_schema=False)
async def mcp_delete(endpoint_name: str, request: Request) -> Response:
    """Explicit session termination."""
    runtime: GatewayRuntime = request.app.state.gateway
    session_id = request.headers.get(SESSION_HEADER, "")
    if session_id:
        await runtime.sessions.delete(session_id)
    return Response(status_code=204)


@router.get("/{endpoint_name}/mcp", include_in_schema=False)
async def mcp_get(endpoint_name: str, request: Request) -> Response:
    """The server->client event stream (SSE).

    Carries list_changed notifications and server->client requests. The open
    stream is replica-pinned; messages from other replicas arrive via the
    SignalBus.
    """
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
                    yield f"data: {json.dumps(payload)}\n\n"
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
