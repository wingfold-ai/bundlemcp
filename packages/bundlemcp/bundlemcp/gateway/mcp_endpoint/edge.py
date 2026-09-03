"""Public MCP endpoints: POST/GET/DELETE /{endpoint_name}/mcp.

The Streamable-HTTP edge is implemented directly here (not via FastMCP's
server session manager) so that session state lives in Redis and any replica
serves any request. FastMCP is used for the upstream side.

This module owns the HTTP surface and the JSON-RPC method dispatch; each method
is handled by a module beside it.
"""

import asyncio
import json
from typing import Any

import structlog
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from bundlemcp.gateway.composition import BundleView, aggregate_capabilities, load_bundle_view
from bundlemcp.gateway.mcp_endpoint.authentication import (
    authenticate,
    note_auth_failure,
    unauthorized,
)
from bundlemcp.gateway.mcp_endpoint.gateway_runtime import GatewayRuntime
from bundlemcp.gateway.mcp_endpoint.jsonrpc import rpc_error, rpc_result
from bundlemcp.gateway.mcp_endpoint.passthrough import (
    handle_completion,
    handle_prompts_get,
    handle_prompts_list,
    handle_resource_templates_list,
    handle_resources_list,
    handle_resources_read,
    handle_resources_subscribe,
)
from bundlemcp.gateway.mcp_endpoint.rate_limit import enforce_rate_limit
from bundlemcp.gateway.mcp_endpoint.tool_call import handle_call
from bundlemcp.gateway.protocol_version import SUPPORTED_PROTOCOL_VERSIONS, negotiate_version
from bundlemcp.models import CallerIdentity
from bundlemcp.store.sessions import SessionRecord, SessionStore

log = structlog.get_logger(__name__)

router = APIRouter()

SESSION_HEADER = "mcp-session-id"

# FWD-2: never forwardable, enforced at runtime on top of write-time checks


async def _handle_initialize(
    runtime: GatewayRuntime, view: BundleView, body: dict, identity: CallerIdentity
) -> Response:
    params = body.get("params") or {}
    negotiated = negotiate_version(params.get("protocolVersion"))  # PROT-12
    if negotiated is None:
        return rpc_error(
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
        identity=identity,
        protocol_version=negotiated,
        client_capabilities=params.get("capabilities") or {},
    )
    await runtime.sessions.create(record)  # SES-1
    response = rpc_result(
        body.get("id"),
        {
            "protocolVersion": negotiated,
            "capabilities": aggregate_capabilities(view),  # PROT-11
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


@router.post("/{endpoint_name}/mcp", include_in_schema=False)
async def mcp_post(endpoint_name: str, request: Request) -> Response:
    runtime: GatewayRuntime = request.app.state.gateway
    async with request.app.state.session_factory() as db:
        view = await load_bundle_view(db, endpoint_name)
        if view is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        auth = await authenticate(request, db, view)
    if auth is None:
        locked = await note_auth_failure(request)  # RATE-5
        return locked if locked is not None else unauthorized(request, endpoint_name)

    try:
        body = await request.json()
    except ValueError:
        return rpc_error(None, -32700, "parse error", status=400)
    method = body.get("method", "")

    if method == "initialize":
        limited = await enforce_rate_limit(
            runtime, request, view, auth, body.get("id"), is_tool_call=False
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
        return rpc_result(body.get("id"), {})
    if method == "tools/list":
        limited = await enforce_rate_limit(
            runtime,
            request,
            view,
            record.identity,
            body.get("id"),
            is_tool_call=False,
        )
        if limited is not None:
            return limited
        return rpc_result(body.get("id"), {"tools": _tools_payload(view)})
    if method == "tools/call":
        limited = await enforce_rate_limit(
            runtime,
            request,
            view,
            record.identity,
            body.get("id"),
            is_tool_call=True,
        )
        if limited is not None:
            return limited
        return await handle_call(runtime, request, view, record, body)
    if method == "prompts/list":
        return await handle_prompts_list(runtime, request, view, record, body.get("id"))
    if method == "prompts/get":
        return await handle_prompts_get(runtime, request, view, record, body, body.get("id"))
    if method == "completion/complete":
        return await handle_completion(runtime, request, view, record, body, body.get("id"))
    if method == "resources/list":
        return await handle_resources_list(runtime, request, view, record, body.get("id"))
    if method == "resources/templates/list":
        return await handle_resource_templates_list(runtime, request, view, record, body.get("id"))
    if method == "resources/read":
        return await handle_resources_read(runtime, request, view, record, body, body.get("id"))
    if method in ("resources/subscribe", "resources/unsubscribe"):
        return await handle_resources_subscribe(body.get("id"))
    if method == "logging/setLevel":
        # PROT-7: accepted; the level applies on each member's next connection
        # (per-call model — no standing upstream connection to set it on now).
        return rpc_result(body.get("id"), {})
    return rpc_error(body.get("id"), -32601, f"method not supported: {method}")


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
        auth = await authenticate(request, db, view)
    if auth is None:
        locked = await note_auth_failure(request)  # RATE-5
        return locked if locked is not None else unauthorized(request, endpoint_name)

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
