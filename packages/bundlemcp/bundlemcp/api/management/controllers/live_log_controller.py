"""The live log: every replica's recent events, and a stream of new ones."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from bundlemcp.api.http.route import route
from bundlemcp.api.http.service_providers import LiveLogServiceProvider
from bundlemcp.api.management.controllers.management_controller import ManagementController
from bundlemcp.api.mcp.protocol.sse import SSE_HEADERS, SSE_KEEPALIVE
from bundlemcp.application.contracts.live_state.live_log_entry import LiveLogEntry
from bundlemcp.application.management.live_log_filter import LiveLogFilter

# streams one replica serves at once; each holds a blocking read on the store
MAX_STREAMS = 20
WAIT_SECONDS = 10.0


def live_log_filter(
    level: Annotated[
        str | None,
        Query(pattern=r"^(debug|info|warning|error|critical)$", description="Lowest severity"),
    ] = None,
    q: Annotated[
        str | None, Query(max_length=200, description="Text the event or a field contains")
    ] = None,
    upstream: Annotated[str | None, Query(description="Only events about this upstream")] = None,
    endpoint: Annotated[str | None, Query(description="Only events about this endpoint")] = None,
) -> LiveLogFilter:
    return LiveLogFilter(level=level, text=q, upstream=upstream, endpoint=endpoint)


FilterProvider = Annotated[LiveLogFilter, Depends(live_log_filter)]


class LiveLogController(ManagementController):
    prefix = "/logs"
    tags = ("logs",)

    def __init__(self) -> None:
        super().__init__()
        self._open_streams = 0  # per replica, so the cap is too

    @route.get("")
    async def recent_logs(
        self,
        service: LiveLogServiceProvider,
        wanted: FilterProvider,
        limit: Annotated[int, Query(ge=1, le=500, description="Most entries returned")] = 200,
    ) -> list[LiveLogEntry]:
        return await service.recent(wanted, limit=limit)

    @route.get("/stream", response_class=StreamingResponse)
    async def stream_logs(
        self,
        service: LiveLogServiceProvider,
        wanted: FilterProvider,
        since: Annotated[
            str | None,
            Query(description="Id of the last entry seen; omitted, only new entries are sent"),
        ] = None,
        last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    ) -> StreamingResponse:
        if self._open_streams >= MAX_STREAMS:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS, "too many live log streams on this replica"
            )
        self._open_streams += 1
        cursor = last_event_id or since or "$"
        return StreamingResponse(
            self._events(service.follow(wanted, after=cursor, wait_seconds=WAIT_SECONDS)),
            media_type="text/event-stream",
            headers=SSE_HEADERS,
        )

    async def _events(self, batches: AsyncIterator[list[LiveLogEntry]]) -> AsyncIterator[str]:
        try:
            async for batch in batches:
                if not batch:
                    yield SSE_KEEPALIVE
                for entry in batch:
                    yield f"id: {entry.id}\ndata: {entry.model_dump_json()}\n\n"
        finally:
            self._open_streams -= 1
