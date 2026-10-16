"""Liveness and readiness probes."""

from fastapi.responses import JSONResponse

from bundlemcp.api.http.controller import Controller
from bundlemcp.api.http.providers import DrainProvider, ReadinessProvider
from bundlemcp.api.http.route import route


class HealthController(Controller):
    include_in_schema = False

    @route.get("/healthz")
    async def healthz(self) -> dict[str, str]:
        return {"status": "ok"}

    @route.get("/readyz")
    async def readyz(self, readiness: ReadinessProvider, drain: DrainProvider) -> JSONResponse:
        """Ready means both stores are reachable and the replica is not shutting down."""
        if drain.draining:
            return JSONResponse(status_code=503, content={"status": "draining"})
        await readiness.check()
        return JSONResponse(content={"status": "ready"})
