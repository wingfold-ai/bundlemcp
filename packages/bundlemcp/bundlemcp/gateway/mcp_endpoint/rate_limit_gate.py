"""Applying an endpoint's configured limits to one request."""

import structlog
from fastapi import Response
from pydantic import ValidationError

from bundlemcp.gateway.mcp_endpoint.endpoint_context import EndpointContext
from bundlemcp.gateway.mcp_endpoint.jsonrpc import rpc_error
from bundlemcp.gateway.mcp_endpoint.jsonrpc_message import JsonRpcMessage
from bundlemcp.gateway.metrics import RATE_LIMIT_REJECTIONS, Counters
from bundlemcp.gateway.proxy import client_ip
from bundlemcp.gateway.ratelimit import RateLimiter
from bundlemcp.models import CallerIdentity
from bundlemcp.schemas import RateLimitConfig, RateRule
from bundlemcp.settings import Settings

log = structlog.get_logger(__name__)


class RateLimitGate:
    """Endpoint-wide and per-client fixed-window limits.

    initialize and tools/list are exempt unless the endpoint opted in. A
    rejection is a metric, never an audit record.
    """

    def __init__(self, limiter: RateLimiter, counters: Counters, settings: Settings) -> None:
        self._limiter = limiter
        self._counters = counters
        self._settings = settings

    @staticmethod
    def _bucket(identity: CallerIdentity, ip: str) -> str:
        """Per-client bucket key: OAuth user, else API key, else client IP."""
        if identity.user_id:
            return f"user:{identity.user_id}"
        if identity.api_key_id:
            return f"apikey:{identity.api_key_id}"
        return f"ip:{ip}"

    async def check(
        self, ctx: EndpointContext, message: JsonRpcMessage, *, tool_call: bool
    ) -> Response | None:
        """A 429 with Retry-After when a configured limit is exceeded, else None."""
        endpoint = ctx.view.endpoint
        if not endpoint.rate_limit:
            return None
        try:
            config = RateLimitConfig.model_validate(endpoint.rate_limit)
        except ValidationError:
            # A stored config whose shape has drifted must not take the endpoint
            # down; serve unlimited and say so loudly.
            log.warning("ratelimit.config_malformed", endpoint=endpoint.name)
            return None
        if not tool_call and not config.include_initialize_list:  # RATE-4
            return None

        checks: list[tuple[str, RateRule]] = []
        if config.endpoint is not None:
            checks.append((f"ep:{endpoint.name}:all", config.endpoint))
        if config.per_client is not None:  # EP-6
            ip = client_ip(ctx.request, self._settings)
            checks.append(
                (f"ep:{endpoint.name}:{self._bucket(ctx.identity, ip)}", config.per_client)
            )

        for scope, rule in checks:
            result = await self._limiter.check(
                scope, rule.limit, rule.window_seconds, fail_closed=config.fail_closed
            )
            if not result.allowed:
                self._counters.inc(RATE_LIMIT_REJECTIONS)
                response = rpc_error(message.id, -32000, "rate limit exceeded", status=429)
                response.headers["Retry-After"] = str(result.retry_after)
                return response
        return None
