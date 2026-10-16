from enum import StrEnum
from typing import Protocol, runtime_checkable


class ToolCallStatus(StrEnum):
    """How a tool call ended, as its metrics label it."""

    SUCCESS = "success"
    ERROR = "error"
    DENIED = "denied"


class RateLimitScope(StrEnum):
    """Which configured limit refused a request."""

    ENDPOINT = "endpoint"
    CLIENT = "client"


@runtime_checkable
class GatewayMetrics(Protocol):
    """Every fact the gateway counts, one method each.

    Label values are endpoint and server names (chosen by the admin) or come
    from the enums above; no method takes a caller, a key, a header value or a
    tool argument, so none can become a label.
    """

    def tool_call_finished(
        self, *, endpoint: str, server: str, status: ToolCallStatus, seconds: float
    ) -> None: ...

    def rate_limit_rejected(self, *, endpoint: str, limit: RateLimitScope) -> None: ...

    def traffic_limiter_failed_open(self) -> None:
        """The traffic rate limiter could not reach its store and let a request through."""
        ...

    def auth_limiter_failed_open(self) -> None:
        """The auth-failure limiter could not reach its store and checked nothing."""
        ...

    def auth_failed(self) -> None: ...

    def auth_locked_out(self) -> None: ...

    def metering_denied(self, *, endpoint: str) -> None: ...

    def upstream_call_started(self, *, server: str) -> None: ...

    def upstream_call_finished(self, *, server: str, ok: bool) -> None: ...

    def tools_list_degraded(self, *, endpoint: str, server: str) -> None:
        """A tools/list included a member upstream whose health is error."""
        ...
