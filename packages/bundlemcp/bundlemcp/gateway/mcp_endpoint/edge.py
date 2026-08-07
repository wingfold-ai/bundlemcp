"""Public MCP endpoints: POST/DELETE /{endpoint_name}/mcp.

The Streamable-HTTP edge is implemented directly here (not via FastMCP's
server session manager) so that session state lives in Redis and any replica
serves any request. FastMCP is used for the upstream side.
"""

import asyncio
import time
import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from bundlemcp.gateway.composition import BundleView, PresentedTool, load_bundle_view
from bundlemcp.gateway.mcp_endpoint._call_outcome import _CallOutcome
from bundlemcp.gateway.mcp_endpoint.gateway_runtime import GatewayRuntime
from bundlemcp.gateway.metering import MeterContext, MeterDecision, new_idempotency_key
from bundlemcp.models import AuditRecord, AuditStatus, EndpointAuthMode
from bundlemcp.services import AuthService
from bundlemcp.store.sessions import SessionRecord, SessionStore, UpstreamBinding

log = structlog.get_logger(__name__)

router = APIRouter()

SESSION_HEADER = "mcp-session-id"
PROTOCOL_VERSION = "2025-11-25"
CALL_TIMEOUT = 60.0  # seconds; becomes runtime-tunable with spec 33

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
        protocol_version=PROTOCOL_VERSION,
        client_capabilities=params.get("capabilities") or {},
    )
    await runtime.sessions.create(record)  # SES-1
    response = _rpc_result(
        body.get("id"),
        {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": True}},
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


async def _drive_upstream(
    runtime: GatewayRuntime,
    pt: PresentedTool,
    arguments: dict,
    extra_headers: dict[str, str],
    record: SessionRecord,
    sub: str | None,
) -> _CallOutcome:
    """Run the upstream call, mapping every failure onto a call outcome."""

    async def run():
        client = runtime.client_factory(pt.server, extra_headers)
        async with client:
            await runtime.sessions.set_binding(
                record.session_id,
                UpstreamBinding(server_name=pt.server.name, identity_key=sub),
            )
            return await client.call_tool_mcp(pt.tool.name, arguments)

    try:
        result = await asyncio.wait_for(run(), timeout=CALL_TIMEOUT)
        status = "error" if result.isError else "success"  # MID-3 isError mapping
        return _CallOutcome(status=status, result=result)
    except TimeoutError:
        return _CallOutcome(status="error", error_message="call_timeout", code=-32000)
    except Exception as exc:
        log.warning("upstream.call_failed", server=pt.server.name, tool=pt.tool.name)
        return _CallOutcome(status="error", error_message=str(exc)[:500], code=-32000)


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

    extra_headers = _forward_headers(request, pt.server, sub)

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

    started = time.monotonic()
    outcome = await _drive_upstream(runtime, pt, arguments, extra_headers, record, sub)
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
        return _unauthorized(request, endpoint_name)

    try:
        body = await request.json()
    except ValueError:
        return _rpc_error(None, -32700, "parse error", status=400)
    method = body.get("method", "")

    if method == "initialize":
        return await _handle_initialize(runtime, view, body, auth)

    # SES-2/SES-3: everything else requires a live session record
    session_id = request.headers.get(SESSION_HEADER, "")
    record = await runtime.sessions.load(session_id) if session_id else None
    if record is None or record.endpoint_name != endpoint_name:
        return JSONResponse({"error": "session not found"}, status_code=404)
    await runtime.sessions.touch(session_id)  # SES-1 (+ PROT-8 for ping)

    if method.startswith("notifications/"):
        return Response(status_code=202)
    if method == "ping":
        return _rpc_result(body.get("id"), {})
    if method == "tools/list":
        return _rpc_result(body.get("id"), {"tools": _tools_payload(view)})
    if method == "tools/call":
        return await _handle_call(runtime, request, view, record, body)
    return _rpc_error(body.get("id"), -32601, f"method not supported: {method}")


@router.delete("/{endpoint_name}/mcp", include_in_schema=False)
async def mcp_delete(endpoint_name: str, request: Request) -> Response:
    """Explicit session termination."""
    runtime: GatewayRuntime = request.app.state.gateway
    session_id = request.headers.get(SESSION_HEADER, "")
    if session_id:
        await runtime.sessions.delete(session_id)
    return Response(status_code=204)
