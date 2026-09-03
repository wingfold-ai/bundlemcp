"""Running one upstream tool call under timeout and cancellation."""

import asyncio

import structlog

from bundlemcp.gateway.composition import PresentedTool
from bundlemcp.gateway.mcp_endpoint.call_outcome import CallOutcome
from bundlemcp.gateway.mcp_endpoint.gateway_runtime import GatewayRuntime
from bundlemcp.gateway.mcp_endpoint.relay_handlers import build_relay_handlers
from bundlemcp.store.sessions import SessionRecord, UpstreamBinding

log = structlog.get_logger(__name__)


async def drive_upstream(
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
) -> CallOutcome:
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
    all_handlers = build_relay_handlers(runtime, record.session_id, max_total)
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
        return CallOutcome(status=status, result=result)
    except asyncio.CancelledError:
        if cancelled[0]:
            return CallOutcome(status="error", error_message="cancelled", code=-32800)
        if timeout_reason[0] is not None:
            return CallOutcome(status="error", error_message=timeout_reason[0], code=-32000)
        raise
    except Exception as exc:
        log.warning("upstream.call_failed", server=pt.server.name, tool=pt.tool.name)
        return CallOutcome(status="error", error_message=str(exc)[:500], code=-32000)
    finally:
        wd.cancel()
        cn.cancel()
