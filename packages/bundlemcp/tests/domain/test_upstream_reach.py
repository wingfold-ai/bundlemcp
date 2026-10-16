"""What a failed upstream call tells about the upstream's health (UPS-4)."""

import pytest
from bundlemcp.domain.servers.observed_response import ObservedResponse
from bundlemcp.domain.servers.response_log import ResponseLog
from bundlemcp.domain.servers.upstream_reach import CONNECTION_CLOSED, UpstreamReach


def _log(*, status: int | None = None, json=False, transport=False, oversized=False):
    log = ResponseLog()
    if status is not None:
        content_type = "application/json" if json else "text/html"
        log.record(ObservedResponse(status=status, content_type=content_type))
    if transport:
        log.record_transport_failure()
    if oversized:
        log.record_oversized(1024)
    return log


@pytest.mark.parametrize(
    ("log", "code", "reach"),
    [
        (_log(transport=True), None, UpstreamReach.UNREACHABLE),  # connect error
        (_log(), CONNECTION_CLOSED, UpstreamReach.UNREACHABLE),  # the stream dropped
        (_log(status=502), -32603, UpstreamReach.UNREACHABLE),  # a proxy's error page
        (_log(status=401), -32603, UpstreamReach.UNDECIDED),  # refused credential
        (_log(status=403), None, UpstreamReach.UNDECIDED),
        (_log(status=500, json=True), -32603, UpstreamReach.ANSWERED),  # the upstream's own error
        (_log(), -32602, UpstreamReach.ANSWERED),  # a JSON-RPC error answer
        (_log(transport=True, oversized=True), None, UpstreamReach.UNDECIDED),  # gateway's cap
        (_log(), None, UpstreamReach.UNDECIDED),  # e.g. the gateway's own bug
    ],
)
def test_ups4_failure_reach(log, code, reach):
    """UPS-4: only an unreachable upstream counts; an answer heals; a refusal is neither."""
    assert UpstreamReach.of_failure(log, jsonrpc_code=code) is reach
