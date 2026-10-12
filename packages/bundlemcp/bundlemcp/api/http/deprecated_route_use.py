"""Recording that automation still calls a deprecated path, and refusing it after sunset."""

import structlog
from fastapi import HTTPException, Request, status

from bundlemcp.api.http.deprecated_api_route import DeprecatedAPIRoute
from bundlemcp.api.http.management_auth import ServiceAuthProvider
from bundlemcp.api.http.providers import ClockProvider, CountersProvider, RateLimiterProvider
from bundlemcp.application.contracts.live_state.counters import DEPRECATED_ROUTE_REQUESTS

log = structlog.get_logger(__name__)

WARN_WINDOW_SECONDS = 3600


class DeprecatedRouteUse:
    """A dependency of every deprecated alias of a management route.

    Each use is counted per old path. A warning naming the caller and the path
    to move to is logged at most once per caller and path per hour, across
    every replica, so a busy script does not flood the log. Once the sunset
    date has passed the alias answers 410 Gone with the new path instead.
    """

    async def __call__(
        self,
        request: Request,
        caller: ServiceAuthProvider,
        limiter: RateLimiterProvider,
        counters: CountersProvider,
        clock: ClockProvider,
    ) -> None:
        route: DeprecatedAPIRoute = request.scope["route"]
        successor = route.successor_path(request.url.path, request.path_params)
        former = route.former_template(request.url.path, request.path_params)
        if route.deprecation.is_sunset(clock.now()):  # API-8
            raise HTTPException(
                status.HTTP_410_GONE,
                f"this path was removed on {route.deprecation.sunset_on}; use {successor}",
            )
        counters.inc(f"{DEPRECATED_ROUTE_REQUESTS}:{former}")
        once = await limiter.check(
            f"deprecated-route:{request.method}:{former}:{caller.caller_key}",
            limit=1,
            window=WARN_WINDOW_SECONDS,
        )
        if once.allowed:
            log.warning(
                "api.deprecated_route",
                route=former,
                method=request.method,
                successor=successor,
                caller=caller.caller_key,
                sunset=str(route.deprecation.sunset_on),
            )
