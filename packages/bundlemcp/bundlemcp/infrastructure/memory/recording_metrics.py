from typing import Any

from bundlemcp.application.contracts.observability.gateway_metrics import (
    AuditDropReason,
    RateLimitScope,
    ToolCallStatus,
)


class RecordingMetrics:
    """Every recorded fact, in order, as (method name, labels): for application tests."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def _record(self, name: str, **labels: Any) -> None:
        self.events.append((name, labels))

    def count(self, name: str) -> int:
        return sum(1 for event, _labels in self.events if event == name)

    def tool_call_finished(
        self, *, endpoint: str, server: str, status: ToolCallStatus, seconds: float
    ) -> None:
        self._record("tool_call_finished", endpoint=endpoint, server=server, status=status)

    def rate_limit_rejected(self, *, endpoint: str, limit: RateLimitScope) -> None:
        self._record("rate_limit_rejected", endpoint=endpoint, limit=limit)

    def traffic_limiter_failed_open(self) -> None:
        self._record("traffic_limiter_failed_open")

    def auth_limiter_failed_open(self) -> None:
        self._record("auth_limiter_failed_open")

    def auth_failed(self) -> None:
        self._record("auth_failed")

    def auth_locked_out(self) -> None:
        self._record("auth_locked_out")

    def metering_denied(self, *, endpoint: str) -> None:
        self._record("metering_denied", endpoint=endpoint)

    def upstream_call_started(self, *, server: str) -> None:
        self._record("upstream_call_started", server=server)

    def upstream_call_finished(self, *, server: str, ok: bool) -> None:
        self._record("upstream_call_finished", server=server, ok=ok)

    def tools_list_degraded(self, *, endpoint: str, server: str) -> None:
        self._record("tools_list_degraded", endpoint=endpoint, server=server)

    def audit_dropped(self, *, reason: AuditDropReason) -> None:
        self._record("audit_dropped", reason=reason)
