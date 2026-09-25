"""Seeing the HTTP answers the MCP client reduces to one generic error."""

from collections.abc import Generator

import httpx2

from bundlemcp.domain.servers.observed_response import ObservedResponse
from bundlemcp.domain.servers.response_log import ResponseLog
from bundlemcp.domain.upstream_oauth.upstream_challenge import UpstreamChallenge

USABLE_MEDIA_TYPES = ("application/json", "text/event-stream")


class ResponseObserver(httpx2.Auth):
    """Records every unusable upstream response into a caller's log.

    Installed as the transport's auth hook, which sees each response before
    the MCP client does, without reading its body — an event stream stays a
    stream. It adds nothing to the request.
    """

    def __init__(self, log: ResponseLog) -> None:
        self._log = log

    def auth_flow(self, request: httpx2.Request) -> Generator[httpx2.Request, httpx2.Response]:
        response = yield request
        content_type = response.headers.get("content-type", "").lower()
        usable = response.is_success and (
            not content_type or content_type.startswith(USABLE_MEDIA_TYPES)
        )
        if not usable:
            self._log.record(
                ObservedResponse(
                    status=response.status_code,
                    content_type=content_type,
                    challenge=UpstreamChallenge.parse(response.headers.get("www-authenticate")),
                )
            )
