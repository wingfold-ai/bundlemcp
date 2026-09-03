"""Applying an endpoint's configured limits to one request."""

from typing import Any

import structlog
from fastapi import Request, Response
from pydantic import ValidationError

from bundlemcp.gateway.composition import BundleView
from bundlemcp.gateway.mcp_endpoint.gateway_runtime import GatewayRuntime
from bundlemcp.gateway.mcp_endpoint.jsonrpc import rpc_error
from bundlemcp.gateway.metrics import RATE_LIMIT_REJECTIONS
from bundlemcp.gateway.proxy import client_ip
from bundlemcp.schemas import RateLimitConfig, RateRule

log = structlog.get_logger(__name__)


def _rate_identity(user_id: str | None, api_key_id: str | None, ip: str) -> str:
    """Per-client rate-limit bucket key: OAuth user, else API key, else client IP."""
    if user_id:
        return f"user:{user_id}"
    if api_key_id:
        return f"apikey:{api_key_id}"
    return f"ip:{ip}"


async def enforce_rate_limit(
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
            resp = rpc_error(rpc_id, -32000, "rate limit exceeded", status=429)
            resp.headers["Retry-After"] = str(result.retry_after)
            return resp
    return None
